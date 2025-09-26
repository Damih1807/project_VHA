from config.database import db
from models.models_db import Users
from models.email_models import EmailTemplate, EmailKeyword, ContactEmail, TeamStructure, EmailConversation, ELeaveConfig
import re
import uuid
from typing import Dict, List, Optional, Any, Tuple
from config.email_config import (
    get_email_template, get_keywords_for_type, 
    get_contacts, get_team_structure, ELEAVE_CONFIG
)
from datetime import datetime, timedelta
from utils.user.llm_services import chatgpt_generate
import os
_conversation_cache = {}
_user_info_cache = {}
_date_extraction_cache = {}
_email_content_cache = {}

def get_hard_coded_email_template(leave_type: str, start_date: str = None, end_date: str = None, reason: str = None, full_name: str = None, team: str = None) -> str:
    """Trả về hard-coded email template cho từng loại với thông tin được truyền vào"""
    
    print(f"[DEBUG] get_hard_coded_email_template called with:")
    print(f"  leave_type: {leave_type}")
    print(f"  start_date: {start_date}")
    print(f"  end_date: {end_date}")
    print(f"  reason: {reason}")
    print(f"  full_name: {full_name}")
    print(f"  team: {team}")
    
    # Sử dụng thông tin được truyền vào, nếu không có hoặc empty thì dùng placeholder
    name_placeholder = full_name if full_name and full_name.strip() else "[TÊN CỦA BẠN]"
    team_placeholder = team if team and team.strip() else "[TÊN TEAM]"
    start_placeholder = start_date if start_date and start_date.strip() else "[NGÀY BẮT ĐẦU]"
    end_placeholder = end_date if end_date and end_date.strip() else "[NGÀY KẾT THÚC]"
    reason_placeholder = reason if reason and reason.strip() else "[LÝ DO]"
    
    print(f"[DEBUG] Placeholders after processing:")
    print(f"  name_placeholder: {name_placeholder}")
    print(f"  team_placeholder: {team_placeholder}")
    print(f"  start_placeholder: {start_placeholder}")
    print(f"  end_placeholder: {end_placeholder}")
    print(f"  reason_placeholder: {reason_placeholder}")
    
    if leave_type == "leave":
        return f"""Kính gửi anh George

Cc chị Jasmine, anh Louis, anh Chris

Em là {name_placeholder} thuộc dự án {team_placeholder}.

Em viết đơn này xin phép anh cho em được nghỉ từ {start_placeholder} đến {end_placeholder}.

Lý do nghỉ phép: {reason_placeholder}.

Trong thời gian nghỉ phép em sẽ cố gắng hỗ trợ team khi cần thiết ạ.

Em xin cảm ơn anh/chị.

{name_placeholder}"""
    
    elif leave_type == "ot":
        return f"""Kính gửi anh George

Cc chị Jasmine, anh Louis, anh Chris

Em là {name_placeholder} thuộc dự án {team_placeholder}.

Em viết đơn này xin phép anh cho em được làm thêm giờ từ {start_placeholder} đến {end_placeholder}.

Lý do làm thêm giờ: {reason_placeholder}.

Em xin cảm ơn anh/chị.

{name_placeholder}"""
    
    elif leave_type == "remote":
        return f"""Kính gửi anh George

Cc chị Jasmine, anh Louis, anh Chris

Em là {name_placeholder} thuộc dự án {team_placeholder}.

Em viết đơn này xin phép anh cho em được làm việc từ xa từ {start_placeholder} đến {end_placeholder}.

Lý do làm việc từ xa: {reason_placeholder}.

Em sẽ đảm bảo hoàn thành công việc đầy đủ và kịp thời.

Em xin cảm ơn anh/chị.

{name_placeholder}"""
    
    elif leave_type == "quit":
        return f"""Kính gửi anh George

Cc chị Jasmine, anh Louis, anh Chris

Em là {name_placeholder}.

Em viết đơn này xin phép được nghỉ việc kể từ ngày {start_placeholder}.

Lý do: {reason_placeholder}.

Em xin cam kết sẽ bàn giao công việc đầy đủ và hỗ trợ quá trình chuyển giao.

Em xin cảm ơn anh/chị.

{name_placeholder}"""
    
    else:
        return "Email template không tồn tại cho loại này."


def clear_all_caches():
    """Xóa tất cả cache"""
    global _conversation_cache, _user_info_cache, _date_extraction_cache, _email_content_cache
    _conversation_cache.clear()
    _user_info_cache.clear()
    _date_extraction_cache.clear()
    _email_content_cache.clear()

def get_cached_user_info(user_id: str) -> Optional[Dict]:
    """Lấy user info từ cache"""
    return _user_info_cache.get(user_id)

def set_cached_user_info(user_id: str, user_info: Dict):
    """Lưu user info vào cache"""
    _user_info_cache[user_id] = user_info

def get_cached_date_extraction(text: str) -> Optional[tuple]:
    """Lấy date extraction result từ cache"""
    return _date_extraction_cache.get(text)

def set_cached_date_extraction(text: str, dates: tuple):
    """Lưu date extraction result vào cache"""
    _date_extraction_cache[text] = dates

def refresh_user_cache(user_id: str):
    """Refresh user cache cho user cụ thể"""
    if user_id in _user_info_cache:
        del _user_info_cache[user_id]

def refresh_date_cache():
    """Refresh date extraction cache"""
    global _date_extraction_cache
    _date_extraction_cache.clear()

def get_cache_status() -> Dict[str, Any]:
    """Lấy trạng thái cache để debug"""
    return {
        "conversation_cache_size": len(_conversation_cache),
        "user_info_cache_size": len(_user_info_cache),
        "date_extraction_cache_size": len(_date_extraction_cache),
        "email_content_cache_size": len(_email_content_cache),
        "conversation_cache_keys": list(_conversation_cache.keys()),
        "user_info_cache_keys": list(_user_info_cache.keys()),
        "date_extraction_cache_keys": list(_date_extraction_cache.keys())[:10],
        "email_content_cache_keys": list(_email_content_cache.keys())
    }

def auto_cleanup_old_cache():
    """Tự động cleanup cache cũ"""
    if len(_conversation_cache) > 1000 or len(_user_info_cache) > 1000 or len(_date_extraction_cache) > 1000 or len(_email_content_cache) > 1000:
        clear_all_caches()

def set_email_content_cache(user_id: str, email_content: str):
    """Lưu email content vào cache để download"""
    _email_content_cache[user_id] = email_content

def get_email_content_cache(user_id: str) -> Optional[str]:
    """Lấy email content từ cache"""
    return _email_content_cache.get(user_id)

def get_email_keywords_from_db() -> Dict[str, List[str]]:
    """Lấy keywords từ database - fallback to config"""
    try:
        from config.email_config import EMAIL_KEYWORDS
        return EMAIL_KEYWORDS.copy()
    except Exception as e:
        print(f"[WARNING] Failed to get keywords from DB: {e}")
        return {}

def get_contacts_from_db() -> Dict[str, str]:
    """Lấy contacts từ database - fallback to config"""
    try:
        from config.email_config import DEFAULT_CONTACTS
        return DEFAULT_CONTACTS.copy()
    except Exception as e:
        print(f"[WARNING] Failed to get contacts from DB: {e}")
        return {}

def get_team_structure_from_db() -> Dict[str, Dict[str, List[str]]]:
    """Lấy team structure từ database - fallback to config"""
    try:
        from config.email_config import TEAM_STRUCTURE_CONFIG
        return TEAM_STRUCTURE_CONFIG.copy()
    except Exception as e:
        print(f"[WARNING] Failed to get team structure from DB: {e}")
        return {}

def get_email_template_from_db(template_type: str, lang: str = "vi") -> Dict[str, str]:
    """Lấy email template từ database - fallback to config"""
    try:
        from config.email_config import get_email_template
        return get_email_template(template_type, lang)
    except Exception as e:
        print(f"[WARNING] Failed to get template from DB: {e}")
        return {}

def get_eleave_config_from_db() -> Dict[str, Any]:
    """Lấy E-leave config từ database - fallback to config"""
    try:
        from config.email_config import ELEAVE_CONFIG
        return ELEAVE_CONFIG.copy()
    except Exception as e:
        print(f"[WARNING] Failed to get E-leave config from DB: {e}")
        return {}

def extract_user_information(text: str) -> Dict[str, str]:
    """Extract user information from text using regex patterns"""
    user_info = {}
    
    name_patterns = [
        r'tên\s+(?:của\s+)?(?:tôi\s+là\s+|em\s+là\s+|mình\s+là\s+)?([A-ZÁÀẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬEÉÈẺẼẸÊẾỀỂỄỆIÍÌỈĨỊOÓÒỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢUÚÙỦŨỤƯỨỪỬỮỰYÝỲỶỸỴĐ][a-záàảãạăắằẳẵặâấầẩẫậeéèẻẽẹêếềểễệiíìỉĩịoóòỏõọôốồổỗộơớờởỡợuúùủũụưứừửữựyýỳỷỹỵđ]*(?:\s+[A-ZÁÀẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬEÉÈẺẼẸÊẾỀỂỄỆIÍÌỈĨỊOÓÒỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢUÚÙỦŨỤƯỨỪỬỮỰYÝỲỶỸỴĐ][a-záàảãạăắằẳẵặâấầẩẫậeéèẻẽẹêếềểễệiíìỉĩịoóòỏõọôốồổỗộơớờởỡợuúùủũụưứừửữựyýỳỷỹỵđ]*)*)',
        r'(?:tôi\s+là\s+|em\s+là\s+|mình\s+là\s+)([A-ZÁÀẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬEÉÈẺẼẸÊẾỀỂỄỆIÍÌỈĨỊOÓÒỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢUÚÙỦŨỤƯỨỪỬỮỰYÝỲỶỸỴĐ][a-záàảãạăắằẳẵặâấầẩẫậeéèẻẽẹêếềểễệiíìỉĩịoóòỏõọôốồổỗộơớờởỡợuúùủũụưứừửữựyýỳỷỹỵđ]*(?:\s+[A-ZÁÀẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬEÉÈẺẼẸÊẾỀỂỄỆIÍÌỈĨỊOÓÒỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢUÚÙỦŨỤƯỨỪỬỮỰYÝỲỶỸỴĐ][a-záàảãạăắằẳẵặâấầẩẫậeéèẻẽẹêếềểễệiíìỉĩịoóòỏõọôốồổỗộơớờởỡợuúùủũụưứừửữựyýỳỷỹỵđ]*)*)',
        r'name:\s*([A-ZÁÀẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬEÉÈẺẼẸÊẾỀỂỄỆIÍÌỈĨỊOÓÒỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢUÚÙỦŨỤƯỨỪỬỮỰYÝỲỶỸỴĐ][a-záàảãạăắằẳẵặâấầẩẫậeéèẻẽẹêếềểễệiíìỉĩịoóòỏõọôốồổỗộơớờởỡợuúùủũụưứừửữựyýỳỷỹỵđ]*(?:\s+[A-ZÁÀẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬEÉÈẺẼẸÊẾỀỂỄỆIÍÌỈĨỊOÓÒỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢUÚÙỦŨỤƯỨỪỬỮỰYÝỲỶỸỴĐ][a-záàảãạăắằẳẵặâấầẩẫậeéèẻẽẹêếềểễệiíìỉĩịoóòỏõọôốồổỗộơớờởỡợuúùủũụưứừửữựyýỳỷỹỵđ]*)*)'
    ]
    
    for pattern in name_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            user_info['full_name'] = match.group(1).strip()
            break
    
    team_patterns = [
        r'team\s+([a-zA-Z0-9_-]+)',
        r'thuộc\s+(?:team\s+|dự\s+án\s+)?([a-zA-Z0-9_-]+)',
        r'dự\s+án\s+([a-zA-Z0-9_-]+)',
        r'team:\s*([a-zA-Z0-9_-]+)'
    ]
    
    for pattern in team_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            user_info['team'] = match.group(1).strip()
            break
    
    return user_info

def collect_missing_information(user_id: str, missing_info: List[str], language: str = "vi") -> str:
    """Collect missing user information"""
    if not missing_info:
        return None
    
    if language == "vi":
        questions = {
            'full_name': 'Bạn có thể cho biết tên đầy đủ của bạn không?',
            'team': 'Bạn thuộc team nào?',
            'start_date': 'Ngày bắt đầu là khi nào? (ví dụ: 10/08)',
            'end_date': 'Ngày kết thúc là khi nào? (ví dụ: 12/08)',
            'reason': 'Lý do xin nghỉ là gì?'
        }
    else:
        questions = {
            'full_name': 'Could you please provide your full name?',
            'team': 'Which team do you belong to?',
            'start_date': 'What is the start date? (e.g., 10/08)',
            'end_date': 'What is the end date? (e.g., 12/08)',
            'reason': 'What is the reason for leave?'
        }
    
    first_missing = missing_info[0]
    return questions.get(first_missing, f"Please provide {first_missing}")

def validate_user_information(user_info: Dict[str, str]) -> Tuple[bool, List[str]]:
    """Validate user information and return missing fields"""
    required_fields = ['full_name', 'team']
    missing_fields = []
    
    for field in required_fields:
        if not user_info.get(field):
            missing_fields.append(field)
    
    return len(missing_fields) == 0, missing_fields

def enhanced_process_email_request(user_input: str, user_id: str, language: str = "vi") -> str:
    """
    Enhanced email processing với tự động lấy thông tin user và chỉ yêu cầu ngày
    """
    conversation = get_conversation_state(user_id)
    
    dates = extract_dates_from_text(user_input)
    leave_type = detect_leave_type(user_input)
    reason = extract_reason_from_text(user_input) or "[Lý do]"
    
    user_info = get_user_info_from_jwt(user_id)
    
    if not conversation:
        conversation = {
            "type": "enhanced_email_workflow",
            "leave_type": leave_type,
            "step": "collect_dates",
            "user_info": user_info,
            "dates": dates if dates[0] else (None, None),
            "reason": reason
        }
        save_conversation_state(user_id, conversation)
    else:
        # Cập nhật dates nếu có
        if dates[0]:
            conversation["dates"] = dates
        
        # Cập nhật reason - logic mới
        new_reason = extract_reason_from_text(user_input)
        print(f"[DEBUG] Extracted reason: {new_reason}")
        print(f"[DEBUG] Current reason in conversation: {conversation.get('reason')}")
        print(f"[DEBUG] User input: '{user_input}'")
        print(f"[DEBUG] Dates extracted: {dates}")
        
        if new_reason and new_reason != "[Lý do]":
            conversation["reason"] = new_reason
            print(f"[DEBUG] Updated reason from extraction: {new_reason}")
        # Nếu user chỉ nhập reason mà không có dates và chưa có reason
        elif not dates[0] and (not conversation.get("reason") or conversation.get("reason") == "[Lý do]"):
            # Loại bỏ các từ không liên quan và coi toàn bộ input là reason
            cleaned_input = user_input.strip()
            if len(cleaned_input) > 2:  # Bất kỳ text nào dài hơn 2 ký tự
                conversation["reason"] = cleaned_input
                print(f"[DEBUG] Updated reason from cleaned input: {cleaned_input}")
        
        conversation["user_info"] = user_info
        save_conversation_state(user_id, conversation)  # Lưu state sau khi cập nhật
    
    missing_info = []
    if not conversation["dates"][0]:
        missing_info.append("start_date")
    if not conversation["dates"][1]:
        missing_info.append("end_date")
    if not conversation.get("reason") or conversation.get("reason") == "[Lý do]":
        missing_info.append("reason")
    
    print(f"[DEBUG] Conversation state: {conversation}")
    print(f"[DEBUG] Missing info: {missing_info}")
    
    if missing_info:
        display_name = get_leave_type_display_name(leave_type)
        
        if "start_date" in missing_info or "end_date" in missing_info:
            return f"Bạn muốn xin {display_name} từ ngày nào đến ngày nào? (ví dụ: 15/08 đến 17/08)"
        elif "reason" in missing_info:
            return f"Bạn có thể cho biết lý do xin {display_name} không? (ví dụ: công việc cá nhân, khám sức khỏe, gia đình...)"
    
    start_date = conversation["dates"][0]
    end_date = conversation["dates"][1]
    full_name = user_info.get("full_name", "[TÊN CỦA BẠN]")
    team = user_info.get("team", "[TÊN TEAM]")
    reason = conversation.get("reason", "[Lý do]")
    leave_type = conversation["leave_type"]
    
    leave_days = 1
    try:
        start = datetime.strptime(start_date, "%d/%m")
        end = datetime.strptime(end_date, "%d/%m")
        leave_days = (end - start).days + 1
    except:
        leave_days = 1
    
    template = get_hard_coded_email_template(
        leave_type, start_date, end_date, reason, full_name, team
    )
    
    # Lưu template vào cache (đã được fill sẵn từ get_hard_coded_email_template)
    set_email_content_cache(user_id, template)
    
    clear_conversation_state(user_id)
    
    download_link = f"http://localhost:3001/api/user/download-email"

    if leave_days >= 3:
        response = f"""📧 **EMAIL TEMPLATE CHO {leave_type.upper()} ({leave_days} NGÀY)**

```
{template}
```

🚨 **QUAN TRỌNG:**
• **Nghỉ từ 3 ngày trở lên BẮT BUỘC phải gửi email này**
• **Phải book trước 5 ngày trên E-leave, nếu không sẽ bị HR từ chối**

📥 **Download email template:** [Tải file .txt]({download_link})

🔗 **Book trên E-leave:** https://vinova.hrpartner.io/portal/employee/login

📋 **Các bước thực hiện:**
1. **DOWNLOAD EMAIL** bằng link trên và chỉnh sửa nếu cần
2. **GỬI EMAIL** theo template
3. **BOOK E-LEAVE** trong vòng 5 ngày
4. Chờ phê duyệt từ manager

⚠️ **Lưu ý:** Không book trước 5 ngày = Tự động bị từ chối"""
    
    else:
        response = f"""📧 **EMAIL TEMPLATE CHO {leave_type.upper()} ({leave_days} NGÀY)**

```
{template}
```

💡 **Thông tin:**
• **Nghỉ dưới 3 ngày không bắt buộc gửi mail** (nhưng có thể gửi nếu muốn)
• **Vẫn phải book trước 5 ngày trên E-leave, nếu không sẽ bị HR từ chối**

📥 **Download email template:** [Tải file .txt]({download_link})

🔗 **Book trên E-leave:** https://vinova.hrpartner.io/portal/employee/login

📋 **Các bước thực hiện:**
1. **BOOK E-LEAVE** trong vòng 5 ngày (bắt buộc)
2. **DOWNLOAD EMAIL** bằng link trên nếu muốn gửi (tùy chọn)
3. Chờ phê duyệt từ manager

⚠️ **Lưu ý:** Không book trước 5 ngày = Tự động bị từ chối"""
    
    return response
    """Phân tích intent bằng LLM"""
    try:
        prompt = f"""
Phân tích câu hỏi sau và trả về JSON với các thông tin:
- intent: loại email (leave, ot, quit, remote)
- dates: ngày bắt đầu và kết thúc (nếu có)
- reason: lý do (nếu có)
- user_info: thông tin user (name, team, office nếu có)
- urgency: có khẩn cấp không (true/false)
- missing_info: thông tin còn thiếu

Câu hỏi: {question}

Trả về JSON format:
{{
    "intent": "leave",
    "dates": ["10/08", "12/08"],
    "reason": "[Lý do]",
    "user_info": {{"name": "Nguyễn Văn A", "team": "backend_team", "office": "hcm"}},
    "urgency": false,
    "missing_info": ["name", "team"]
}}
"""
        
        response = chatgpt_generate(prompt).strip()
        
        try:
            import json
            result = json.loads(response)
            return result
        except json.JSONDecodeError:
            return {
                "intent": "unknown",
                "dates": [],
                "reason": None,
                "user_info": {},
                "urgency": False,
                "missing_info": []
            }
            
    except Exception as e:
        print(f"[WARNING] LLM analysis failed: {e}")
        return {
            "intent": "unknown",
            "dates": [],
            "reason": None,
            "user_info": {},
            "urgency": False,
            "missing_info": []
        }

def analyze_user_input_with_llm(user_input: str, user_id: str, language: str = "vi") -> Dict[str, Any]:
    """
    Phân tích user input bằng LLM để xác định intent và thông tin
    """
    current_user_info = get_user_info_from_jwt(user_id)
    
    prompt = f"""
Phân tích câu hỏi của user và trả về JSON với thông tin chi tiết:

User hiện tại: {current_user_info}

Câu hỏi: {user_input}

Phân tích và trả về JSON:
{{
    "intent": "leave|ot|quit|remote|unknown",
    "dates": ["start_date", "end_date"],
    "reason": "lý do",
    "user_info_updates": {{"name": "tên mới", "team": "team mới", "office": "office mới"}},
    "urgency": true/false,
    "missing_info": ["name", "team", "office"],
    "action": "create_email|show_guidance|ask_info|ask_dates"
}}

Lưu ý:
- Nếu có ngày và khẩn cấp (trong 3 ngày tới) -> action: create_email
- Nếu có ngày và không khẩn cấp -> action: show_guidance  
- Nếu thiếu thông tin user -> action: ask_info
- Nếu thiếu ngày -> action: ask_dates
"""
    
    try:
        response = chatgpt_generate(prompt).strip()
        
        import json
        result = json.loads(response)
        
        if "user_info_updates" in result:
            current_user_info.update(result["user_info_updates"])
            set_cached_user_info(user_id, current_user_info)
        
        return result
        
    except Exception as e:
        print(f"[WARNING] LLM analysis failed: {e}")
        return {
            "intent": "unknown",
            "dates": [],
            "reason": None,
            "urgency": False,
            "missing_info": ["name", "team", "office"],
            "action": "ask_info"
        }

def handle_email_request_with_llm(user_input: str, user_id: str, language: str = "vi") -> str:
    """
    Xử lý email request sử dụng LLM để phân tích
    """
    analysis = analyze_user_input_with_llm(user_input, user_id, language)
    
    intent = analysis.get("intent", "unknown")
    dates = analysis.get("dates", [])
    reason = analysis.get("reason", "[Lý do]")
    urgency = analysis.get("urgency", False)
    missing_info = analysis.get("missing_info", [])
    action = analysis.get("action", "ask_info")
    
    user_info = get_user_info_from_jwt(user_id)
    
    if action == "create_email":
        if len(dates) >= 2:
            return create_leave_email(user_info, dates, reason, language, intent)
        else:
            return "Có lỗi xảy ra khi tạo email"
    
    elif action == "show_guidance":
        if len(dates) >= 2:
            return get_eleave_guidance(intent, dates[0], dates[1], reason)
        else:
            return "Có lỗi xảy ra khi hiển thị hướng dẫn"
    
    elif action == "ask_info":
        return "Flow này không yêu cầu thông tin user"
    
    elif action == "ask_dates":
        display_name = get_leave_type_display_name(intent)
        return f"Bạn muốn xin {display_name} từ ngày nào đến ngày nào? (ví dụ: 10/08 đến 12/08)"
    
    else:
        return "Có lỗi xảy ra, vui lòng thử lại"

def detect_leave_type_with_llm(user_input: str, language: str = "vi") -> str:
    """
    Detect loại leave bằng LLM
    """
    prompt = f"""
Phân tích câu hỏi và xác định loại email:

Câu hỏi: {user_input}

Trả về một trong các loại sau:
- leave: nghỉ phép thông thường
- ot: làm thêm giờ, overtime
- quit: nghỉ việc, resignation  
- remote: làm việc từ xa, work from home

Chỉ trả về tên loại, không có text khác.
"""
    
    try:
        response = chatgpt_generate(prompt).strip()
        leave_type = response.strip().lower()
        
        valid_types = ["leave", "ot", "quit", "remote"]
        if leave_type in valid_types:
            return leave_type
        else:
            return "leave"
            
    except Exception as e:
        print(f"[WARNING] LLM leave type detection failed: {e}")
        return "leave"

def extract_dates_with_llm(text: str, language: str = "vi") -> tuple:
    """
    Extract dates bằng LLM
    """
    prompt = f"""
Trích xuất ngày từ text sau và trả về JSON:

Text: {text}

Trả về JSON format:
{{
    "start_date": "dd/mm",
    "end_date": "dd/mm"
}}

Nếu chỉ có 1 ngày, dùng cùng ngày cho start và end.
Nếu không có ngày, trả về null cho cả hai.
"""
    
    try:
        response = chatgpt_generate(prompt).strip()
        
        import json
        result = json.loads(response)
        
        start_date = result.get("start_date")
        end_date = result.get("end_date")
        
        if start_date and end_date:
            return (start_date, end_date)
        else:
            return (None, None)
            
    except Exception as e:
        print(f"[WARNING] LLM date extraction failed: {e}")
        return (None, None)

def extract_reason_with_llm(text: str, language: str = "vi") -> str:
    """
    Extract reason bằng LLM
    """
    prompt = f"""
Trích xuất lý do từ text sau:

Text: {text}

Trả về lý do ngắn gọn, nếu không có thì trả về "[Lý do]".
"""
    
    try:
        response = chatgpt_generate(prompt).strip()
        reason = response.strip()
        
        if reason and reason.lower() not in ["không có", "none", "null"]:
            return reason
        else:
            return "[Lý do]"
            
    except Exception as e:
        print(f"[WARNING] LLM reason extraction failed: {e}")
        return "[Lý do]"

def check_urgency_with_llm(start_date: str, language: str = "vi") -> bool:
    """
    Kiểm tra urgency bằng LLM
    """
    prompt = f"""
Kiểm tra xem ngày {start_date} có khẩn cấp không (trong vòng 3 ngày tới từ hôm nay).

Trả về true nếu khẩn cấp, false nếu không.
"""
    
    try:
        response = chatgpt_generate(prompt).strip()
        response_lower = response.strip().lower()
        
        return response_lower in ["true", "yes", "có", "khẩn cấp"]
        
    except Exception as e:
        print(f"[WARNING] LLM urgency check failed: {e}")
        return False

def is_leave_email_request(question: str) -> bool:
    """Kiểm tra xem có phải request email nghỉ phép không"""
    keywords = get_keywords_for_type("leave")
    question_lower = question.lower()
    
    for keyword in keywords:
        if keyword.lower() in question_lower:
            return True
    
    import re
    date_patterns = [
        r'\d{1,2}/\d{1,2}.*?(?:đến|tới|until|to).*?\d{1,2}/\d{1,2}',
        r'từ.*?\d{1,2}/\d{1,2}.*?(?:đến|tới).*?\d{1,2}/\d{1,2}',
        r'nghỉ.*?\d{1,2}/\d{1,2}.*?(?:đến|tới).*?\d{1,2}/\d{1,2}',
    ]
    
    for pattern in date_patterns:
        if re.search(pattern, question_lower):
            print(f"[DEBUG] Date pattern matched for leave request: {pattern}")
            return True
    
    return False

def is_quit_email_request(question: str) -> bool:
    """Kiểm tra xem có phải request email nghỉ việc không"""
    keywords = get_keywords_for_type("quit")
    question_lower = question.lower()
    
    for keyword in keywords:
        if keyword.lower() in question_lower:
            return True
    
    return False

def is_ot_email_request(question: str) -> bool:
    """Kiểm tra xem có phải request email OT không"""
    keywords = get_keywords_for_type("ot")
    question_lower = question.lower()
    
    for keyword in keywords:
        if keyword.lower() in question_lower:
            return True
    
    return False

def is_remote_email_request(question: str) -> bool:
    """Kiểm tra xem có phải request email remote work không"""
    keywords = get_keywords_for_type("remote")
    question_lower = question.lower()
    
    for keyword in keywords:
        if keyword.lower() in question_lower:
            return True
    
    return False

def get_user_info(user_id: str) -> Dict[str, str]:
    """Lấy thông tin user từ database"""
    try:
        user = db.session.query(Users).filter_by(user_id=user_id).first()
        if user:
            return {
                "full_name": user.full_name,
                "email": user.email,
                "team": getattr(user, 'team', ''),
                "office": getattr(user, 'office', '')
            }
        return {}
    except Exception as e:
        print(f"[WARNING] Failed to get user info from DB: {e}")
        return {}

def get_user_info_from_jwt(user_id: str) -> Dict[str, str]:
    """Lấy thông tin user từ JWT và cache"""
    cached_info = get_cached_user_info(user_id)
    if cached_info:
        return cached_info
    
    user_info = {
        "user_id": user_id,
        "full_name": "",
        "email": "",
        "team": "",
        "office": ""
    }
    
    try:
        db_info = get_user_info(user_id)
        user_info.update(db_info)
        
        if not user_info.get("full_name"):
            try:
                from flask import g
                if hasattr(g, 'user') and g.user:
                    user_info["full_name"] = g.user.get("full_name", "") or g.user.get("name", "")
                    user_info["email"] = g.user.get("email", "")
            except Exception as e:
                print(f"[WARNING] Failed to get user info from Flask context: {e}")
        
    except Exception as e:
        print(f"[WARNING] Failed to get user info from DB: {e}")
    
    set_cached_user_info(user_id, user_info)
    
    return user_info

def determine_office_and_team(user_info: Dict[str, str]) -> Dict[str, str]:
    """Xác định office và team từ user info"""
    office = user_info.get("office", "hcm")
    team = user_info.get("team", "teamnet")
    return {"office": office, "team": team}

def get_cc_list(office: str, team: str, leave_days: int) -> List[str]:
    """Lấy danh sách CC cho email"""
    contacts = get_contacts()
    team_structure = get_team_structure()
    
    cc_list = []
    
    if office in contacts:
        cc_list.append(contacts[office])
    
    if office in team_structure and team in team_structure[office]:
        cc_list.extend(team_structure[office][team])
    
    return cc_list

def build_email_from_template(
    template_type: str,
    full_name: str, 
    alias_name: str,
    email: str, 
    start_date: str, 
    end_date: str, 
    reason: str = "[Lý do]", 
    office: str = "hcm",
    team: str = "teamnet",
    lang: str = "vi"
) -> str:
    """Build email từ template"""
    template = get_email_template(template_type, lang)
    
    if not template:
        return "Template không tồn tại"
    
    try:
        start = datetime.strptime(start_date, "%d/%m")
        end = datetime.strptime(end_date, "%d/%m")
        leave_days = (end - start).days + 1
    except:
        leave_days = 1
    
    cc_list = get_cc_list(office, team, leave_days)
    cc_emails = ", ".join(cc_list) if cc_list else ""
    
    email_content = template["content"].format(
        full_name=full_name,
        alias_name=alias_name,
        email=email,
        start_date=start_date,
        end_date=end_date,
        reason=reason,
        office=office,
        team=team,
        leave_days=leave_days,
        cc_emails=cc_emails,
        to_recipients="Anh George",
        cc_recipients=cc_emails or "Chị Jasmine, Anh Louis, Chị Sunny"
    )
    
    return email_content

def build_leave_email_template(
    full_name: str, 
    alias_name: str,
    email: str, 
    start_date: str, 
    end_date: str, 
    reason: str = "[Lý do]", 
    office: str = "hcm",
    team: str = "teamnet",
    lang: str = "vi"
) -> str:
    """Build leave email template"""
    return build_email_from_template("leave", full_name, alias_name, email, start_date, end_date, reason, office, team, lang)

def build_quit_email_template(
    full_name: str, 
    alias_name: str,
    email: str, 
    start_date: str, 
    end_date: str, 
    reason: str = "[Lý do]", 
    lang: str = "vi"
) -> str:
    """Build quit email template"""
    return build_email_from_template("quit", full_name, alias_name, email, start_date, end_date, reason, lang=lang)

def build_OT_email_template(
    full_name: str, 
    alias_name: str,
    email: str, 
    start_date: str, 
    end_date: str, 
    reason: str = "công việc", 
    lang: str = "vi"
) -> str:
    """Build OT email template"""
    return build_email_from_template("ot", full_name, alias_name, email, start_date, end_date, reason, lang=lang)

def build_remote_email_template(
    full_name: str, 
    alias_name: str,
    email: str, 
    start_date: str, 
    end_date: str, 
    reason: str = "công việc", 
    lang: str = "vi"
) -> str:
    """Build remote work email template"""
    return build_email_from_template("remote", full_name, alias_name, email, start_date, end_date, reason, lang=lang)

def extract_dates(text: str) -> tuple:
    """Extract dates từ text (legacy function)"""
    return extract_dates_from_text(text)

def extract_dates_from_text(text: str) -> tuple:
    """Extract dates từ text với cache"""
    cached_result = get_cached_date_extraction(text)
    if cached_result:
        return cached_result
    
    patterns = [
        r'từ\s+ngày\s+(\d{1,2}/\d{1,2})\s+(?:đến|tới)\s+ngày\s+(\d{1,2}/\d{1,2})',
        r'ngày\s+(\d{1,2}/\d{1,2})\s+(?:đến|tới)\s+ngày\s+(\d{1,2}/\d{1,2})',
        r'(\d{1,2}/\d{1,2})\s+(?:đến|tới)\s+(\d{1,2}/\d{1,2})',
        r'(\d{1,2}/\d{1,2})-(\d{1,2}/\d{1,2})',
        r'từ\s+(\d{1,2}/\d{1,2})\s+(?:đến|tới)\s+(\d{1,2}/\d{1,2})',
        r'ngày\s+(\d{1,2}(?:/\d{1,2})?)',
        r'(\d{1,2}/\d{1,2})',
        r'(\d{1,2})-(\d{1,2})\s+tháng\s+(\d{1,2})',
        r'từ\s+(\d{1,2})-(\d{1,2})\s+tháng\s+(\d{1,2})'
    ]
    
    text_lower = text.lower()
    
    for pattern in patterns:
        matches = re.findall(pattern, text_lower)
        if matches:
            if len(matches[0]) == 2:
                start_date, end_date = matches[0]
                if '/' not in start_date:
                    start_date = f"{start_date}/{datetime.now().month:02d}"
                if '/' not in end_date:
                    end_date = f"{end_date}/{datetime.now().month:02d}"
                
                result = (start_date, end_date)
                set_cached_date_extraction(text, result)
                return result
            elif len(matches[0]) == 1:
                date_str = matches[0]
                if '/' not in date_str:
                    date_str = f"{date_str}/{datetime.now().month:02d}"
                
                result = (date_str, date_str)
                set_cached_date_extraction(text, result)
                return result
    
    result = (None, None)
    set_cached_date_extraction(text, result)
    return result

def extract_reason_from_text(text: str) -> str:
    """Trích xuất lý do từ text"""
    reason_keywords = [
        "lý do", "reason", "vì", "do", "bởi vì", "tại vì",
        "khám bệnh", "ốm", "bệnh", "sức khỏe", "health",
        "gia đình", "family", "[Lý do]", "personal",
        "công việc", "work", "dự án", "project",
        "nghĩa vụ quân sự", "khám nghĩa vụ quân sự", "quân sự",
        "đi khám", "khám sức khỏe", "kiểm tra sức khỏe",
        "đau bụng", "đau đầu", "đau lưng"
    ]
    
    text_lower = text.lower()
    for keyword in reason_keywords:
        if keyword in text_lower:
            sentences = text.split('.')
            for sentence in sentences:
                if keyword in sentence.lower():
                    keyword_pos = sentence.lower().find(keyword)
                    if keyword_pos != -1:
                        reason_part = sentence[keyword_pos + len(keyword):].strip()
                        if reason_part:
                            return reason_part
                        else:
                            return keyword
    
    return None

def get_conversation_state(user_id: str) -> Optional[Dict]:
    """Lấy conversation state từ cache (database tạm thời disabled)"""
    if user_id in _conversation_cache:
        return _conversation_cache[user_id]
    
    return None

def save_conversation_state(user_id: str, conversation: Dict):
    """Lưu conversation state vào cache (database tạm thời disabled)"""
    try:
        _conversation_cache[user_id] = conversation
        print(f"[INFO] Saved conversation state to cache for user {user_id}")
        
    except Exception as e:
        print(f"[WARNING] Failed to save conversation: {e}")
        _conversation_cache[user_id] = conversation

def clear_conversation_state(user_id: str):
    """Xóa conversation state"""
    try:
        if user_id in _conversation_cache:
            del _conversation_cache[user_id]
            print(f"[INFO] Cleared conversation state for user {user_id}")
    except Exception as e:
        print(f"[WARNING] Failed to clear conversation: {e}")
    
    if user_id in _conversation_cache:
        del _conversation_cache[user_id]

def is_urgent_leave(start_date: str) -> bool:
    """Kiểm tra xem có phải urgent leave không (< 3 ngày) - Logic mới theo yêu cầu"""
    try:
        if '/' in start_date:
            day, month = start_date.split('/')
            start_day = int(day)
            start_month = int(month)
        else:
            start_day = int(start_date)
            start_month = datetime.now().month
        
        now = datetime.now()
        current_day = now.day
        current_month = now.month
        current_year = now.year
        
        try:
            if start_month >= current_month:
                start_year = current_year
            else:
                start_year = current_year + 1
                
            start_datetime = datetime(start_year, start_month, start_day)
            days_diff = (start_datetime - now).days
        except ValueError:
            if start_month == current_month:
                days_diff = start_day - current_day
            else:
                days_diff = start_day + (30 - current_day)
        
        return days_diff < 3 and days_diff >= 0
        
    except Exception as e:
        print(f"[WARNING] Error checking urgent leave: {e}")
        return False

def calculate_days_difference(start_date: str) -> int:
    """Tính số ngày từ hôm nay đến start_date - Cải thiện accuracy"""
    try:
        if '/' in start_date:
            day, month = start_date.split('/')
            start_day = int(day)
            start_month = int(month)
        else:
            start_day = int(start_date)
            start_month = datetime.now().month
        
        now = datetime.now()
        current_year = now.year
        
        try:
            if start_month >= now.month:
                start_year = current_year
            else:
                start_year = current_year + 1
                
            start_datetime = datetime(start_year, start_month, start_day)
            days_diff = (start_datetime - now).days
            
            return days_diff
        except ValueError:
            if start_month == now.month:
                days_diff = start_day - now.day
            else:
                days_diff = start_day + (30 - now.day)
            
            return days_diff
        
    except Exception as e:
        print(f"[WARNING] Error calculating days difference: {e}")
        return 0

def is_in_leave_email(user_id: str) -> bool:
    """Kiểm tra xem user có đang trong leave email workflow không"""
    conversation = get_conversation_state(user_id)
    return conversation is not None

def create_leave_email(user_info: Dict, dates: List[str], reason: str, language: str = "vi", leave_type: str = "leave") -> str:
    """Tạo email nghỉ phép sử dụng hard-coded template"""
    if not dates or len(dates) < 2:
        return "Thiếu thông tin ngày"
    
    start_date, end_date = dates[0], dates[1]
    
    template = get_hard_coded_email_template(leave_type, start_date, end_date, reason)
    
    if user_info.get("full_name"):
        template = template.replace("[TÊN CỦA BẠN]", user_info["full_name"])
    if user_info.get("team"):
        template = template.replace("[TÊN TEAM]", user_info["team"])
    
    return template

def create_leave_email_original(user_info: Dict, dates: List[str], reason: str, language: str = "vi") -> str:
    """Tạo email nghỉ phép (original function)"""
    return create_leave_email(user_info, dates, reason, language, "leave")

def create_quit_email(user_info: Dict[str, str], dates: Tuple[str, str], reason: str, language: str = "vi") -> str:
    """Tạo email nghỉ việc"""
    return create_leave_email(user_info, list(dates), reason, language, "quit")

def create_OT_email(user_info: Dict[str, str], dates: Tuple[str, str], reason: str, language: str = "vi") -> str:
    """Tạo email OT"""
    return create_leave_email(user_info, list(dates), reason, language, "ot")

def create_remote_email(user_info: Dict[str, str], dates: Tuple[str, str], reason: str, language: str = "vi") -> str:
    """Tạo email remote work"""
    return create_leave_email(user_info, list(dates), reason, language, "remote")

def get_leave_type_display_name(leave_type: str) -> str:
    """
    Lấy display name cho leave type
    """
    display_names = {
        "leave": "Leave",
        "ot": "OT (Overtime)",
        "quit": "Quit (Resignation)", 
        "remote": "Remote Work"
    }
    return display_names.get(leave_type, "Leave")

def get_eleave_guidance_by_type(leave_type: str) -> str:
    """
    Lấy E-leave guidance theo loại leave
    """
    if leave_type == "ot":
        return get_ot_eleave_guidance()
    elif leave_type == "quit":
        return get_quit_eleave_guidance()
    elif leave_type == "remote":
        return get_remote_eleave_guidance()
    else:
        display_name = get_leave_type_display_name(leave_type)
        return get_eleave_guidance(display_name)

def get_eleave_guidance(leave_type: str, start_date: str = None, end_date: str = None, reason: str = None) -> str:
    """
    Trả về hướng dẫn chi tiết book lịch trên E-leave system với thông tin động
    """
    from_date_text = f"**{start_date}**" if start_date else "Chọn ngày bắt đầu"
    until_date_text = f"**{end_date}**" if end_date else "Chọn ngày kết thúc"
    reason_text = f"**{reason}**" if reason and reason != "[Lý do]" else "Điền chi tiết lý do"
    
    guidance = f"""
Bạn có thể đặt lịch trước qua hệ thống e-leave tại: 
https://vinova.hrpartner.io/portal/employee/login

📋 HƯỚNG DẪN BOOK LỊCH ({leave_type}) TRÊN HỆ THỐNG E-LEAVE:

1. 🚪 Truy cập vào mục "Time Off & Leave"
   - Đăng nhập vào hệ thống
   - Trên thanh menu bên trái, chọn mục "Time Off & Leave"

2. 📝 Điền thông tin vào đơn:
   - Application Will Be Sent To: Đơn của bạn sẽ được gửi đến những người có tên trong danh sách này để phê duyệt
   - Leave Type: Chọn loại hình {leave_type}
   - From: {from_date_text}
   - Until: {until_date_text}
   - Duration (Days): Số ngày sẽ tự động được tính
   - Short Description: Nhập mô tả ngắn gọn về lý do
   - Reason: {reason_text}

3. 📤 Gửi đơn:
   - Sau khi điền đầy đủ thông tin, nhấn nút "Submit" để gửi đơn

4. 📊 Theo dõi trạng thái đơn:
   - Bạn có thể theo dõi trạng thái đơn trong phần lịch bên phải
   - Các ngày đã được phê duyệt sẽ hiển thị trên lịch
   - Lịch cũng hiển thị các ngày lễ

Lưu ý: Các yêu cầu có dự định (trước 3 ngày) không cần gửi email, chỉ cần book trên hệ thống.
"""
    return guidance

def get_ot_eleave_guidance() -> str:
    """
    Trả về hướng dẫn chi tiết book OT trên E-leave system
    """
    return get_eleave_guidance("OT (Overtime)")

def get_quit_eleave_guidance() -> str:
    """
    Trả về hướng dẫn chi tiết book resignation trên E-leave system
    """
    return get_eleave_guidance("Quit (Resignation)")

def get_remote_eleave_guidance() -> str:
    """
    Trả về hướng dẫn chi tiết book remote work trên E-leave system
    """
    return get_eleave_guidance("Remote Work")

def detect_leave_type(user_input: str) -> str:
    """
    Detect loại leave từ user input (sử dụng LLM)
    """
    return detect_leave_type_with_llm(user_input, "vi")

def handle_urgent_vs_planned_workflow(user_input: str, user_id: str, language: str = "vi") -> str:
    """
    Workflow chính: Xử lý logic khẩn cấp vs không khẩn cấp sử dụng LLM
    """
    return handle_email_request_with_llm(user_input, user_id, language)

def handle_urgent_case(user_input: str, user_id: str, language: str, leave_type: str, dates: tuple) -> str:
    """
    Xử lý trường hợp khẩn cấp - Không cần trong flow mới
    """
    return process_email_request(user_input, user_id, language)

def handle_planned_case(leave_type: str, start_date: str = None, end_date: str = None, reason: str = None) -> str:
    """
    Xử lý trường hợp planned - Chuyển về flow mới
    """
    user_input = f"{leave_type} từ {start_date} đến {end_date}"
    if reason:
        user_input += f" lý do {reason}"
    return process_email_request(user_input, "dummy_user", "vi")
    reason_text = f"**{reason}**" if reason and reason != "[Lý do]" else "Điền chi tiết lý do"
    
    leave_days = 1
    if start_date and end_date:
        try:
            start = datetime.strptime(start_date, "%d/%m")
            end = datetime.strptime(end_date, "%d/%m")
            leave_days = (end - start).days + 1
        except:
            leave_days = 1
    
    display_name = get_leave_type_display_name(leave_type)
    
    if leave_days >= 3:
        template = get_hard_coded_email_template(leave_type, start_date, end_date, reason)
        guidance = f"""� **NGHỈ PHÉP THEO KẾ HOẠCH ({leave_days} NGÀY)**

🚨 **Do nghỉ từ 3 ngày trở lên, bạn cần viết mail và book E-leave:**

📧 **BƯỚC 1: Viết mail theo template sau:**

```
{template}
```

💡 **Hướng dẫn viết mail:**
• Copy template trên và điền thông tin cần thiết
• Gửi mail trước khi book E-leave
• Đảm bảo có đủ thông tin: ngày, lý do, team

🔗 **BƯỚC 2: Book lịch trên hệ thống E-leave:**
https://vinova.hrpartner.io/portal/employee/login

📋 **HƯỚNG DẪN BOOK LỊCH ({leave_type}) TRÊN HỆ THỐNG E-LEAVE:**

1. 🚪 **Truy cập vào mục "Time Off & Leave"**
   - Đăng nhập vào hệ thống
   - Trên thanh menu bên trái, chọn mục "Time Off & Leave"

2. 📝 **Điền thông tin vào đơn:**
   - Application Will Be Sent To: Đơn của bạn sẽ được gửi đến những người có tên trong danh sách này để phê duyệt
   - Leave Type: Chọn loại hình {leave_type}
   - From: {from_date_text}
   - Until: {until_date_text}
   - Duration (Days): Số ngày sẽ tự động được tính
   - Short Description: Nhập mô tả ngắn gọn về lý do
   - Reason: {reason_text}

3. 📤 **Gửi đơn:**
   - Sau khi điền đầy đủ thông tin, nhấn nút "Submit" để gửi đơn

4. 📊 **Theo dõi trạng thái đơn:**
   - Bạn có thể theo dõi trạng thái đơn trong phần lịch bên phải
   - Các ngày đã được phê duyệt sẽ hiển thị trên lịch
   - Lịch cũng hiển thị các ngày lễ

⚠️ **Lưu ý quan trọng:**
• Đối với ngày nghỉ có kế hoạch trước 03 ngày sẽ được BGĐ accept
• Dưới 03 ngày có thể bị reject và coi như nghỉ không hưởng lương (trừ trường hợp khẩn cấp)
• Nghỉ từ 3 ngày trở lên PHẢI viết mail và submit đơn"""
    
    else:
        guidance = f"""📅 **NGHỈ PHÉP THEO KẾ HOẠCH ({leave_days} NGÀY)**

✅ **Vì nghỉ dưới 3 ngày, bạn chỉ cần book E-leave, không cần viết mail**

🔗 **Truy cập hệ thống E-leave:**
https://vinova.hrpartner.io/portal/employee/login

📋 **HƯỚNG DẪN BOOK LỊCH ({leave_type}) TRÊN HỆ THỐNG E-LEAVE:**

1. 🚪 **Truy cập vào mục "Time Off & Leave"**
   - Đăng nhập vào hệ thống
   - Trên thanh menu bên trái, chọn mục "Time Off & Leave"

2. 📝 **Điền thông tin vào đơn:**
   - Application Will Be Sent To: Đơn của bạn sẽ được gửi đến những người có tên trong danh sách này để phê duyệt
   - Leave Type: Chọn loại hình {leave_type}
   - From: {from_date_text}
   - Until: {until_date_text}
   - Duration (Days): Số ngày sẽ tự động được tính
   - Short Description: Nhập mô tả ngắn gọn về lý do
   - Reason: {reason_text}

3. 📤 **Gửi đơn:**
   - Sau khi điền đầy đủ thông tin, nhấn nút "Submit" để gửi đơn

4. 📊 **Theo dõi trạng thái đơn:**
   - Bạn có thể theo dõi trạng thái đơn trong phần lịch bên phải
   - Các ngày đã được phê duyệt sẽ hiển thị trên lịch
   - Lịch cũng hiển thị các ngày lễ

💡 **Lưu ý:** Nghỉ dưới 3 ngày chỉ cần book trên hệ thống, không cần gửi mail."""
    
    return guidance

def start_date_conversation(user_id: str, language: str, leave_type: str, display_name: str) -> str:
    """
    Bắt đầu conversation để hỏi ngày
    """
    conversation = {
        "type": "urgent_planned_workflow",
        "leave_type": leave_type,
        "step": "ask_dates"
    }
    save_conversation_state(user_id, conversation)
    
    return f"Bạn muốn xin {display_name} từ ngày nào đến ngày nào? (ví dụ: 10/08 đến 12/08)"

def continue_urgent_planned_workflow(user_input: str, user_id: str, language: str) -> str:
    """
    Tiếp tục workflow khi user cung cấp thông tin
    """
    conversation = get_conversation_state(user_id)
    
    if not conversation:
        return "Có lỗi xảy ra, vui lòng thử lại."
    
    user_input_lower = user_input.lower()
    team_info = None
    office_info = None
    
    team_patterns = [
        r'team\s+(\w+)',
        r'(\w+)_team',
        r'team\s+(\w+)_team'
    ]
    
    office_patterns = [
        r'office\s+(\w+)',
        r'văn\s+phòng\s+(\w+)',
        r'(\w+)\s+office'
    ]
    
    for pattern in team_patterns:
        team_match = re.search(pattern, user_input_lower)
        if team_match:
            team_info = team_match.group(1)
            break
    
    for pattern in office_patterns:
        office_match = re.search(pattern, user_input_lower)
        if office_match:
            office_info = office_match.group(1)
            break
    
    if team_info or office_info:
        cached_user_info = get_cached_user_info(user_id) or {}
        if team_info:
            cached_user_info["team"] = team_info
        if office_info:
            cached_user_info["office"] = office_info
        set_cached_user_info(user_id, cached_user_info)
        
        leave_type = conversation.get("leave_type", "leave")
        display_name = get_leave_type_display_name(leave_type)
        
        if "dates" in conversation:
            dates = conversation["dates"]
            urgent = is_urgent_leave(dates[0])
            if urgent:
                return handle_urgent_case(user_input, user_id, language, leave_type, dates)
            else:
                clear_conversation_state(user_id)
                reason = extract_reason_from_text(user_input) or "[Lý do]"
                return handle_planned_case(leave_type, dates[0], dates[1], reason)
        else:
            return f"Bạn muốn xin {display_name} từ ngày nào đến ngày nào? (ví dụ: 10/08 đến 12/08)"
    
    dates = extract_dates_from_text(user_input)
    
    if not dates or not dates[0]:
        return "Mình chưa hiểu rõ ngày, bạn nhập lại giúp mình nhé (ví dụ: 15/08 đến 17/08)"
    
    conversation["dates"] = dates
    save_conversation_state(user_id, conversation)
    
    days_diff = calculate_days_difference(dates[0])
    leave_type = conversation["leave_type"]
    
    if days_diff < 3:
        clear_conversation_state(user_id)
        return handle_urgent_case(user_input, user_id, language, leave_type, dates)
    else:
        clear_conversation_state(user_id)
        reason = extract_reason_from_text(user_input) or "[Lý do]"
        return handle_planned_case(leave_type, dates[0], dates[1], reason) 

def process_email_request(user_input: str, user_id: str, language: str = "vi") -> str:
    """
    Xử lý email request với flow đơn giản:
    1. Nhập ngày → Tạo email template ngay (tự động lấy thông tin user)
    2. Nghỉ trên 3 ngày → Bắt buộc gửi mail
    3. Tất cả đều phải book E-leave trước 5 ngày
    """
    dates = extract_dates_from_text(user_input)
    leave_type = detect_leave_type(user_input)
    reason = extract_reason_from_text(user_input) or "[Lý do]"
    
    user_info = get_user_info_from_jwt(user_id)
    full_name = user_info.get("full_name", "[TÊN CỦA BẠN]")
    team = user_info.get("team", "[TÊN TEAM]")
    
    if not dates or not dates[0]:
        display_name = get_leave_type_display_name(leave_type)
        return f"Bạn muốn xin {display_name} từ ngày nào đến ngày nào? (ví dụ: 10/08 đến 12/08)"
    
    leave_days = 1
    if dates[0] and dates[1]:
        try:
            start = datetime.strptime(dates[0], "%d/%m")
            end = datetime.strptime(dates[1], "%d/%m")
            leave_days = (end - start).days + 1
        except:
            leave_days = 1
    
    template = get_hard_coded_email_template(leave_type, dates[0], dates[1], reason, full_name, team)
    
    set_email_content_cache(user_id, template)
    
    download_link = f"http://localhost:3001/api/user/download-email"

    if leave_days >= 3:
        response = f"""📧 **EMAIL TEMPLATE CHO {leave_type.upper()} ({leave_days} NGÀY)**

```
{template}
```

🚨 **QUAN TRỌNG:**
• **Nghỉ từ 3 ngày trở lên BẮT BUỘC phải gửi email này**
• **Phải book trước 5 ngày trên E-leave, nếu không sẽ bị HR từ chối**

📥 **Download email template:** [Tải file .txt]({download_link})

🔗 **Book trên E-leave:** https://vinova.hrpartner.io/portal/employee/login

📋 **Các bước thực hiện:**
1. **DOWNLOAD EMAIL** bằng link trên và chỉnh sửa nếu cần
2. **GỬI EMAIL** theo template trước
3. **BOOK E-LEAVE** trong vòng 5 ngày
4. Chờ phê duyệt từ manager

⚠️ **Lưu ý:** Không book trước 5 ngày = Tự động bị từ chối"""
    
    else:
        response = f"""📧 **EMAIL TEMPLATE CHO {leave_type.upper()} ({leave_days} NGÀY)**

```
{template}
```

💡 **Thông tin:**
• **Nghỉ dưới 3 ngày không bắt buộc gửi mail** (nhưng có thể gửi nếu muốn)
• **Vẫn phải book trước 5 ngày trên E-leave, nếu không sẽ bị HR từ chối**

📥 **Download email template:** [Tải file .txt]({download_link})

🔗 **Book trên E-leave:** https://vinova.hrpartner.io/portal/employee/login

📋 **Các bước thực hiện:**
1. **BOOK E-LEAVE** trong vòng 5 ngày (bắt buộc)
2. **DOWNLOAD EMAIL** bằng link trên nếu muốn gửi (tùy chọn)
3. Chờ phê duyệt từ manager

⚠️ **Lưu ý:** Không book trước 5 ngày = Tự động bị từ chối"""
    
    return response

def smart_email_processor(user_input: str, user_id: str, language: str = "vi") -> str:
    """
    Smart processor cho email request với auto user info detection
    """
    try:
        return enhanced_process_email_request(user_input, user_id, language)
        
    except Exception as e:
        print(f"[ERROR] Smart email processor failed: {e}")
        return process_email_request(user_input, user_id, language)

def analyze_intent_with_llm(question: str, lang: str = "vi") -> Dict[str, Any]:
    """Phân tích intent bằng LLM"""
    try:
        prompt = f"""
Phân tích câu hỏi sau và trả về JSON với các thông tin:
- intent: loại email (leave, ot, quit, remote)
- dates: ngày bắt đầu và kết thúc (nếu có)
- reason: lý do (nếu có)
- user_info: thông tin user (name, team, office nếu có)
- urgency: có khẩn cấp không (true/false)
- missing_info: thông tin còn thiếu

Câu hỏi: {question}

Trả về JSON format:
{{
    "intent": "leave",
    "dates": ["10/08", "12/08"],
    "reason": "[Lý do]",
    "user_info": {{"name": "Nguyễn Văn A", "team": "backend_team", "office": "hcm"}},
    "urgency": false,
    "missing_info": ["name", "team"]
}}
"""
        
        response = chatgpt_generate(prompt).strip()
        
        try:
            import json
            result = json.loads(response)
            return result
        except json.JSONDecodeError:
            return {
                "intent": "unknown",
                "dates": [],
                "reason": None,
                "user_info": {},
                "urgency": False,
                "missing_info": []
            }
            
    except Exception as e:
        print(f"[WARNING] LLM analysis failed: {e}")
        return {
            "intent": "unknown",
            "dates": [],
            "reason": None,
            "user_info": {},
            "urgency": False,
            "missing_info": []
        } 