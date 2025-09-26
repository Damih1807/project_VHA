from typing import Dict, Any, List
from urllib.parse import urlsplit, urlunsplit

def notify_no_documents(lang: str) -> str:
    """Return notification for no documents"""
    return "Xin lỗi, tôi không tìm thấy tài liệu liên quan để trả lời câu hỏi của bạn." if lang == "vi" else "Sorry, I couldn't find any relevant documents to answer your question."

def notify_error_loading_vectors(lang: str) -> str:
    """Return notification for vector loading error"""
    return "Lỗi khi tải dữ liệu vector từ S3." if lang == "vi" else "Error loading vector data from S3."

def notify_no_answer_found(lang: str) -> str:
    """Return notification for no answer found"""
    return "Xin lỗi, tôi không thể tìm thấy thông tin phù hợp để trả lời câu hỏi của bạn. Vui lòng thử đặt câu hỏi khác hoặc liên hệ bộ phận hỗ trợ." if lang == "vi" else "Sorry, I couldn't find relevant information to answer your question. Please try asking differently or contact support."

def append_page_fragment(url: str, page: int) -> str:
    """Append page fragment to URL"""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, f"page={page}"))

def validate_response(response: str, lang: str) -> Dict[str, Any]:
    """Validate response and return appropriate result with enhanced detection"""
    if not response or not response.strip():
        no_answer_response = notify_no_answer_found(lang)
        return {
            "response": no_answer_response,
            "references": []
        }
    
    # Enhanced no-answer detection patterns
    no_info_indicators = [
        "không có thông tin",
        "không tìm thấy",
        "tài liệu được cung cấp không có",
        "tài liệu chưa đủ thông tin",
        "vui lòng cho biết",
        "mình cần hỗ trợ",
        "không có câu trả lời",
        "the answer is not available",
        "không thể tìm thấy thông tin",
        "xin lỗi, tôi không",
        "tôi không thể trả lời",
        "không có dữ liệu",
        "thông tin không có",
        "sorry, i cannot",
        "i don't have information",
        "no information available",
        "unable to find",
        "không có tài liệu nào",
        "tài liệu không chứa"
    ]
    
    response_lower = response.lower().strip()
    
    # Check if response is too short (likely generic)
    if len(response_lower) < 50:
        no_answer_response = notify_no_answer_found(lang)
        return {
            "response": no_answer_response,
            "references": []
        }
    
    # Check for no-answer patterns
    if any(indicator in response_lower for indicator in no_info_indicators):
        no_answer_response = notify_no_answer_found(lang)
        return {
            "response": no_answer_response,
            "references": []
        }
    
    # Check if response is mostly generic phrases
    generic_phrases = [
        "dựa trên thông tin",
        "theo tài liệu", 
        "có thể nói rằng",
        "tôi hiểu rằng",
        "based on the information",
        "according to the document"
    ]
    
    # If response only contains generic phrases without substance
    meaningful_content = response_lower
    for phrase in generic_phrases:
        meaningful_content = meaningful_content.replace(phrase, "")
    
    if len(meaningful_content.strip()) < 30:
        no_answer_response = notify_no_answer_found(lang)
        return {
            "response": no_answer_response,
            "references": []
        }
    
    return None

def is_offensive_or_sensitive(text: str) -> bool:
    """Detect offensive, abusive, or sensitive content (VI/EN) with lightweight rules.

    Best-effort heuristic filter; avoid over-blocking by targeting explicit profanity,
    insults, and hate/discriminatory terms.
    """
    if not text:
        return False

    normalized = text.lower().strip()

    # Vietnamese profanity/insults (explicit)
    profanities_vi = [
        'địt', 'đụ','đù','má','móa','mọe', 'lồn', 'cặc', 'buồi', 'chim', 'má mày', 'mẹ mày', 'đm', 'dm', 'vcl', 'vl', 'cc',
        'đồ ngu', 'ngu như', 'óc chó', 'câm mồm', 'khốn nạn', 'mất dạy', 'chó chết', 'đồ rác rưởi','súc vật',
    ]
    hate_vi = [
        'đồ mọi', 'bọn da đen', 'bọn da vàng', 'bọn da trắng', 'đồ đồng tính', 'đồ gay', 'đồ pê đê',
        'bọn việt', 'bọn tàu', 'bọn do thái', 'bọn hồi giáo','bọn nhà nhập khẩu','đồ đồng bóng','đồ đồng tính',
    ]

    # English profanity/insults/hate (subset)
    profanities_en = [
        'fuck', 'shit', 'bitch', 'bastard', 'asshole', 'dick', 'pussy', 'motherfucker', 'fucking',
        'retard', 'stupid', 'idiot', 'moron'
    ]
    hate_en = [
        'nigger', 'chink', 'spic', 'kike', 'fag', 'tranny', 'retarded', 'go back to', 'white trash'
    ]

    keyword_lists = [profanities_vi, hate_vi, profanities_en, hate_en]
    for keywords in keyword_lists:
        if any(k in normalized for k in keywords):
            return True

    return False

def professional_refusal(lang: str) -> str:
    """Return a professional refusal message for offensive/abusive content."""
    if lang == 'vi':
        return (
            "Tôi xin phép từ chối trả lời vì nội dung có chứa yếu tố xúc phạm, nhạy cảm hoặc phân biệt đối xử. "
            "Vui lòng sử dụng ngôn ngữ lịch sự và tôn trọng. Nếu bạn cần hỗ trợ, hãy đặt câu hỏi theo cách phù hợp hơn."
        )
    return (
        "I’m sorry, I must decline to respond because the message contains offensive, sensitive, or discriminatory content. "
        "Please use respectful language. If you still need help, feel free to rephrase your question."
    )

def handle_follow_up_questions(question: str, classification_result: Dict[str, Any]) -> Dict[str, Any]:
    """Handle follow-up questions by forcing general type"""
    follow_up_indicators = ['chi tiết hơn', 'thêm thông tin', 'cụ thể hơn','còn gì nữa không', 'rõ ràng hơn', 'more details', 'more info']
    
    if any(indicator in question.lower() for indicator in follow_up_indicators):
        classification_result['question_type'] = 'general'
        classification_result['method'] = 'follow_up'
        print(f"[INFO] Forced general type for follow-up question")
    
    return classification_result 