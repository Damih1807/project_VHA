from langdetect import detect
from langdetect.lang_detect_exception import LangDetectException
from typing import Dict, Any, List

def detect_language(text: str) -> str:
    """Detect language of text"""
    try:
        lang = detect(text)
        if lang == "vi":
            return "vi"
        return "en"
    except LangDetectException:
        return "vi"

def should_use_hr_training_data(question_analysis: Dict[str, Any]) -> bool:
    """Kiểm tra xem có nên sử dụng HR training data không"""
    return (
        question_analysis['question_type'] == 'hr_question' and
        question_analysis['confidence'] > 0.6
    )

def should_skip_chitchat(question_analysis: Dict[str, Any]) -> bool:
    """Kiểm tra xem có nên skip chitchat không"""
    return question_analysis['question_type'] == 'hr_question'

def enhance_question_with_llm_analysis(question: str, question_analysis: Dict[str, Any]) -> str:
    """Tăng cường câu hỏi dựa trên LLM analysis"""
    processed_question = question_analysis.get('processed_question', question)
    keywords = question_analysis.get('keywords', [])
    
    if keywords:
        enhanced = f"{processed_question} {' '.join(keywords)}"
        return enhanced
    
    return processed_question

def unified_classification(question: str, lang: str = "vi", enhanced_response_func=None) -> Dict[str, Any]:
    """
    Thống nhất classification logic giữa LLM và FAISS
    Returns: {
        'question_type': str,
        'confidence': float,
        'response': str,
        'method': str,
        'keywords': list,
        'intent': str
    }
    """
    try:
        from .llm_services import process_question_with_llm
        
        llm_analysis = process_question_with_llm(question, lang)
        print(f"[INFO] LLM classification: {llm_analysis}")
        
        if enhanced_response_func:
            from utils.aws_client import bedrock_embeddings
            faiss_response, faiss_type, faiss_confidence = enhanced_response_func(question, bedrock_embeddings)
            print(f"[INFO] FAISS classification: {faiss_type}, confidence: {faiss_confidence}")
        else:
            faiss_response, faiss_type, faiss_confidence = "", "general", 0.0
        
        if llm_analysis['confidence'] >= 0.7:
            return {
                'question_type': llm_analysis['question_type'],
                'confidence': llm_analysis['confidence'],
                'response': '',
                'method': 'llm',
                'keywords': llm_analysis.get('keywords', []),
                'intent': llm_analysis.get('intent', 'unknown')
            }
        elif faiss_confidence >= 0.6 and faiss_response:
            return {
                'question_type': faiss_type,
                'confidence': faiss_confidence,
                'response': faiss_response,
                'method': 'faiss',
                'keywords': [],
                'intent': 'predefined'
            }
        elif llm_analysis['confidence'] >= 0.5:
            return {
                'question_type': llm_analysis['question_type'],
                'confidence': llm_analysis['confidence'],
                'response': '',
                'method': 'llm',
                'keywords': llm_analysis.get('keywords', []),
                'intent': llm_analysis.get('intent', 'unknown')
            }
        else:
            return {
                'question_type': 'general',
                'confidence': 0.4,
                'response': '',
                'method': 'fallback',
                'keywords': [],
                'intent': 'unknown'
            }
            
    except Exception as e:
        print(f"[ERROR] Unified classification failed: {e}")
        return {
            'question_type': 'general',
            'confidence': 0.0,
            'response': '',
            'method': 'error',
            'keywords': [],
            'intent': 'unknown'
        } 