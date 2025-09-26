import os
import json
import traceback
import boto3
import asyncio
import numpy as np
import time
import re
from typing import List, Tuple
from asyncio import run
from dotenv import load_dotenv
from functools import lru_cache
from openai import OpenAI
from urllib.parse import urlsplit, urlunsplit
from flask import g

from langchain_community.embeddings import BedrockEmbeddings
from langchain_community.vectorstores import FAISS

from utils.user.enhanced_chitchat_classifier import get_enhanced_response, is_chitchat
from utils.user.advanced_analyzer import analyze_document_question, format_analysis_result
from utils.user.conversation_memory import get_conversation_memory, create_user_conversation, add_message_to_conversation, get_conversation_context
from utils.user.contextual_understanding import analyze_text_context, enhance_context_with_history
from utils.admin.upload_s3_utils import s3_client, BUCKET_NAME, DATA_DIR, download_from_s3
from utils.aws_client import bedrock_embeddings
from utils.user.email_utils import (
    is_leave_email_request, is_quit_email_request, is_ot_email_request, is_remote_email_request,
    handle_urgent_vs_planned_workflow, smart_email_processor,
    is_in_leave_email
)
from models.models_db import FileDocument
from utils.admin.response_utils import extract_references_from_docs, format_references_in_response, stream_response_chunks, stream_llm_response

from utils.user.llm_services import chatgpt_generate, build_prompt
from utils.user.language_utils import detect_language, unified_classification
from utils.user.keywords_utils import (
    is_hr_related_question, check_keywords_in_docs, enhance_question_for_search,
    lightweight_context_analysis, enhance_question_with_context
)
from utils.user.vector_store_utils import (
    get_latest_n_files, load_multiple_vector_stores, retrieve_relevant_docs,
    build_context, prioritize_files_for_hr_questions
)
from utils.user.chitchat_handler import handle_chitchat, should_handle_as_chitchat
from utils.user.response_utils import (
    notify_no_documents, notify_error_loading_vectors, notify_no_answer_found,
    validate_response, handle_follow_up_questions, is_offensive_or_sensitive, professional_refusal
)

model = "gpt-4o-mini"

load_dotenv()

session = boto3.Session(
    aws_access_key_id=os.getenv("ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("SECRET_ACCESS_KEY"),
    region_name=os.getenv("REGION")
)
s3_client = session.client("s3")
bedrock_client = session.client(service_name="bedrock-runtime")

class StreamingResultContainer:
    """Container to share data between generator and caller"""
    def __init__(self):
        self.references = []
        self.full_response = ""

def get_response_from_multiple_sources(
    question: str, 
    retrieve_k: int, 
    rerank_k: int, 
    enable_rerank: bool = True, 
    model=None, 
    chat_history: List[Tuple[str, str]] = None, 
    user_id: str = None, 
    conversation_id: str = None,
    stream: bool = False,
    cancellation_check=None
) -> dict:
    """Main function to get response from multiple sources with enhanced email processing and fast responses"""
    
    if stream:
        result_container = StreamingResultContainer()
        streaming_generator = get_streaming_response_from_multiple_sources(
            question=question,
            retrieve_k=retrieve_k,
            rerank_k=rerank_k,
            enable_rerank=enable_rerank,
            model=model,
            chat_history=chat_history,
            user_id=user_id,
            conversation_id=conversation_id,
            cancellation_check=cancellation_check,
            result_container=result_container
        )
        return {
            "generator": streaming_generator,
            "references": [],
            "_result_container": result_container
        }
    
    t0 = time.time()
    lang = detect_language(question)

    # Offensive/sensitive content guardrail
    if is_offensive_or_sensitive(question):
        refusal = professional_refusal(lang)
        return {"response": refusal, "references": [], "method": "guardrail"}
    
    user_id = g.user.get("user_id") or g.user.get("id")
    
    # Check for fast HR responses first
    from utils.user.fast_response_utils import get_immediate_response
    from utils.user.email_utils import analyze_intent_with_llm
    try:
        intent_analysis = analyze_intent_with_llm(question, lang)
        current_intent = intent_analysis.get('intent', 'unknown')
        
        if current_intent in ['hr_inquiry', 'hr_partner', 'policy_inquiry']:
            fast_response = get_immediate_response(question, current_intent)
            if fast_response:
                _save_conversation_message(user_id, conversation_id, "assistant", fast_response)
                return {"response": fast_response, "references": [], "method": "quick_response"}
    except Exception as e:
        print(f"[WARNING] Fast response check failed: {e}")
        pass
    
    is_email_request = (
        is_leave_email_request(question) or 
        is_quit_email_request(question) or 
        is_ot_email_request(question) or 
        is_remote_email_request(question)
    )
    
    is_in_email_conversation = is_in_leave_email(user_id)

    if is_email_request or is_in_email_conversation:
        try:
            response = smart_email_processor(question, user_id, lang)
            return {"response": response, "references": []}
        except Exception as e:
            print(f"[ERROR] Email processor failed: {e}")
            from utils.user.email_utils import clear_conversation_state
            clear_conversation_state(user_id)
    
    if is_in_email_conversation and not is_email_request:
        from utils.user.email_utils import clear_conversation_state
        clear_conversation_state(user_id)
    
    enhanced_question = _handle_conversation_memory(question, user_id, conversation_id)
    
    classification_result = unified_classification(enhanced_question, lang, get_enhanced_response)
    
    classification_result = handle_follow_up_questions(question, classification_result)
    
    if classification_result['method'] == 'faiss' and classification_result['response']:
        _save_conversation_message(user_id, conversation_id, "assistant", classification_result['response'])
        return {"response": classification_result['response'], "references": []}
    
    if should_handle_as_chitchat(classification_result, question):
        response = handle_chitchat(question, lang, t0, model)
        _save_conversation_message(user_id, conversation_id, "assistant", response)
        return {"response": response, "references": []}
    
    context_analysis = lightweight_context_analysis(enhanced_question, chat_history)
    
    enhanced_question = _enhance_question_for_search(question, classification_result, context_analysis, chat_history)
    
    try:
        from config.performance import MAX_FILES_TO_LOAD
    except ImportError:
        MAX_FILES_TO_LOAD = 20
    
    from utils.user.vector_store_utils import get_smart_files
    latest_files = get_smart_files(enhanced_question, MAX_FILES_TO_LOAD)
    
    if not latest_files:
        return {"response": notify_no_documents(lang), "references": []}

    if classification_result['question_type'] == 'hr_question':
        prioritized_files = prioritize_files_for_hr_questions(latest_files, enhanced_question)
    else:
        prioritized_files = latest_files

    vector_stores = load_multiple_vector_stores(prioritized_files, bedrock_embeddings)
    if not vector_stores:
        print("[WARNING] No vector stores available, using chitchat fallback")
        chitchat_response = handle_chitchat(question, lang, t0, model)
        return {"response": chitchat_response, "references": []}

    docs = retrieve_relevant_docs(vector_stores, enhanced_question, k=retrieve_k)
    
    if not docs:
        print("[WARNING] No documents retrieved, using chitchat fallback")
        chitchat_response = handle_chitchat(question, lang, t0, model)
        return {"response": chitchat_response, "references": []}
    
    if not check_keywords_in_docs(docs):
        fallback_docs = retrieve_relevant_docs(vector_stores, question, k=retrieve_k)
        if fallback_docs and check_keywords_in_docs(fallback_docs):
            docs = fallback_docs
        else:
            print("[WARNING] No relevant keywords found, but continuing with document search")

    context = build_context(docs, enhanced_question)
    safe_question = enhanced_question or question or ""
    safe_context = context or ""
    prompt = build_prompt(safe_context, safe_question, lang, chat_history=chat_history)

    try:
        response = chatgpt_generate(prompt, model=model or "gpt-4o-mini").strip()
        
        validation_result = validate_response(response, lang)
        if validation_result:
            return validation_result

        references = extract_references_from_docs(docs, response, question)
        formatted_response = format_references_in_response(response, references)
        
        _save_conversation_message(user_id, conversation_id, "assistant", formatted_response)
        
        return {"response": formatted_response, "references": references}
        
    except Exception as e:
        print("[ERROR] Exception in generating response:", flush=True)
        traceback.print_exc()
        error_message = ("Đã xảy ra lỗi hệ thống: " + str(e)) if lang == "vi" else ("A system error occurred: " + str(e))
        return {"response": error_message, "references": []}

def get_streaming_response_from_multiple_sources(
    question: str, 
    retrieve_k: int, 
    rerank_k: int, 
    enable_rerank: bool = True, 
    model=None, 
    chat_history: List[Tuple[str, str]] = None, 
    user_id: str = None, 
    conversation_id: str = None,
    cancellation_check=None,
    result_container=None
):
    """Stream response from multiple sources with enhanced email processing and fast responses"""
    t0 = time.time()
    lang = detect_language(question)

    # Offensive/sensitive content guardrail (streaming)
    if is_offensive_or_sensitive(question):
        refusal = professional_refusal(lang)
        for chunk in stream_response_chunks(refusal):
            if cancellation_check and cancellation_check():
                print("[INFO] Guardrail stream cancelled")
                return
            yield chunk
        return
    
    user_id = g.user.get("user_id") or g.user.get("id")
    
    # Check for fast HR responses first
    from utils.user.fast_response_utils import get_immediate_response
    from utils.user.email_utils import analyze_intent_with_llm
    try:
        intent_analysis = analyze_intent_with_llm(question, lang)
        current_intent = intent_analysis.get('intent', 'unknown')
        
        if current_intent in ['hr_inquiry', 'hr_partner', 'policy_inquiry']:
            fast_response = get_immediate_response(question, current_intent)
            if fast_response:
                _save_conversation_message(user_id, conversation_id, "assistant", fast_response)
                for chunk in stream_response_chunks(fast_response):
                    if cancellation_check and cancellation_check():
                        print("[INFO] Fast response stream cancelled")
                        return
                    yield chunk
                return
    except Exception as e:
        print(f"[WARNING] Fast response check failed: {e}")
        pass
    
    is_email_request = (
        is_leave_email_request(question) or 
        is_quit_email_request(question) or 
        is_ot_email_request(question) or 
        is_remote_email_request(question)
    )
    
    is_in_email_conversation = is_in_leave_email(user_id)

    if is_email_request or is_in_email_conversation:
        try:
            response = smart_email_processor(question, user_id, lang)
            for chunk in stream_response_chunks(response):
                if cancellation_check and cancellation_check():
                    print("[INFO] Email stream cancelled")
                    return
                yield chunk
            return
        except Exception as e:
            print(f"[ERROR] Email processor failed: {e}")
            from utils.user.email_utils import clear_conversation_state
            clear_conversation_state(user_id)
    
    if is_in_email_conversation and not is_email_request:
        from utils.user.email_utils import clear_conversation_state
        clear_conversation_state(user_id)
    
    enhanced_question = _handle_conversation_memory(question, user_id, conversation_id)
    
    classification_result = unified_classification(enhanced_question, lang, get_enhanced_response)
    
    classification_result = handle_follow_up_questions(question, classification_result)
    
    if classification_result['method'] == 'faiss' and classification_result['response']:
        _save_conversation_message(user_id, conversation_id, "assistant", classification_result['response'])
        for chunk in stream_response_chunks(classification_result['response']):
            if cancellation_check and cancellation_check():
                print("[INFO] FAISS stream cancelled")
                return
            yield chunk
        return
    
    if should_handle_as_chitchat(classification_result, question):
        response = handle_chitchat(question, lang, t0, model)
        _save_conversation_message(user_id, conversation_id, "assistant", response)
        for chunk in stream_response_chunks(response):
            if cancellation_check and cancellation_check():
                print("[INFO] Chitchat stream cancelled")
                return
            yield chunk
        return
    
    context_analysis = lightweight_context_analysis(enhanced_question, chat_history)
    
    enhanced_question = _enhance_question_for_search(question, classification_result, context_analysis, chat_history)
    
    try:
        from config.performance import MAX_FILES_TO_LOAD
    except ImportError:
        MAX_FILES_TO_LOAD = 20
    
    from utils.user.vector_store_utils import get_smart_files
    latest_files = get_smart_files(enhanced_question, MAX_FILES_TO_LOAD)
    
    if not latest_files:
        no_docs_response = notify_no_documents(lang)
        for chunk in stream_response_chunks(no_docs_response):
            if cancellation_check and cancellation_check():
                print("[INFO] No docs stream cancelled")
                return
            yield chunk
        return

    if classification_result['question_type'] == 'hr_question':
        prioritized_files = prioritize_files_for_hr_questions(latest_files, enhanced_question)
    else:
        prioritized_files = latest_files

    vector_stores = load_multiple_vector_stores(prioritized_files, bedrock_embeddings)
    if not vector_stores:
        print("[WARNING] No vector stores available, using chitchat fallback")
        chitchat_response = handle_chitchat(question, lang, t0, model)
        for chunk in stream_response_chunks(chitchat_response):
            if cancellation_check and cancellation_check():
                print("[INFO] Vector store fallback stream cancelled")
                return
            yield chunk
        return

    docs = retrieve_relevant_docs(vector_stores, enhanced_question, k=retrieve_k)
    
    if not docs:
        print("[WARNING] No documents retrieved, using chitchat fallback")
        chitchat_response = handle_chitchat(question, lang, t0, model)
        for chunk in stream_response_chunks(chitchat_response):
            if cancellation_check and cancellation_check():
                print("[INFO] No docs fallback stream cancelled")
                return
            yield chunk
        return
    
    if not check_keywords_in_docs(docs):
        fallback_docs = retrieve_relevant_docs(vector_stores, question, k=retrieve_k)
        if fallback_docs and check_keywords_in_docs(fallback_docs):
            docs = fallback_docs
        else:
            print("[WARNING] No relevant keywords found, but continuing with document search")

    context = build_context(docs, enhanced_question)
    safe_question = enhanced_question or question or ""
    safe_context = context or ""
    prompt = build_prompt(safe_context, safe_question, lang, chat_history=chat_history)

    try:
        full_response = ""
        for chunk in stream_llm_response(prompt, model=model, cancellation_check=cancellation_check):
            if cancellation_check and cancellation_check():
                print("[INFO] LLM stream cancelled")
                return
                
            if chunk:
                full_response += chunk
                yield chunk
        
        validation_result = validate_response(full_response, lang)
        if validation_result:
            error_msg = validation_result.get('response', 'Validation failed')
            yield f"\n{error_msg}"
            return

        references = extract_references_from_docs(docs, full_response, question)
        
        if result_container:
            result_container.references = references
            result_container.full_response = full_response
        
        _save_conversation_message(user_id, conversation_id, "assistant", full_response)
        
        
    except Exception as e:
        print("[ERROR] Exception in generating streaming response:", flush=True)
        traceback.print_exc()
        error_message = ("Đã xảy ra lỗi hệ thống: " + str(e)) if lang == "vi" else ("A system error occurred: " + str(e))
        yield error_message

def _handle_conversation_memory(question: str, user_id: str, conversation_id: str) -> str:
    """Handle conversation memory integration"""
    if user_id:
        try:
            if not conversation_id:
                conversation_id = create_user_conversation(user_id)
            
            add_message_to_conversation(conversation_id, "user", question)
            
            conversation_context = get_conversation_context(conversation_id, window_size=5)
            if conversation_context:
                enhanced_question = f"{question} | Context: {conversation_context}"
            else:
                enhanced_question = question
                
        except Exception as e:
            enhanced_question = question
            conversation_id = None
    else:
        enhanced_question = question
    
    return enhanced_question

def _enhance_question_for_search(question: str, classification_result: dict, context_analysis: dict, chat_history: List[Tuple[str, str]] = None) -> str:
    """Enhance question for search with multiple strategies"""
    from utils.user.language_utils import enhance_question_with_llm_analysis
    
    enhanced_question = enhance_question_with_llm_analysis(question, classification_result)
    
    enhanced_question = enhance_question_with_context(enhanced_question, context_analysis, chat_history)
    
    enhanced_question = enhance_question_for_search(enhanced_question)
    
    return enhanced_question

def _save_conversation_message(user_id: str, conversation_id: str, role: str, content: str):
    """Save message to conversation memory"""
    if user_id and conversation_id:
        try:
            add_message_to_conversation(conversation_id, role, content)
        except Exception as e:
            print(f"[ERROR] Failed to save conversation message: {e}")
            pass

