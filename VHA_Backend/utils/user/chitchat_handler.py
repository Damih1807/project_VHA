from typing import Dict, Any
from .llm_services import chatgpt_generate
from .enhanced_chitchat_classifier import get_enhanced_response
from utils.aws_client import bedrock_embeddings

def handle_chitchat(question: str, lang: str, t0: float, model: str = "gpt-4o-mini") -> str:
    """Handle chitchat with enhanced response fallback"""
    try:
        response, response_type, confidence = get_enhanced_response(question, bedrock_embeddings)
        
        if response and confidence > 0.6:
            print(f"[INFO] Enhanced response used - Type: {response_type}, Confidence: {confidence:.2f}")
            return response
        
        prompt = f"""
        {"Trả lời câu hỏi sau một cách tự nhiên, ngắn gọn (tối đa 3 câu), thân thiện như đang trò chuyện. Không cần quá trang trọng." if lang == "vi"
            else "Answer the following question in a natural, concise (max 3 sentences), and friendly way as if chatting. No need to be too formal."}
        Câu hỏi: {question}
        """
        response = chatgpt_generate(prompt, model)
        return response
        
    except Exception as e:
        print(f"[ERROR] Enhanced chitchat failed: {e}")
        prompt = f"""
        {"Trả lời câu hỏi sau một cách tự nhiên, ngắn gọn (tối đa 3 câu), thân thiện như đang trò chuyện. Không cần quá trang trọng." if lang == "vi"
            else "Answer the following question in a natural, concise (max 3 sentences), and friendly way as if chatting. No need to be too formal."}
        Câu hỏi: {question}
        """
        response = chatgpt_generate(prompt, model)
        return response

def is_basic_greeting(question: str) -> bool:
    """Check if question is a basic greeting"""
    basic_greetings = ['xin chào', 'hello', 'hi', 'chào', 'chào bạn', 'chào anh', 'chào chị']
    return any(greeting in question.lower() for greeting in basic_greetings)

def should_handle_as_chitchat(classification_result: Dict[str, Any], question: str) -> bool:
    """Determine if question should be handled as chitchat"""
    from .keywords_utils import is_hr_related_question
    from .language_utils import should_skip_chitchat
    
    is_basic_greeting_result = is_basic_greeting(question)
    
    return (
        (classification_result['question_type'] == 'chitchat' and not should_skip_chitchat(classification_result)) or 
        is_basic_greeting_result
    ) and not is_hr_related_question(question) 