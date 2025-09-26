from typing import List, Dict, Any

HR_KEYWORDS = [
    "lương", "thưởng", "phúc lợi", "lương cơ bản", "thưởng tháng 13", "phụ cấp", "kpi", "bonus", "overtime", "tăng lương",
    
    "phép năm", "nghỉ phép", "leave", "policy", "carry over", "nghỉ thai sản", "thai sản", "maternity leave", 
    "nghỉ ốm", "nghỉ bệnh", "ốm đau", "nghỉ không lương", "nghỉ cưới", "nghỉ tang", "nghỉ khám thai", 
    "nghỉ con ốm", "nghỉ dưỡng sức", "nghỉ lễ", "nghỉ tết", "nghỉ phép đặc biệt", "ngày nghỉ", "ngày lễ",
    "special leave", "sick leave", "unpaid leave", "marriage leave", "funeral leave", "pregnancy checkup leave",
    "child sick leave", "convalescence leave", "holiday", "public holiday", "annual leave",
    
    "nghỉ việc", "thôi việc", "từ chức", "chấm dứt hợp đồng", "resignation", "termination", "quit job", "layoff",
    
    "bảo hiểm", "bảo hiểm xã hội", "bảo hiểm y tế", "bảo hiểm thất nghiệp", "bhxh", "bhyt", "insurance", 
    "social insurance", "health insurance", "unemployment insurance",
    
    "hợp đồng", "thử việc", "chính thức", "chấm dứt", "contract", "hợp đồng lao động", "tăng ca", "làm thêm giờ",
    
    "văn hóa", "môi trường", "đồng nghiệp", "quản lý", "giao tiếp", "teamwork", "xung đột",
    
    "đào tạo", "training", "certification", "mentoring", "career path", "workshop", "e-learning", "elearning", "online learning", "platform", "học tập",
    
    "văn phòng", "canteen", "phòng họp", "parking", "gym", "internet", "máy tính", "địa chỉ", "address", "location",
    
    "chính sách", "quy định", "nội bộ", "thủ tục", "quy trình", "bảo mật", "remote work", "dress code",
    
    "it support", "hr support", "eap", "health check", "mental health", "emergency contact"
]

KEYWORDS = HR_KEYWORDS + [
    "chế độ", "chính sách", "quy định", "thủ tục", "hướng dẫn", "quy trình", "trợ cấp", "compensation"
]

def is_hr_related_question(question: str) -> bool:
    """Kiểm tra xem câu hỏi có liên quan đến HR không"""
    question_lower = question.lower()
    return any(kw in question_lower for kw in HR_KEYWORDS)

def check_keywords_in_docs(docs) -> bool:
    """Kiểm tra xem có keywords trong documents không"""
    context = " ".join([doc.page_content.lower() for doc in docs if doc.page_content])
    return any(kw in context for kw in KEYWORDS)

def enhance_question_for_search(question: str) -> str:
    """Tăng cường câu hỏi để tìm kiếm chính xác hơn"""
    question_lower = question.lower()
    
    if "nghỉ việc" in question_lower and "nghỉ phép" not in question_lower:
        enhanced = question + " thôi việc từ chức chấm dứt hợp đồng"
    elif "e-learning" in question_lower or "elearning" in question_lower:
        enhanced = question + " đào tạo online platform học tập"
    elif "địa chỉ" in question_lower or "address" in question_lower:
        enhanced = question + " văn phòng location địa điểm"
    elif "trợ cấp" in question_lower:
        enhanced = question + " compensation benefit phúc lợi"
    elif "ngày lễ" in question_lower or "ngày nghỉ" in question_lower:
        enhanced = question + " holiday public holiday nghỉ lễ"
    else:
        enhanced = question
    
    return enhanced

def lightweight_context_analysis(question: str, conversation_history: List[str] = None) -> Dict[str, Any]:
    """
    Lightweight context analysis cho performance
    Returns: {
        'entities': list,
        'topics': list,
        'sentiment': str,
        'confidence': float
    }
    """
    try:
        entities = []
        question_lower = question.lower()
        
        hr_entities = ['lương', 'thưởng', 'nghỉ phép', 'bảo hiểm', 'hợp đồng', 'kpi', 'đánh giá']
        for entity in hr_entities:
            if entity in question_lower:
                entities.append(entity)
        
        location_entities = ['việt nam', 'singapore', 'hà nội', 'tp hcm', 'đà nẵng']
        for entity in location_entities:
            if entity in question_lower:
                entities.append(entity)
        
        topics = []
        if any(word in question_lower for word in ['lương', 'thưởng', 'salary', 'bonus']):
            topics.append('salary')
        if any(word in question_lower for word in ['nghỉ', 'phép', 'leave', 'holiday']):
            topics.append('leave')
        if any(word in question_lower for word in ['bảo hiểm', 'insurance']):
            topics.append('insurance')
        if any(word in question_lower for word in ['hợp đồng', 'contract']):
            topics.append('contract')
        if any(word in question_lower for word in ['đào tạo', 'training']):
            topics.append('training')
        
        positive_words = ['tốt', 'hay', 'thích', 'hài lòng', 'tuyệt vời', 'cảm ơn']
        negative_words = ['xấu', 'tệ', 'không thích', 'không hài lòng', 'lỗi', 'vấn đề']
        
        positive_count = sum(1 for word in positive_words if word in question_lower)
        negative_count = sum(1 for word in negative_words if word in question_lower)
        
        if positive_count > negative_count:
            sentiment = 'positive'
        elif negative_count > positive_count:
            sentiment = 'negative'
        else:
            sentiment = 'neutral'
        
        confidence = min(0.9, 0.5 + len(entities) * 0.1 + len(topics) * 0.1)
        
        return {
            'entities': entities,
            'topics': topics,
            'sentiment': sentiment,
            'confidence': confidence
        }
        
    except Exception as e:
        print(f"[ERROR] Lightweight context analysis failed: {e}")
        return {
            'entities': [],
            'topics': [],
            'sentiment': 'neutral',
            'confidence': 0.0
        }

def enhance_question_with_context(question: str, context_analysis: Dict[str, Any], conversation_history: List[str] = None) -> str:
    """Tăng cường câu hỏi với context analysis"""
    enhanced_parts = [question]
    
    if context_analysis.get('entities'):
        enhanced_parts.extend(context_analysis['entities'])
    
    if context_analysis.get('topics'):
        enhanced_parts.extend(context_analysis['topics'])
    
    if conversation_history:
        recent_keywords = []
        for msg in conversation_history[-3:]:
            if isinstance(msg, dict) and msg.get('role') == 'user':
                content = msg.get('content', '').lower()
                for keyword in HR_KEYWORDS[:10]:
                    if keyword in content:
                        recent_keywords.append(keyword)
            elif isinstance(msg, str):
                content = msg.lower()
                for keyword in HR_KEYWORDS[:10]:
                    if keyword in content:
                        recent_keywords.append(keyword)
        
        if recent_keywords:
            enhanced_parts.extend(recent_keywords[:3])
    
    follow_up_indicators = ['chi tiết hơn', 'thêm thông tin', 'cụ thể hơn', 'rõ ràng hơn', 'more details', 'more info']
    if any(indicator in question.lower() for indicator in follow_up_indicators):
        if conversation_history:
            recent_context = []
            for msg in conversation_history[-4:]:
                if isinstance(msg, dict):
                    if msg.get('role') == 'user':
                        recent_context.append(f"User: {msg.get('content', '')}")
                    elif msg.get('role') == 'assistant':
                        recent_context.append(f"Assistant: {msg.get('content', '')}")
                elif isinstance(msg, str):
                    recent_context.append(msg)
            
            if recent_context:
                context_text = ' | '.join(recent_context[-2:])
                enhanced_parts.append(f"Context: {context_text}")
        
        return ' '.join(enhanced_parts)
    
    return ' '.join(enhanced_parts) 