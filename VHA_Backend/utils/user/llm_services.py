import os
import json
import time
from typing import Dict, Any
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

_openai_client = None

def get_openai_client():
    """Get or create OpenAI client singleton"""
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            timeout=30.0,
            max_retries=2
        )
    return _openai_client

def chatgpt_generate(prompt: str, model: str = "gpt-4o-mini") -> str:
    """Generate response using OpenAI with fallback"""
    client = get_openai_client()
    
    try:
        if prompt is None:
            prompt = ""
        elif not isinstance(prompt, str):
            prompt = str(prompt)
        safe_content = prompt if prompt.strip() else "Hãy trả lời ngắn gọn."
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": safe_content
                }
            ],
            temperature=0.7,
            max_tokens=1000,
            stream=False
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[ERROR] LLM generation failed: {e}")
        if model != "gpt-3.5-turbo":
            try:
                return chatgpt_generate(prompt, "gpt-3.5-turbo")
            except:
                pass
        raise e

def chatgpt_generate_stream(prompt: str, model: str = "gpt-4o-mini", cancellation_check=None):
    """Generate streaming response using OpenAI with fallback"""
    client = get_openai_client()
    
    try:
        if prompt is None:
            prompt = ""
        elif not isinstance(prompt, str):
            prompt = str(prompt)
        safe_content = prompt if prompt.strip() else "Hãy trả lời ngắn gọn."
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": safe_content
                }
            ],
            temperature=0.7,
            max_tokens=1000,
            stream=True
        )
        
        for chunk in response:
            if cancellation_check and cancellation_check():
                print("[INFO] LLM stream cancelled by user")
                return
                
            if chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                if content and content.strip() and content not in ['{}', '{"content": ""}', '{"response": ""}']:
                    yield content
                
    except Exception as e:
        print(f"[ERROR] LLM streaming generation failed: {e}")
        if model != "gpt-3.5-turbo":
            try:
                for chunk in chatgpt_generate_stream(prompt, "gpt-3.5-turbo", cancellation_check):
                    yield chunk
                return
            except:
                pass
        yield f"Lỗi hệ thống: {str(e)}"

def process_question_with_llm(question: str, lang: str = "vi", use_caching: bool = True) -> Dict[str, Any]:
    """
    Sử dụng LLM để xử lý và phân loại câu hỏi chính xác hơn
    Với tùy chọn caching keywords để giảm token usage
    
    Args:
        question: Câu hỏi cần xử lý
        lang: Ngôn ngữ ('vi' hoặc 'en')
        use_caching: Có sử dụng keyword caching hay không (mặc định: True)
    
    Returns: {
        'processed_question': str,
        'question_type': str,
        'keywords': list,
        'intent': str,
        'confidence': float,
        'topic': str,
        'method': str
    }
    """
    try:
        if use_caching:
            cached_result = _try_keyword_caching(question, lang)
            if cached_result and cached_result['confidence'] >= 0.6:
                result = _process_with_llm(question, lang)
                result.update({
                    'topic': cached_result['topic'],
                    'method': 'keyword_caching',
                    'cached_keywords': cached_result['keywords']
                })
                return result
        
        result = _process_with_llm(question, lang)
        
        topic_result = classify_topic_with_llm(question, lang)
        result.update({
            'topic': topic_result['topic'],
            'method': 'llm'
        })
        
        return result
        
    except Exception as e:
        print(f"[ERROR] LLM question processing failed: {e}")
        return {
            'processed_question': question,
            'question_type': 'general',
            'keywords': [],
            'intent': 'unknown',
            'confidence': 0.0,
            'topic': 'khác',
            'method': 'fallback'
        }

def _try_keyword_caching(question: str, lang: str = "vi") -> Dict[str, Any]:
    """
    Thử phân loại chủ đề bằng keyword caching
    """
    topic_keywords_map = {
        "nghỉ phép": [
            "nghỉ phép", "leave", "xin nghỉ", "đơn xin nghỉ", "nghỉ năm", "annual leave", 
            "paid leave", "unpaid leave", "nghỉ ốm", "sick leave", "maternity leave", 
            "paternity leave", "compassionate leave", "nghỉ bù", "day off", "xin nghỉ việc",
            "nghỉ lễ", "holiday", "vacation", "nghỉ thai sản", "nghỉ con ốm"
        ],
        "làm thêm giờ": [
            "làm thêm giờ", "overtime", "ot", "thêm giờ", "tăng ca", "extra hours", 
            "after hours", "làm ca đêm", "night shift", "ca tối", "weekend work", 
            "holiday work", "double pay", "tăng ca", "làm thêm", "ca đêm"
        ],
        "làm việc từ xa": [
            "làm việc từ xa", "remote", "work from home", "wfh", "từ xa", "telework", 
            "telecommute", "online work", "virtual work", "hybrid work", "offsite work", 
            "remote policy", "làm việc tại nhà", "làm việc online"
        ],
        "nghỉ việc": [
            "nghỉ việc", "quit", "resign", "thôi việc", "xin nghỉ việc", "termination", 
            "end contract", "nghỉ hưu", "retirement", "chấm dứt hợp đồng", "sa thải", 
            "fired", "layoff", "voluntary leave", "thôi việc", "nghỉ việc"
        ],
        "quy định": [
            "policy", "quy định", "nội quy", "quy chế", "rules", "regulation", 
            "guidelines", "code of conduct", "standard operating procedure", "SOP", 
            "company policy", "chính sách", "quy tắc", "điều lệ","chính sách"
        ],
        "lương thưởng": [
            "lương", "thưởng", "salary", "bonus", "tiền", "lương bổng", "pay", 
            "compensation", "allowance", "phụ cấp", "thu nhập", "payroll", "wage", 
            "commission", "incentive", "13th month salary", "lương tháng 13"
        ],
        "bảo hiểm": [
            "bảo hiểm", "insurance", "bhxh", "bhyt", "bảo hiểm xã hội", "bảo hiểm y tế", 
            "social insurance", "health insurance", "unemployment insurance", 
            "life insurance", "medical coverage", "bảo hiểm thất nghiệp"
        ],
        "đào tạo": [
            "đào tạo", "training", "học", "course", "khóa học", "onboarding", 
            "orientation", "seminar", "workshop", "mentoring", "coaching", 
            "professional development", "technical training", "soft skills training"
        ],
        "công việc": [
            "công việc", "work", "job", "task", "dự án", "project", "assignment", 
            "responsibility", "job description", "JD", "duty", "role", "performance", 
            "KPI", "objective", "nhiệm vụ", "trách nhiệm"
        ],
        "chitchat": [
            "xin chào", "hello", "hi", "cảm ơn", "thank", "tạm biệt", "bye", "chào", 
            "good morning", "good afternoon", "good evening", "how are you", 
            "nice to meet you", "see you", "have a nice day", "chào bạn"
        ]
    }
    
    question_lower = question.lower()
    
    topic_scores = {}
    for topic, keywords in topic_keywords_map.items():
        score = 0
        for keyword in keywords:
            if keyword.lower() in question_lower:
                score += 1
        if score > 0:
            topic_scores[topic] = score
    
    if topic_scores:
        best_topic = max(topic_scores, key=topic_scores.get)
        best_score = topic_scores[best_topic]
        
        if best_score >= 1:
            return {
                'topic': best_topic,
                'confidence': min(0.8, 0.3 + best_score * 0.1),
                'keywords': [k for k in topic_keywords_map[best_topic] if k.lower() in question_lower],
                'method': 'keyword_caching'
            }
    
    return None

def _process_with_llm(question: str, lang: str = "vi") -> Dict[str, Any]:
    """
    Xử lý câu hỏi với LLM (phần core logic)
    """
    if lang == "vi":
        prompt = f"""
        Phân tích câu hỏi sau và trả về JSON với các thông tin:
        1. processed_question: Câu hỏi đã được xử lý để tìm kiếm chính xác hơn
        2. question_type: Loại câu hỏi ('hr_question', 'chitchat', 'general')
        3. keywords: Danh sách từ khóa quan trọng
        4. intent: Ý định của câu hỏi
        5. confidence: Độ tin cậy (0.0-1.0)

        Quy tắc:
        - Nếu câu hỏi liên quan đến HR (lương, thưởng, nghỉ phép, hợp đồng, đào tạo, văn phòng, chính sách, ngày lễ, địa chỉ) → hr_question
        - Nếu câu hỏi chỉ là chào hỏi, tán gẫu, không liên quan công việc → chitchat
        - Nếu câu hỏi mơ hồ, không rõ ràng → general
        - Nếu câu hỏi cần thông tin chi tiết, cần suy luận, cần làm rõ câu hỏi trước → general
        Ví dụ:
        - "ở Việt Nam có những ngày lễ nào ?" → hr_question (về ngày lễ)
        - "xin chào" → chitchat
        - "mỗi mùa đều có vẻ đẹp riêng" → chitchat
        - "tôi muốn tìm hiểu về các chính sách của công ty" → general

        Câu hỏi: "{question}"

        Trả về JSON:
        """
    else:
        prompt = f"""
        Analyze the following question and return JSON with:
        1. processed_question: Processed question for accurate search
        2. question_type: Question type ('hr_question', 'chitchat', 'general')
        3. keywords: List of important keywords
        4. intent: Question intent
        5. confidence: Confidence score (0.0-1.0)

        Rules:
        - If question relates to HR (salary, benefits, leave, contract, training, office, policy, holidays, address) → hr_question
        - If question is just greeting, casual chat, not work-related → chitchat
        - If question is vague, unclear → general

        Question: "{question}"

        Return JSON:
        """

    response = chatgpt_generate(prompt, model="gpt-4o-mini")
    
    try:
        result = json.loads(response.strip())
        
        required_fields = ['processed_question', 'question_type', 'keywords', 'intent', 'confidence']
        for field in required_fields:
            if field not in result:
                result[field] = None if field != 'confidence' else 0.0
        
        if not isinstance(result['confidence'], (int, float)):
            result['confidence'] = 0.0
            
        return result
        
    except json.JSONDecodeError:
        return {
            'processed_question': question,
            'question_type': 'general',
            'keywords': [],
            'intent': 'unknown',
            'confidence': 0.0
        }

def build_prompt(context: str, question: str, lang: str, chat_history: list = None) -> str:
    """Build prompt for LLM"""
    history_prompt = ""
    if chat_history:
        for turn in chat_history:
            if turn["role"] == "user":
                history_prompt += f"\nNgười dùng: {turn['content']}"
            elif turn["role"] == "assistant":
                history_prompt += f"\nTrợ lý: {turn['content']}"

    if lang == "vi":
        template = """
        Bạn là một trợ lý AI lịch sự, trôi chảy, chuyên trả lời các câu hỏi dựa trên tài liệu nhân sự.

        Hành vi của bạn phải tuân thủ nghiêm ngặt các quy tắc sau:

        1. Chỉ sử dụng [ngữ cảnh] được cung cấp để trả lời câu hỏi.
        2. KHÔNG trả lời dựa trên kiến thức chung hoặc bịa đặt thông tin ngoài [ngữ cảnh].
        3. Nếu câu hỏi cần tính toán, hãy giải thích từng bước dựa trên [ngữ cảnh].
        4. Nếu context có thông tin, phải trả lời dựa trên context, không được trả lời phủ định.
        5. Trả lời bằng **tiếng Việt**.
        6. Sử dụng giọng điệu lịch sự, chuyên nghiệp và tự nhiên.

        Hướng dẫn:
        - Nếu ngữ cảnh **có thông tin liên quan**, hãy làm theo định dạng Markdown đầy đủ bên dưới.
        - Nếu ngữ cảnh **không đủ thông tin để trả lời**, hãy lịch sự nói rằng không có câu trả lời trong tài liệu.
        - KHÔNG sử dụng định dạng Markdown trong trường hợp này. Chỉ trả về câu trên.
        - Nếu câu hỏi chứa từ ngữ nhạy cảm, phân biệt chủng tộc, tôn giáo, tình dục, thì từ chối trả lời một cách lịch sự. 
        - Nếu câu hỏi có ý phản động thì từ chối trả lời một cách lịch sự.
        Chỉ trả lời bằng tiếng Việt.

        <context>
        {context}
        </context>
        <history>
        {history_prompt}
        </history>

        <question>
        {question}
        </question>

        ---

        ****  
            [Tạo câu trả lời chuyên nghiệp, tự nhiên, dựa trên ngữ cảnh]

        ---

        """
    else:
        template = """
        You are a polite and fluent AI assistant specialized in answering questions based on HR documents.

        Your behavior must strictly follow these rules:

        1. Use only the provided [context] to answer the question.
        2. Do NOT answer from general knowledge or fabricate any information beyond the [context].
        3. If the question requires calculation or reasoning, explain your steps based only on the context.
        4. Respond in **English**.
        5. Use a polite, professional, and natural tone.

        Instructions:
        - If the context **contains relevant information**, follow the full Markdown output format below.
        - If the context **does NOT contain enough information to answer**, politely say that the answer is not available in the documents.
        - Do **NOT** use Markdown formatting in this case. Just return the sentence above.

        Only answer in English.

        <context>
        {context}
        </context>
        <history>
        {history_prompt}
        </history>

        <question>
        {question}
        </question>

        ---

        ****  
            [detailed answer, clearly supported by context]

        
        ---"""

    return template.format(
        context=context or "",
        question=question or "",
        history_prompt=history_prompt if chat_history else "",
    )

def classify_topic_with_llm(question: str, lang: str = "vi") -> Dict[str, Any]:
    """
    Phân loại chủ đề với LLM
    """
    try:
        if lang == "vi":
            prompt = f"""
            Phân tích câu hỏi sau và trả về JSON với các thông tin:
            1. topic: Chủ đề chính của câu hỏi (ví dụ: nghỉ phép, làm thêm giờ, làm việc từ xa, nghỉ việc, quy định, lương thưởng, bảo hiểm, đào tạo, công việc, chitchat)
            2. confidence: Độ tin cậy của phân loại (0.0-1.0)
            3. reasoning: Lý do tại sao phân loại được chọn
            4. subtopics: Danh sách các chủ đề con (nếu có)
            5. keywords: Danh sách từ khóa quan trọng để phân loại

            Quy tắc:
            - Nếu câu hỏi liên quan đến HR (lương, thưởng, nghỉ phép, hợp đồng, đào tạo, văn phòng, chính sách, ngày lễ, địa chỉ) → nghỉ phép, làm thêm giờ, làm việc từ xa, nghỉ việc, quy định, lương thưởng, bảo hiểm, đào tạo, công việc
            - Nếu câu hỏi chỉ là chào hỏi, tán gẫu, không liên quan công việc → chitchat
            - Nếu câu hỏi mơ hồ, không rõ ràng → general
            - Nếu câu hỏi cần thông tin chi tiết, cần suy luận, cần làm rõ câu hỏi trước → general

            Ví dụ:
            - "ở Việt Nam có những ngày lễ nào ?" → hr_question (về ngày lễ)
            - "xin chào" → chitchat
            - "mỗi mùa đều có vẻ đẹp riêng" → chitchat
            - "tôi muốn tìm hiểu về các chính sách của công ty" → general

            Câu hỏi: "{question}"

            Trả về JSON:
            """
        else:
            prompt = f"""
            Analyze the following question and return JSON with:
            1. topic: Main topic of the question (e.g., leave, overtime, remote work, resignation, policy, salary, benefits, training, job, chitchat)
            2. confidence: Confidence of the classification (0.0-1.0)
            3. reasoning: Reason for the classification
            4. subtopics: List of subtopics (if any)
            5. keywords: List of important keywords for classification

            Rules:
            - If question relates to HR (salary, benefits, leave, contract, training, office, policy, holidays, address) → leave, overtime, remote work, resignation, policy, salary, benefits, training, job
            - If question is just greeting, casual chat, not work-related → chitchat
            - If question is vague, unclear → general
            - If question requires detailed information, reasoning, or clarification → general

            Question: "{question}"

            Return JSON:
            """

        response = chatgpt_generate(prompt, model="gpt-4o-mini")
        
        try:
            result = json.loads(response.strip())
            
            required_fields = ['topic', 'confidence', 'reasoning', 'subtopics', 'keywords']
            for field in required_fields:
                if field not in result:
                    result[field] = None
            
            if not isinstance(result['confidence'], (int, float)):
                result['confidence'] = 0.0
                
            return result
            
        except json.JSONDecodeError:
            return {
                'topic': 'khác',
                'confidence': 0.0,
                'reasoning': f'LLM error: JSON parsing failed',
                'subtopics': [],
                'keywords': []
            }
            
    except Exception as e:
        print(f"[ERROR] LLM topic classification failed: {e}")
        return {
            'topic': 'khác',
            'confidence': 0.0,
            'reasoning': f'LLM error: {str(e)}',
            'subtopics': [],
            'keywords': []
        }

def classify_topic_with_keywords_caching(question: str, lang: str = "vi") -> Dict[str, Any]:
    """
    Phân loại chủ đề với caching keywords để giảm token usage
    Sử dụng LLM lần đầu, sau đó dùng keywords cho câu hỏi tương tự
    """
    topic_keywords_map = {
        "nghỉ phép": [
            "nghỉ phép", "leave", "xin nghỉ", "đơn xin nghỉ", "nghỉ năm", "annual leave", 
            "paid leave", "unpaid leave", "nghỉ ốm", "sick leave", "maternity leave", 
            "paternity leave", "compassionate leave", "nghỉ bù", "day off", "xin nghỉ việc",
            "nghỉ lễ", "holiday", "vacation", "nghỉ thai sản", "nghỉ con ốm"
        ],
        "làm thêm giờ": [
            "làm thêm giờ", "overtime", "ot", "thêm giờ", "tăng ca", "extra hours", 
            "after hours", "làm ca đêm", "night shift", "ca tối", "weekend work", 
            "holiday work", "double pay", "tăng ca", "làm thêm", "ca đêm"
        ],
        "làm việc từ xa": [
            "làm việc từ xa", "remote", "work from home", "wfh", "từ xa", "telework", 
            "telecommute", "online work", "virtual work", "hybrid work", "offsite work", 
            "remote policy", "làm việc tại nhà", "làm việc online"
        ],
        "nghỉ việc": [
            "nghỉ việc", "quit", "resign", "thôi việc", "xin nghỉ việc", "termination", 
            "end contract", "nghỉ hưu", "retirement", "chấm dứt hợp đồng", "sa thải", 
            "fired", "layoff", "voluntary leave", "thôi việc", "nghỉ việc"
        ],
        "quy định": [
            "policy", "quy định", "nội quy", "quy chế", "rules", "regulation", 
            "guidelines", "code of conduct", "standard operating procedure", "SOP", 
            "company policy", "chính sách", "quy tắc", "điều lệ"
        ],
        "lương thưởng": [
            "lương", "thưởng", "salary", "bonus", "tiền", "lương bổng", "pay", 
            "compensation", "allowance", "phụ cấp", "thu nhập", "payroll", "wage", 
            "commission", "incentive", "13th month salary", "lương tháng 13"
        ],
        "bảo hiểm": [
            "bảo hiểm", "insurance", "bhxh", "bhyt", "bảo hiểm xã hội", "bảo hiểm y tế", 
            "social insurance", "health insurance", "unemployment insurance", 
            "life insurance", "medical coverage", "bảo hiểm thất nghiệp"
        ],
        "đào tạo": [
            "đào tạo", "training", "học", "course", "khóa học", "onboarding", 
            "orientation", "seminar", "workshop", "mentoring", "coaching", 
            "professional development", "technical training", "soft skills training"
        ],
        "công việc": [
            "công việc", "work", "job", "task", "dự án", "project", "assignment", 
            "responsibility", "job description", "JD", "duty", "role", "performance", 
            "KPI", "objective", "nhiệm vụ", "trách nhiệm"
        ],
        "chitchat": [
            "xin chào", "hello", "hi", "cảm ơn", "thank", "tạm biệt", "bye", "chào", 
            "good morning", "good afternoon", "good evening", "how are you", 
            "nice to meet you", "see you", "have a nice day", "chào bạn"
        ]
    }
    
    question_lower = question.lower()
    
    topic_scores = {}
    for topic, keywords in topic_keywords_map.items():
        score = 0
        for keyword in keywords:
            if keyword.lower() in question_lower:
                score += 1
        if score > 0:
            topic_scores[topic] = score
    
    if topic_scores:
        best_topic = max(topic_scores, key=topic_scores.get)
        best_score = topic_scores[best_topic]
        
        if best_score >= 1:
            return {
                'topic': best_topic,
                'confidence': min(0.8, 0.3 + best_score * 0.1),
                'reasoning': f'Keyword matching: {best_score} keywords found',
                'subtopics': [],
                'keywords': [k for k in topic_keywords_map[best_topic] if k.lower() in question_lower],
                'method': 'keyword_caching'
            }
    
    try:
        llm_result = classify_topic_with_llm(question, lang)
        llm_result['method'] = 'llm'
        return llm_result
    except Exception as e:
        return {
            'topic': 'khác',
            'confidence': 0.2,
            'reasoning': f'Fallback after LLM error: {str(e)}',
            'subtopics': [],
            'keywords': [],
            'method': 'fallback'
        }

def update_topic_keywords_from_llm(question: str, llm_result: Dict[str, Any]) -> None:
    """
    Cập nhật topic keywords từ kết quả LLM (placeholder function)
    Trong thực tế, có thể lưu vào database hoặc cache
    """
    print(f"[INFO] Would update topic keywords for question: {question}")
    print(f"[INFO] LLM result: {llm_result}") 