from flask import Blueprint, request, jsonify, g, session, send_file, make_response
import json
from flask import Response
from datetime import datetime, date
import uuid
import os
import threading
import re
import re
import time
from flask_sqlalchemy import SQLAlchemy
from utils.admin.response_utils import ( api_response, message_response, convert_html_links_to_markdown, get_file_info_by_id, sse_event, sse_response, soft_markdown_finalize, MarkdownChunker, stream_response_chunks, stream_with_references, sse_text_event, format_references_in_response )
from utils.admin.upload_s3_utils import download_from_s3
from utils.user.chat_utils import get_response_from_multiple_sources
from models.models_db import db, ConversationLog, ConversationSession, TokenUsage
from error.error_codes import ErrorCode
from utils.admin.session_utils import require_session
from utils.admin.auth_utils import require_member_or_admin
from utils.admin.title_utils import generate_summary_from_question_auto_lang
from utils.admin.token_utils import count_tokens
from utils.user.email_utils import is_in_leave_email, is_leave_email_request, is_quit_email_request, is_ot_email_request, is_remote_email_request
from utils.admin.global_config import get_effective_config, get_global_config
import config.rerank as rerank
from sqlalchemy import func, desc
from sqlalchemy.orm import aliased
from sqlalchemy.sql import distinct, text
from utils.admin.response_utils import create_streaming_response
from utils.user.chat_utils import get_streaming_response_from_multiple_sources
from utils.user.enhanced_chitchat_classifier import get_chitchat_answer, is_chitchat_fast
from utils.user.llm_services import classify_topic_with_keywords_caching
from utils.user.fast_response_utils import get_immediate_response, is_fast_response_available, fast_response_handler
from utils.user.email_utils import clear_conversation_state, smart_email_processor
stream_cancellation_flags = {}
stream_cancellation_lock = threading.Lock()

user_bp = Blueprint("user", __name__, url_prefix="/api/user")

@user_bp.route("/check-session", methods=["GET"])
@require_session
@require_member_or_admin
def get_active_session():
    """
    Kiểm tra session đang hoạt động
    ---
    tags:
      - User
    responses:
      200:
        description: Có session trống đang hoạt động
      404:
        description: Không có session trống
    """
    email = g.user["email"]
    user_id = g.user.get("user_id") or g.user.get("id")
    session = ConversationSession.query.filter_by(email=email, user_id = user_id, is_active=True).first()
    if session:
        has_logs = ConversationLog.query.filter_by(con_id=session.id).first()
        if not has_logs:
            return jsonify(api_response(ErrorCode.SUCCESS, "Empty active session found", {
                "con_id": session.id
            })), 200
    return jsonify(api_response(ErrorCode.NOT_FOUND, "No empty active session found")), 404

@user_bp.route("/start-session", methods=["POST"])
@require_session
@require_member_or_admin
def start_or_reactivate_session():
    """
    Tạo session mới hoặc kích hoạt lại session cũ nếu con_id được truyền vào
    ---
    tags:
      - User
    parameters:
      - name: body
        in: body
        required: false
        schema:
          type: object
          properties:
            con_id:
              type: string
    responses:
      201:
        description: Session được tạo hoặc kích hoạt thành công
      400:
        description: Dữ liệu không hợp lệ
      401:
        description: Unauthorized
    """
    data = request.get_json(force=True)
    requested_con_id = data.get("con_id") if isinstance(data, dict) else None
    email = g.user["email"]
    user_id = g.user.get("user_id") or g.user.get("id")
    now = datetime.now()
    if requested_con_id:
        session = ConversationSession.query.filter_by(id=requested_con_id, user_id=user_id).first()
        if session:
            session.is_active = True
            session.last_asked_at = now
            db.session.commit()
            return jsonify(api_response(ErrorCode.SUCCESS, "Session re-activated successfully", {
                "con_id": session.id
            })), 201

    new_con_id = requested_con_id or str(uuid.uuid4())
    new_session = ConversationSession(
        id=new_con_id,
        user_id=user_id,
        email=email,
        started_at=now,
        last_asked_at=now,
        is_active=True,
    )
    db.session.add(new_session)
    db.session.commit()

    return jsonify(api_response(ErrorCode.SUCCESS, "New session started successfully", {
        "con_id": new_con_id
    })), 201


@user_bp.route("/end-session", methods=["POST"])
@require_session
@require_member_or_admin
def end_session():
    """
    Kết thúc session hiện tại
    ---
    tags:
      - User
    responses:
      200:
        description: Kết thúc session thành công
      400:
        description: Không có session hoạt động
    """
    email = g.user["email"]
    session = ConversationSession.query.filter_by(email=email, is_active=True).first()

    if not session:
        return jsonify(api_response(ErrorCode.BAD_REQUEST, "No active session found")), 400

    session.is_active = False
    db.session.commit()

    return jsonify(api_response(ErrorCode.SUCCESS, "Session ended successfully")), 200

@user_bp.route("/clear-cache", methods=["POST"])
@require_session
@require_member_or_admin
def clear_cache():
    """
    Clear cache cho user
    """
    try:
        user_id = g.user.get("user_id") or g.user.get("id")
        from utils.user.email_utils import refresh_user_cache
        
        refresh_user_cache(user_id)
        
        return jsonify(api_response(ErrorCode.SUCCESS, "Cache cleared successfully")), 200
    except Exception as e:
        return jsonify(api_response(ErrorCode.INTERNAL_SERVER_ERROR, f"Failed to clear cache: {str(e)}")), 500

@user_bp.route("/cache-status", methods=["GET"])
@require_session
@require_member_or_admin
def get_cache_status():
    """
    Lấy trạng thái cache để debug
    """
    try:
        from utils.user.email_utils import get_cache_status
        
        cache_status = get_cache_status()
        
        return jsonify(api_response(ErrorCode.SUCCESS, "Cache status retrieved", cache_status)), 200
    except Exception as e:
        return jsonify(api_response(ErrorCode.INTERNAL_SERVER_ERROR, f"Failed to get cache status: {str(e)}")), 500

@user_bp.route("/ask", methods=["POST"])
@require_session
@require_member_or_admin
def ask():
    """
    Gửi câu hỏi tới chatbot
    ---
    tags:
      - User
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            question:
              type: string
            con_id:
              type: string
            top_k:
              type: integer
              description: (Tuỳ chọn) Số lượng tài liệu tối đa cần truy xuất
    responses:
      200:
        description: Trả lời thành công
      400:
        description: Thiếu thông tin hoặc session không hợp lệ
      500:
        description: Lỗi server
    """
    data = request.json
    question = data.get("question", "").strip()
    con_id = data.get("con_id")
    user_id = g.user.get("user_id") or g.user.get("id")
    email = g.user.get("email")
    now = datetime.now()
    today = date.today()
    lang = "vi"

    
    try:
        from utils.user.llm_services import classify_topic_with_keywords_caching
        _topic_info = classify_topic_with_keywords_caching(question, lang)
        classified_topic = _topic_info.get("topic", "khác")
    except Exception:
        classified_topic = "khác"

    if is_chitchat_fast(question):
      print("ff")
      fast_response = get_chitchat_answer(question)
      if fast_response:
          new_log = ConversationLog(
              con_id=con_id,
              user_id=user_id,
              email=email,
              question=question,
              answer=fast_response,
              topic=classified_topic,
              timestamp=now
          )
          db.session.add(new_log)
          db.session.commit()
          return jsonify(api_response(ErrorCode.SUCCESS, "Fast chitchat response", {"response": fast_response})), 200
    from utils.user.email_utils import analyze_intent_with_llm
    intent_analysis = analyze_intent_with_llm(question, lang)
    current_intent = intent_analysis.get('intent', 'unknown')
    
    is_potential_hr = False
    if current_intent in ['hr_inquiry', 'hr_partner', 'policy_inquiry']:
        is_potential_hr = True
    elif fast_response_handler.contains_hr_keywords(question):
        print(f"[DEBUG] HR keywords detected in question: {question}")
        is_potential_hr = True
        current_intent = 'hr_inquiry'
    
    if is_potential_hr:
        fast_response = get_immediate_response(question, current_intent)
        if fast_response:
            formatted_response = convert_html_links_to_markdown(fast_response)
            
            new_log = ConversationLog(
                con_id=con_id,
                user_id=user_id,
                email=email,
                question=question,
                answer=formatted_response,
                topic=classified_topic,
                timestamp=now
            )
            db.session.add(new_log)
            db.session.commit()
            
            print(f"[DEBUG] Fast response provided for intent: {current_intent}")
            return jsonify(api_response(ErrorCode.SUCCESS, "Fast response provided", {"response": formatted_response})), 200
    
    is_email_request = (
        is_leave_email_request(question) or 
        is_quit_email_request(question) or 
        is_ot_email_request(question) or 
        is_remote_email_request(question) or
        is_in_leave_email(user_id)
    ) 
    
    if not is_email_request and is_in_leave_email(user_id):
        from utils.user.email_utils import clear_conversation_state
        clear_conversation_state(user_id)
    
    if current_intent == 'chitchat' and is_in_leave_email(user_id):
        clear_conversation_state(user_id)
    
    if current_intent == 'policy_inquiry' and is_in_leave_email(user_id):
        clear_conversation_state(user_id)
    
    if current_intent == 'information_request' and is_in_leave_email(user_id):
    
        clear_conversation_state(user_id)
    
    if current_intent in ['policy_inquiry', 'information_request']:
        pass
    elif is_email_request:
        reply = smart_email_processor(question, user_id, lang)
        return jsonify(api_response(ErrorCode.SUCCESS, reply)), 200
    
    if not is_email_request and is_in_leave_email(user_id):
        
        clear_conversation_state(user_id)

    if not question or not con_id:
        return jsonify(api_response(ErrorCode.BAD_REQUEST, "Missing 'question' or 'con_id'")), 400

    session = ConversationSession.query.filter_by(id=con_id, email=email, is_active=True).first()
    if not session:
        return jsonify(api_response(ErrorCode.BAD_REQUEST, "Invalid or inactive session")), 400

    effective_config = get_effective_config(user_id)
    try:
        admin_chat_settings = get_global_config("chat_settings") or {}
        if isinstance(admin_chat_settings, str):
            try:
                admin_chat_settings = json.loads(admin_chat_settings)
            except Exception:
                pass
    except Exception as _cfg_err:
        retrieve_k = 5
        rerank_k = 3
        enable_rerank = True
        model = "gpt-4o-mini"
    else:
        retrieve_k = effective_config["retrieve_k"]
        rerank_k = effective_config["rerank_k"]
        enable_rerank = effective_config["enable_rerank"]
        model = effective_config["model"]

    usage = TokenUsage.query.filter_by(user_id=user_id, date=today).first()
    used = usage.tokens_used if usage else 0
    prompt_tokens = count_tokens(question)
    
    try:
        system_settings = get_global_config("system_settings") or {}
        print(f"[DEBUG] system_settings: {system_settings}")
        
        max_tokens_per_day = system_settings.get("max_tokens_per_day")
        print(f"[DEBUG] max_tokens_per_day from settings: {max_tokens_per_day}")
        
        if max_tokens_per_day is None:
            max_tokens_per_day = 30000
            print(f"[WARNING] Token limit not configured in Admin settings, using default: {max_tokens_per_day}")
    except Exception as e:
        max_tokens_per_day = 30000
        print(f"[WARNING] Using fallback token limit: {max_tokens_per_day}")

    print(f"[TOKEN] Limit: {max_tokens_per_day}, Total: {used + prompt_tokens}")
    if used + prompt_tokens > int(max_tokens_per_day):
        print(f"[TOKEN] User {user_id} exceeded token limit!")
        return jsonify(api_response(ErrorCode.FORBIDDEN, "Bạn đã vượt quá giới hạn token sử dụng trong ngày.", {
            "token_limit": int(max_tokens_per_day),
            "tokens_used": used,
            "tokens_requested": prompt_tokens,
            "remaining_tokens": max(0, int(max_tokens_per_day) - used)
        })), 403

    logs = (
        ConversationLog.query
        .filter(ConversationLog.con_id == con_id)
        .order_by(ConversationLog.timestamp.asc())
        .limit(3)
        .all()
    )
    chat_history = []
    for log in logs:
        chat_history.append({"role": "user", "content": log.question})
        chat_history.append({"role": "assistant", "content": log.answer})

    try:
        print(f"[CONFIG] Using retrieve_k={retrieve_k}, rerank_k={rerank_k}, enable_rerank={enable_rerank}, model={model}")
        result = get_response_from_multiple_sources(
            question=question,
            retrieve_k=retrieve_k,
            rerank_k=rerank_k,
            enable_rerank=enable_rerank,
            model=model,
            chat_history=chat_history
        )
        
        if isinstance(result, dict):
            response = result["response"]
            references = result.get("references", [])
            if (
                not response or not response.strip()
                or response.lower().startswith("xin lỗi")
                or "không thể tìm thấy thông tin" in response.lower()
                or (references is not None and len(references) == 0 and "vivo" in question.lower() and "vinova" not in response.lower())
                # or len(response.strip()) < 30
            ):
                no_answer_msg = "Xin lỗi, tôi không thể tìm thấy thông tin phù hợp để trả lời câu hỏi của bạn."
                return jsonify(api_response(ErrorCode.SUCCESS, "No relevant information found", {"response": no_answer_msg})), 200
        else:
            response = result
            references = []
            
        formatted_response = convert_html_links_to_markdown(response)
            
        response_tokens = count_tokens(formatted_response)
        total_tokens = prompt_tokens + response_tokens

        if usage:
            usage.tokens_used += total_tokens
        else:
            db.session.add(TokenUsage(user_id=user_id, date=today, tokens_used=total_tokens))

        session.last_asked_at = now

        new_log = ConversationLog(
            con_id=con_id,
            user_id=user_id,
            email=email,
            question=question,
            answer=formatted_response,
            topic=classified_topic,
            timestamp=now
        )
        db.session.add(new_log)
        db.session.commit()



        return jsonify(api_response(ErrorCode.SUCCESS, "Answered successfully", {"response": formatted_response})), 200

    except Exception as e:
        db.session.rollback()
        return jsonify(api_response(ErrorCode.SERVER_ERROR, "Lỗi xử lý yêu cầu", {
            "error": str(e)
        })), 500

@user_bp.route("/ask/stream", methods=["POST"]) # Improve in future
@require_session
@require_member_or_admin
def ask_stream():
    if request.method == 'OPTIONS':
        response = make_response()
        response.headers['Access-Control-Allow-Origin'] = request.headers.get('Origin', '*')
        response.headkers['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        return response
        
    data = request.json or {}
    question = (data.get("question") or "").strip()
    con_id = data.get("con_id")
    user_id = g.user.get("user_id") or g.user.get("id")
    email = g.user.get("email")
    today = date.today()
    now = datetime.now()
    lang = "vi"
    
    try:
        _topic_info = classify_topic_with_keywords_caching(question, lang)
        classified_topic = _topic_info.get("topic", "khác")
    except Exception:
        classified_topic = "khác"
        
    if not question or not con_id:
        return jsonify(api_response(ErrorCode.BAD_REQUEST, "Missing 'question' or 'con_id'")), 400
        
    session = ConversationSession.query.filter_by(id=con_id, email=email, is_active=True).first()
    if not session:
        return jsonify(api_response(ErrorCode.BAD_REQUEST, "Invalid or inactive session")), 400

    try:
        usage = TokenUsage.query.filter_by(user_id=user_id, date=today).first()
        used = usage.tokens_used if usage else 0
        prompt_tokens = count_tokens(question)
        
        system_settings = get_global_config("system_settings") or {}
        max_tokens_per_day = system_settings.get("max_tokens_per_day")
        
        if used + prompt_tokens > int(max_tokens_per_day):
            return jsonify(api_response(ErrorCode.FORBIDDEN, "Bạn đã vượt quá giới hạn token sử dụng trong ngày.", {
                "token_limit": int(max_tokens_per_day),
                "tokens_used": used,
                "tokens_requested": prompt_tokens,
                "remaining_tokens": max(0, int(max_tokens_per_day) - used)
            })), 403
    except Exception as e:
        print(f"[WARNING] Failed to check token limit in stream: {e}")
        
    logs = (ConversationLog.query
        .filter(ConversationLog.con_id == con_id)
        .order_by(ConversationLog.timestamp.asc())
        .limit(3).all())
    chat_history = []
    for log in logs:
        chat_history += [{"role": "user", "content": log.question},
                        {"role": "assistant", "content": log.answer}]
    
    try:
        effective_config = get_effective_config(user_id)
        retrieve_k = effective_config.get("retrieve_k", 5)
        rerank_k = effective_config.get("rerank_k", 3)
        enable_rerank = effective_config.get("enable_rerank", True)
        model = effective_config.get("model", "gpt-4o-mini")
    except Exception as e:
        print(f"[WARNING] Failed to get effective config in stream: {e}")
        retrieve_k = 5
        rerank_k = 3
        enable_rerank = True
        model = "gpt-4o-mini"

    def generate():
        try:
            print(f"[DEBUG] Starting streaming request for question: {question}")
            
            orchestration = get_response_from_multiple_sources(
                question=question,
                retrieve_k=retrieve_k,
                rerank_k=rerank_k,
                enable_rerank=enable_rerank,
                model=model,
                chat_history=chat_history,
                stream=True
            )
            
            if isinstance(orchestration, dict):
                references = orchestration.get("references", []) or []
                delta_gen = orchestration.get("generator") or orchestration.get("llm_stream")
                result_container = orchestration.get("_result_container")
                if delta_gen is None:
                    full_text = orchestration.get("response") or ""
                    if full_text and full_text.strip():
                        full_text = convert_html_links_to_markdown(full_text)
                        for chunk in stream_response_chunks(full_text):
                            yield sse_event("delta", chunk)
                    delta_gen = []
            else:
                delta_gen = orchestration
                references = []
                result_container = None
            
            raw_collector = ""
            content_streamed = False
            
            for delta in delta_gen:
                if delta and delta.strip():
                    clean_delta = delta.strip()
                    print(f"[DEBUG] Streaming delta: {repr(clean_delta[:50])}")
                    
                    formatted_delta = convert_html_links_to_markdown(clean_delta)
                    
                    yield f"event: delta\ndata: {formatted_delta}\n\n"
                    raw_collector += formatted_delta
                    content_streamed = True
                    
            final_references = references
             
            if result_container and hasattr(result_container, 'references') and result_container.references:
                final_references = result_container.references
                
                if content_streamed and final_references:
                    ref_content = "\n\n**Tài liệu tham khảo:**\n"
                    for i, ref in enumerate(final_references, 1):
                        file_name = ref.get('file_name', 'Unknown').replace('.pdf', '').replace('.docx', '').replace('.txt', '')
                        file_url = ref.get('file_url', '')
                        
                        if file_url:
                            ref_content += f"{i}. [{file_name}]({file_url})\n"
                        else:
                            ref_content += f"{i}. {file_name}\n"
                    
                    formatted_ref_content = convert_html_links_to_markdown(ref_content)
                    yield sse_event("delta", {"content": formatted_ref_content})
                    
                    print(f"[DEBUG] Reference SSE event yielded successfully")
                    
                    raw_collector += formatted_ref_content
                    print(f"[DEBUG] Added references to raw_collector, total length: {len(raw_collector)}")
            else:
                print(f"[DEBUG] No references found to stream")
            
            yield f"event: done\ndata: \n\n"
            
            try:
                final_answer = convert_html_links_to_markdown(raw_collector)
                response_tokens = count_tokens(final_answer)
                total_tokens = prompt_tokens + response_tokens
                
                if usage:
                    usage.tokens_used += total_tokens
                else:
                    db.session.add(TokenUsage(user_id=user_id, date=today, tokens_used=total_tokens))
                
                session.last_asked_at = now
                
                db.session.add(ConversationLog(
                    con_id=con_id,
                    user_id=user_id,
                    email=email,
                    question=question,
                    answer=final_answer,
                    topic=classified_topic,
                    timestamp=now
                ))
                db.session.commit()
            except Exception as e:
                print(f"[WARNING] Failed to save stream data: {e}")
                
        except Exception as e:
            error_msg = f"Đã xảy ra lỗi khi xử lý yêu cầu: {str(e)}"
            print(f"[ERROR] Stream error: {error_msg}")
            yield f"event: error\ndata: {error_msg}\n\n"

    return sse_response(generate())


@user_bp.route("/ask/stream/stop", methods=["POST"])
@require_session
@require_member_or_admin
def stop_stream():
    """
    Dừng stream đang chạy cho conversation cụ thể
    ---
    tags:
      - User
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            con_id:
              type: string
              description: ID của conversation cần dừng stream
    responses:
      200:
        description: Stream đã được dừng thành công
      400:
        description: Thiếu thông tin hoặc session không hợp lệ
      404:
        description: Không tìm thấy stream để dừng
    """
    if request.method == 'OPTIONS':
        response = make_response()
        response.headers['Access-Control-Allow-Origin'] = request.headers.get('Origin', '*')
        response.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        return response
        
    data = request.json
    con_id = data.get("con_id")
    user_id = g.user.get("user_id") or g.user.get("id")
    email = g.user.get("email")

    if not con_id:
      email = g.user.get("email")

    if not con_id:
        return jsonify(api_response(ErrorCode.BAD_REQUEST, "Missing 'con_id'")), 400

    session = ConversationSession.query.filter_by(id=con_id, email=email, is_active=True).first()
    if not session:
        return jsonify(api_response(ErrorCode.BAD_REQUEST, "Invalid or inactive session")), 400

    stream_key = f"{user_id}_{con_id}"
    
    with stream_cancellation_lock:
        if stream_key in stream_cancellation_flags:
            stream_cancellation_flags[stream_key] = True
            return jsonify(api_response(ErrorCode.SUCCESS, "Stream stop signal sent successfully")), 200
        else:
            return jsonify(api_response(ErrorCode.NOT_FOUND, "No active stream found for this conversation")), 404

@user_bp.route("/download-email", methods=["GET"])
def download_email_template():
    """
    Download email template as .txt file
    ---
    tags:
      - User
    parameters:
      - name: user_id
        in: query
        type: string
        required: false
        description: ID của user (để lấy cached email)
      - name: full_name
        in: query
        type: string
        required: false
        description: Tên đầy đủ của user
      - name: team
        in: query
        type: string
        required: false
        description: Tên team của user
      - name: leave_type
        in: query
        type: string
        required: false
        description: Loại email (leave, ot, remote, quit)
      - name: start_date
        in: query
        type: string
        required: false
        description: Ngày bắt đầu (dd/mm)
      - name: end_date
        in: query
        type: string
        required: false
        description: Ngày kết thúc (dd/mm)
      - name: reason
        in: query
        type: string
        required: false
        description: Lý do
    responses:
      200:
        description: Download thành công
      404:
        description: Không có email template
    """
    try:
        print(f"[DEBUG] Starting download email template...")
        
        # Lấy thông tin từ query params thay vì g.user
        user_id = request.args.get("user_id")
        full_name = request.args.get("full_name", "[TÊN CỦA BẠN]")
        team = request.args.get("team", "[TÊN TEAM]")
        
        print(f"[DEBUG] Params - user_id: {user_id}, full_name: {full_name}, team: {team}")
        
        from utils.user.email_utils import get_email_content_cache, get_hard_coded_email_template
        
        # Nếu có user_id thì lấy từ cache, không thì tạo mới
        email_content = None
        if user_id:
            email_content = get_email_content_cache(user_id)
            print(f"[DEBUG] Email content from cache: {email_content[:100] if email_content else 'None'}")
        
        if not email_content:
            print(f"[DEBUG] No cached email, generating template...")
            leave_type = request.args.get("leave_type", "leave")
            start_date = request.args.get("start_date")
            end_date = request.args.get("end_date")
            reason = request.args.get("reason", "[Lý do]")
            
            # Lấy thông tin từ database nếu có user_id
            if user_id:
                try:
                    from models.models_db import Users
                    user = Users.query.filter_by(user_id=user_id).first()
                    if user:
                        full_name = user.full_name or "[TÊN CỦA BẠN]"
                        team = getattr(user, 'team', None) or "[TÊN TEAM]"
                        print(f"[DEBUG] User from DB - full_name: {full_name}, team: {team}")
                except Exception as db_error:
                    print(f"[DEBUG] Could not get user from DB: {db_error}")
            
            print(f"[DEBUG] Template params: leave_type={leave_type}, start_date={start_date}, end_date={end_date}, reason={reason}, full_name={full_name}, team={team}")
            
            email_content = get_hard_coded_email_template(
                leave_type, start_date, end_date, reason, full_name, team
            )
            
            print(f"[DEBUG] Generated email content: {email_content[:100] if email_content else 'None'}")
        
        if not email_content or email_content == "Email template không tồn tại cho loại này.":
            print(f"[DEBUG] Email content is empty or invalid: {email_content}")
            return jsonify(api_response(ErrorCode.NOT_FOUND, "Không có email template để download")), 404
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        user_name = full_name.replace(" ", "_") if full_name and not full_name.startswith("[") else "user"
        filename = f"email_template_{user_name}_{timestamp}.txt"
        
        print(f"[DEBUG] Creating response with filename: {filename}")
        print(f"[DEBUG] Email content length: {len(email_content)}")
        
        # Tạo response với content type text/plain
        response = Response(
            email_content,
            mimetype='text/plain',
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Content-Type': 'text/plain; charset=utf-8'
            }
        )
        
        print(f"[DEBUG] Response created successfully")
        return response
        
    except Exception as e:
        print(f"[ERROR] Exception in download_email_template: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify(api_response(ErrorCode.SERVER_ERROR, f"Không thể download email template: {str(e)}")), 500

@user_bp.route("/email-template", methods=["POST"])
@require_session
def create_email_template():
    """
    Create email template with provided information
    ---
    tags:
      - User
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            leave_type:
              type: string
              description: Loại email (leave, ot, remote, quit)
            start_date:
              type: string
              description: Ngày bắt đầu (dd/mm)
            end_date:
              type: string
              description: Ngày kết thúc (dd/mm)
            reason:
              type: string
              description: Lý do
            full_name:
              type: string
              description: Tên đầy đủ
            team:
              type: string
              description: Team
          required: ["leave_type"]
    responses:
      200:
        description: Tạo template thành công
      400:
        description: Dữ liệu không hợp lệ
      401:
        description: Unauthorized
    """
    try:
        data = request.get_json()
        user_id = g.user.get("user_id") or g.user.get("id")
        
        leave_type = data.get("leave_type")
        if not leave_type:
            return jsonify(api_response(ErrorCode.BAD_REQUEST, "leave_type là bắt buộc")), 400
        
        start_date = data.get("start_date")
        end_date = data.get("end_date")
        reason = data.get("reason", "[Lý do]")
        full_name = data.get("full_name")
        team = data.get("team")
        
        from utils.user.email_utils import get_hard_coded_email_template, set_email_content_cache
        
        email_content = get_hard_coded_email_template(
            leave_type, start_date, end_date, reason, full_name, team
        )
        
        if email_content == "Email template không tồn tại cho loại này.":
            return jsonify(api_response(ErrorCode.BAD_REQUEST, "Loại email không hợp lệ")), 400
        
        set_email_content_cache(user_id, email_content)
        
        return jsonify(api_response(ErrorCode.SUCCESS, "Email template được tạo thành công", {
            "email_content": email_content,
            "download_available": True
        })), 200
        
    except Exception as e:
        return jsonify(api_response(ErrorCode.INTERNAL_SERVER_ERROR, f"Không thể tạo email template: {str(e)}")), 500

@user_bp.route("/email-templates", methods=["GET"])
@require_session
def get_available_email_templates():
    """
    Get list of available email templates
    ---
    tags:
      - User
    responses:
      200:
        description: Lấy danh sách template thành công
      401:
        description: Unauthorized
    """
    try:
        templates = [
            {
                "type": "leave",
                "name": "Nghỉ phép",
                "description": "Template cho đơn xin nghỉ phép thông thường"
            },
            {
                "type": "ot",
                "name": "Làm thêm giờ",
                "description": "Template cho đơn xin làm thêm giờ (overtime)"
            },
            {
                "type": "remote",
                "name": "Làm việc từ xa",
                "description": "Template cho đơn xin làm việc từ xa (remote work)"
            },
            {
                "type": "quit",
                "name": "Nghỉ việc",
                "description": "Template cho đơn xin nghỉ việc (resignation)"
            }
        ]
        
        return jsonify(api_response(ErrorCode.SUCCESS, "Danh sách email templates", {
            "templates": templates
        })), 200
        
    except Exception as e:
        return jsonify(api_response(ErrorCode.INTERNAL_SERVER_ERROR, f"Không thể lấy danh sách templates: {str(e)}")), 500

@user_bp.route("/test-email-flow", methods=["POST"])
@require_session
def test_email_flow():
    """
    Test email flow với thông tin user từ token
    ---
    tags:
      - User
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            question:
              type: string
              description: Câu hỏi về email
          required: ["question"]
    responses:
      200:
        description: Test thành công
      400:
        description: Dữ liệu không hợp lệ
      401:
        description: Unauthorized
    """
    try:
        data = request.get_json()
        question = data.get("question", "").strip()
        user_id = g.user.get("user_id") or g.user.get("id")
        
        if not question:
            return jsonify(api_response(ErrorCode.BAD_REQUEST, "Question là bắt buộc")), 400
        
        from utils.user.email_utils import smart_email_processor, get_email_content_cache
        
        response = smart_email_processor(question, user_id, "vi")
        
        cached_email = get_email_content_cache(user_id)
        
        user_info = {
            "user_id": user_id,
            "full_name": g.user.get("full_name") or g.user.get("name"),
            "email": g.user.get("email"),
            "team": g.user.get("team", "Not specified")
        }
        
        return jsonify(api_response(ErrorCode.SUCCESS, "Email flow test completed", {
            "user_info": user_info,
            "question": question,
            "response": response,
            "email_cached": cached_email is not None,
            "download_available": "/api/user/download-email" in response
        })), 200
        
    except Exception as e:
        return jsonify(api_response(ErrorCode.INTERNAL_SERVER_ERROR, f"Test failed: {str(e)}")), 500
@user_bp.route("/conversation_logs/<int:log_id>/update_answer", methods=["PUT"])
@require_session
@require_member_or_admin
def update_answer(log_id):
    try:
        data = request.get_json()
        raw_answer = data.get("answer", "").strip()

        if not raw_answer:
            return jsonify(api_response(ErrorCode.BAD_REQUEST, "Answer cannot be empty")), 400

        log = ConversationLog.query.get(log_id)
        if not log:
            return jsonify(api_response(ErrorCode.NOT_FOUND, "Conversation log not found")), 404

        log.answer = raw_answer
        log.updated_at = datetime.now()

        db.session.commit()

        return jsonify(api_response(ErrorCode.SUCCESS, "Answer updated successfully")), 200

    except Exception as e:
        return jsonify(api_response(ErrorCode.INTERNAL_SERVER_ERROR, f"Error: {str(e)}")), 500
    
@user_bp.route("/ask/token-usage", methods=["POST"])
@require_session
@require_member_or_admin
def get_token_usage():
    """
    Tính số token sử dụng cho câu hỏi
    ---
    tags:
      - User
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            question:
              type: string
    responses:
      200:
        description: Thành công
      400:
        description: Dữ liệu không hợp lệ
      500:
        description: Lỗi server
    """
    data = request.json
    question = data.get("question", "").strip()
    user_id = g.user.get("user_id") or g.user.get("id")

    if not question:
        return jsonify(api_response(ErrorCode.BAD_REQUEST, "Thiếu câu hỏi")), 400

    try:
        prompt_tokens = count_tokens(question)
        today = date.today()
        usage = TokenUsage.query.filter_by(user_id=user_id, date=today).first()
        used = usage.tokens_used if usage else 0

        system_settings = get_global_config("system_settings") or {}
        max_tokens_per_day = system_settings.get("max_tokens_per_day")
        if max_tokens_per_day is None:
            max_tokens_per_day = 30000
            print(f"[WARNING] Token limit not configured in Admin settings, using default: {max_tokens_per_day}")

        return jsonify(api_response(ErrorCode.SUCCESS, "Thành công", {
            "question_tokens": prompt_tokens,
            "used_tokens_today": used,
            "remaining_tokens": max(0, int(max_tokens_per_day) - used),
        })), 200

    except Exception as e:
        return jsonify(api_response(ErrorCode.SERVER_ERROR, str(e))), 500

@user_bp.route("/chat-history", methods=["GET"])
@require_session
@require_member_or_admin
def get_chat_history_by_conversation():
    """
    Lấy lịch sử chat theo session
    ---
    tags:
      - User
    parameters:
      - name: con_id
        in: query
        type: string
        required: true
        description: ID của session
      - name: page
        in: query
        type: integer
        required: false
      - name: limit
        in: query
        type: integer
        required: false
    responses:
      200:
        description: Lấy lịch sử chat thành công
      400:
        description: Thiếu con_id
      500:
        description: Lỗi server
    """
    con_id = request.args.get("con_id")
    page = int(request.args.get("page", 1))
    limit = int(request.args.get("limit", 10))
    email = g.user["email"]

    if not con_id:
        return jsonify(api_response(ErrorCode.BAD_REQUEST, "Missing 'con_id'")), 400

    try:
        query = db.session.query(
            ConversationLog.question,
            ConversationLog.answer,
            ConversationLog.timestamp
        ).filter(
            ConversationLog.email == email,
            ConversationLog.con_id == con_id
        ).order_by(ConversationLog.timestamp.desc())

        total_count = query.count()
        total_pages = (total_count + limit - 1) // limit
        has_next_page = page < total_pages

        results = query.offset((page - 1) * limit).limit(limit).all()

        items = [
            {
                "question": row.question,
                "answer": row.answer
            }
            for row in results
        ]

        return jsonify(api_response(ErrorCode.SUCCESS, "Chat history retrieved", {
            "items": items,
            "metadata": {
                "page": page,
                "limit": limit,
                "totalPages": total_pages,
                "totalCount": total_count,
                "hasNextPage": has_next_page
            }
        })), 200

    except Exception as e:
        return jsonify(api_response(ErrorCode.SERVER_ERROR, ErrorCode.get_message(ErrorCode.SERVER_ERROR), {
            "error": str(e)
        })), 500

@user_bp.route("/conversations", methods=["GET"])
@require_session
@require_member_or_admin
def get_conversations_by_user():
    """
    Lấy danh sách các cuộc hội thoại của user
    ---
    tags:
      - User
    parameters:
      - name: lang
        in: query
        type: string
        required: false
        description: Ngôn ngữ cho summary (mặc định: en)
      - name: limit
        in: query
        type: integer
        required: false
        description: Giới hạn số lượng conversations (mặc định: 25)
    responses:
      200:
        description: Lấy danh sách thành công
      500:
        description: Lỗi server
    """
    user_id = g.user.get("user_id")
    email = g.user.get("email")
    lang = request.args.get("lang", "en")
    limit = request.args.get("limit", "25")

    if not user_id:
        return jsonify(message_response(ErrorCode.BAD_REQUEST, "Missing user_id"), {
            "error": str(e)
        }), 400
    try:
        query = db.session.query(ConversationSession.id).filter(
            (ConversationSession.user_id == user_id) | (ConversationSession.email == email)
        ).order_by(ConversationSession.started_at.desc())
        
        try:
            limit_int = int(limit)
            if limit_int > 0:
                query = query.limit(limit_int)
            else:
                query = query.limit(25)
        except ValueError:
            query = query.limit(25)
        
        sessions = query.all()

        result = []
        for s in sessions:
            con_id = s.id

            latest_log = db.session.query(ConversationLog).filter_by(con_id=con_id)\
                            .order_by(ConversationLog.timestamp.desc()).first()
            question = latest_log.question if latest_log else ""

            summary = generate_summary_from_question_auto_lang(question, start=2)

            result.append({
                "con_id": con_id,
                "summary": summary
            })
        
        message = f"Retrieved {len(result)} conversation summaries (limited to {limit})"
            
        return jsonify(api_response(ErrorCode.SUCCESS, message, result)), 200

    except Exception as e:
        return jsonify(api_response(ErrorCode.SERVER_ERROR, ErrorCode.get_message(ErrorCode.SERVER_ERROR), {
            "error": str(e)
        })), 500


@user_bp.route("/conversations/<string:con_id>", methods=["DELETE"])
@require_session
@require_member_or_admin
def delete_conversation(con_id):
    """
    Xóa một cuộc hội thoại theo con_id
    ---
    tags:
      - User
    parameters:
      - name: con_id
        in: path
        type: string
        required: true
        description: ID của cuộc hội thoại
    responses:
      200:
        description: Xóa thành công
      404:
        description: Không tìm thấy session
      500:
        description: Lỗi server
    """
    user_id = g.user.get("id") or g.user.get("user_id")
    email = g.user.get("email")

    try:
        session = ConversationSession.query.filter(
            ConversationSession.id == con_id,
            ((ConversationSession.user_id == user_id) | (ConversationSession.email == email))
        ).first()

        if not session:
            return jsonify(message_response(ErrorCode.NOT_FOUND, "Conversation session not found")), 404

        db.session.delete(session)
        db.session.commit()

        return jsonify(message_response(ErrorCode.SUCCESS, "Conversation deleted successfully")), 200

    except Exception as e:
        db.session.rollback()
        return jsonify(message_response(ErrorCode.SERVER_ERROR, ErrorCode.get_message(ErrorCode.SERVER_ERROR), {
            "error": str(e)
        })), 500

@user_bp.route('/search-chat', methods=['GET'])
@require_session
@require_member_or_admin
def search_chat_by_summary():
    query = request.args.get('query', '').strip().lower()
    email = request.args.get('email', '').strip()
    page = int(request.args.get('page', 1))
    limit = int(request.args.get('limit', 20))
    offset = (page - 1) * limit

    try:
        session_query = ConversationSession.query
        if email:
            session_query = session_query.filter(ConversationSession.email == email)

        session_query = session_query.order_by(ConversationSession.started_at.desc()).limit(200)
        sessions = session_query.all()
        session_ids = [s.id for s in sessions]

        sub_latest_log = db.session.query(
            ConversationLog.con_id,
            func.max(ConversationLog.timestamp).label("max_time")
        ).filter(ConversationLog.con_id.in_(session_ids))\
         .group_by(ConversationLog.con_id)\
         .subquery()

        latest_logs = db.session.query(ConversationLog)\
            .join(sub_latest_log,
                  (ConversationLog.con_id == sub_latest_log.c.con_id) &
                  (ConversationLog.timestamp == sub_latest_log.c.max_time))\
            .all()

        logs_by_con_id = {log.con_id: log for log in latest_logs}

        matched_results = []
        for s in sessions:
            latest_log = logs_by_con_id.get(s.id)
            if not latest_log:
                continue

            question = latest_log.question.strip()
            summary = generate_summary_from_question_auto_lang(question, start=2)

            if query in summary.lower():
                matched_results.append({
                    "con_id": s.id,
                    "summary": summary,
                    "latest_question": question
                })

        total = len(matched_results)
        paged_results = matched_results[offset:offset + limit]

        return jsonify({
            "total": total,
            "page": page,
            "limit": limit,
            "results": paged_results
        }), 200

    except Exception as e:
        return jsonify({
            "error": "Lỗi server",
            "details": str(e)
        }), 500

    
@user_bp.route("/ask/form-config", methods=["GET"])
@require_session
@require_member_or_admin
def get_ask_form_config():
    try:
        user_id = g.user.get("user_id") or g.user.get("id")

        effective_config = get_effective_config(user_id)

        return jsonify(api_response(ErrorCode.SUCCESS, "OK", effective_config)), 200

    except Exception as e:
        return jsonify(api_response(ErrorCode.SERVER_ERROR, "Không thể lấy config", {
            "error": str(e)
        })), 500

@user_bp.route("/file/<string:file_id>", methods=["GET"])
@require_session
@require_member_or_admin
def get_file_info(file_id):
    """
    Lấy thông tin file document theo ID
    ---
    tags:
      - User
    parameters:
      - name: file_id
        in: path
        required: true
        type: string
        description: ID của file document
    responses:
      200:
        description: Lấy thông tin file thành công
      404:
        description: File không tồn tại
      401:
        description: Unauthorized
    """
    file_info = get_file_info_by_id(file_id)
    if file_info:
        return jsonify(api_response(ErrorCode.SUCCESS, "File info retrieved successfully", file_info)), 200
    else:
        return jsonify(api_response(ErrorCode.NOT_FOUND, "File not found")), 404

@user_bp.route("/file/<string:file_id>/download", methods=["GET"])
@require_session
@require_member_or_admin
def download_file(file_id):
    """
    Download file document theo ID
    ---
    tags:
      - User
    parameters:
      - name: file_id
        in: path
        required: true
        type: string
        description: ID của file document
    responses:
      200:
        description: Download file thành công
      404:
        description: File không tồn tại
      401:
        description: Unauthorized
    """
    file_info = get_file_info_by_id(file_id)
    if not file_info:
        return jsonify(api_response(ErrorCode.NOT_FOUND, "File not found")), 404
    
    try:
        from utils.admin.upload_s3_utils import download_pdf_from_s3
        file_content = download_pdf_from_s3(file_info['file_url'])
        
        from flask import send_file
        import io
        
        file_obj = io.BytesIO(file_content)
        file_obj.seek(0)
        
        return send_file(
            file_obj,
            as_attachment=True,
            download_name=file_info['file_name'],
            mimetype=file_info['content_type']
        )
        
    except Exception as e:
        return jsonify(api_response(ErrorCode.SERVER_ERROR, "Không thể download file", {
            "error": str(e)
        })), 500

@user_bp.route("/file/<string:file_id>/preview", methods=["GET"])
@require_session
@require_member_or_admin
def preview_file(file_id):
    """
    Preview file document theo ID (chỉ hỗ trợ PDF và text)
    ---
    tags:
      - User
    parameters:
      - name: file_id
        in: path
        required: true
        type: string
        description: ID của file document
    responses:
      200:
        description: Preview file thành công
      404:
        description: File không tồn tại
      400:
        description: File type không được hỗ trợ
      401:
        description: Unauthorized
    """
    file_info = get_file_info_by_id(file_id)
    if not file_info:
        return jsonify(api_response(ErrorCode.NOT_FOUND, "File not found")), 404
    
    supported_types = ['application/pdf', 'text/plain', 'text/html']
    if file_info['content_type'] not in supported_types:
        return jsonify(api_response(ErrorCode.BAD_REQUEST, "File type không được hỗ trợ cho preview")), 400
    
    try:
        from utils.admin.upload_s3_utils import download_pdf_from_s3
        file_content = download_pdf_from_s3(file_info['file_url'])
        
        if file_info['content_type'] == 'application/pdf':
            from flask import Response
            return Response(file_content, mimetype='application/pdf')
        else:
            text_content = file_content.decode('utf-8', errors='ignore')
            return jsonify(api_response(ErrorCode.SUCCESS, "File preview retrieved successfully", {
                "content": text_content,
                "file_name": file_info['file_name'],
                "content_type": file_info['content_type']
            })), 200
        
    except Exception as e:
        return jsonify(api_response(ErrorCode.SERVER_ERROR, "Không thể preview file", {
            "error": str(e)
        })), 500

@user_bp.route("/conversation-status", methods=["GET"])
@require_session
@require_member_or_admin
def get_conversation_status():
    """
    Lấy trạng thái conversation để debug
    """
    try:
        user_id = g.user.get("user_id") or g.user.get("id")
        from utils.user.email_utils import get_conversation_state, is_in_leave_email
        
        conversation_state = get_conversation_state(user_id)
        is_in_email = is_in_leave_email(user_id)
        
        status = {
            "is_in_email_conversation": is_in_email,
            "conversation_state": conversation_state
        }
        
        return jsonify(api_response(ErrorCode.SUCCESS, "Conversation status retrieved", status)), 200
    except Exception as e:
        return jsonify(api_response(ErrorCode.INTERNAL_SERVER_ERROR, f"Failed to get conversation status: {str(e)}")), 500

@user_bp.route("/clear-conversation", methods=["POST"])
@require_session
@require_member_or_admin
def clear_conversation():
    """
    Clear conversation state cho user
    """
    try:
        user_id = g.user.get("user_id") or g.user.get("id")
        from utils.user.email_utils import clear_conversation_state
        
        clear_conversation_state(user_id)
        
        return jsonify(api_response(ErrorCode.SUCCESS, "Conversation cleared successfully")), 200
    except Exception as e:
        return jsonify(api_response(ErrorCode.INTERNAL_SERVER_ERROR, f"Failed to clear conversation: {str(e)}")), 500

@user_bp.route("/force-clear-conversation", methods=["POST"])
@require_session
@require_member_or_admin
def force_clear_conversation():
    """
    Force clear conversation state cho user
    """
    try:
        user_id = g.user.get("user_id") or g.user.get("id")
        from utils.user.email_utils import clear_conversation_state, clear_all_caches
        
        clear_conversation_state(user_id)
        clear_all_caches()
        
        return jsonify(api_response(ErrorCode.SUCCESS, "All conversation states and caches cleared successfully")), 200
    except Exception as e:
        return jsonify(api_response(ErrorCode.INTERNAL_SERVER_ERROR, f"Failed to clear conversation: {str(e)}")), 500
