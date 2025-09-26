"""
Email configuration module
"""
import os
from typing import Dict, List, Any

EMAIL_TEMPLATES = {
    "leave": {
        "subject_vi": "ĐƠN XIN NGHỈ PHÉP - {full_name} - {team}",
        "subject_en": "LEAVE REQUEST - {full_name} - {team}",
        "content_vi": """Kính gửi anh George

Cc chị Jasmine, anh Louis, anh Chris

Em là {full_name} thuộc dự án {team}.

Em viết đơn này xin phép anh cho em được nghỉ {leave_days} ngày từ {start_date} đến {end_date}.

Lý do nghỉ phép: {reason}.

Trong thời gian nghỉ phép em sẽ cố gắng hỗ trợ team khi cần thiết ạ.

Em xin cảm ơn anh/chị.

{full_name}""",
        "content_en": """To: George

CC: Jasmine, Louis, Chris

I am {full_name} from {team} project.

I am writing to request {leave_days} days leave from {start_date} to {end_date}.

Reason for leave: {reason}.

During my leave, I will try to support the team when necessary.

Thank you for your consideration.

{full_name}"""
    },
    "quit": {
        "subject_vi": "ĐƠN XIN NGHỈ VIỆC - {full_name}",
        "subject_en": "RESIGNATION REQUEST - {full_name}",
        "content_vi": """Kính gửi anh George

Cc chị Jasmine, anh Louis, anh Chris

Em là {full_name}.

Em viết đơn này xin phép anh cho em được nghỉ việc từ {start_date}.

Lý do: {reason}.

Em sẽ bàn giao công việc và đảm bảo không ảnh hưởng đến tiến độ chung.

Em xin cảm ơn anh/chị.

{full_name}""",
        "content_en": """To: George

CC: Jasmine, Louis, Chris

I am {full_name}.

I am writing to request resignation from {start_date}.

Reason: {reason}.

I will ensure proper handover so the work remains uninterrupted.

Thank you for your consideration.

{full_name}"""
    },
    "ot": {
        "subject_vi": "ĐƠN XIN LÀM THÊM GIỜ - {full_name} - {team}",
        "subject_en": "OVERTIME REQUEST - {full_name} - {team}",
        "content_vi": """Kính gửi anh George

Cc chị Jasmine, anh Louis, anh Chris

Em là {full_name} thuộc dự án {team}.

Em viết đơn này xin phép anh cho em được làm thêm giờ vào ngày {start_date}, từ [GIỜ BẮT ĐẦU] đến [GIỜ KẾT THÚC].

Lý do làm thêm giờ: {reason}.

Em sẽ đảm bảo sức khỏe và chất lượng công việc khi tham gia làm thêm.

Em xin cảm ơn anh/chị.

{full_name}""",
        "content_en": """To: George

CC: Jasmine, Louis, Chris

I am {full_name} from {team} project.

I am writing to request overtime on {start_date}, from [START TIME] to [END TIME].

Reason for overtime: {reason}.

I will ensure my health and work quality during overtime.

Thank you for your consideration.

{full_name}"""
    },
    "remote": {
        "subject_vi": "ĐƠN XIN LÀM VIỆC TỪ XA - {full_name} - {team}",
        "subject_en": "REMOTE WORK REQUEST - {full_name} - {team}",
        "content_vi": """Kính gửi anh George

Cc chị Jasmine, anh Louis, anh Chris

Em là {full_name} thuộc dự án {team}.

Em viết đơn này xin phép anh cho em được làm việc từ xa vào ngày {start_date}.

Lý do làm việc từ xa: {reason}.

Em sẽ đảm bảo hoàn thành công việc đúng tiến độ và luôn sẵn sàng hỗ trợ team khi cần.

Em xin cảm ơn anh/chị.

{full_name}""",
        "content_en": """To: George

CC: Jasmine, Louis, Chris

I am {full_name} from {team} project.

I am writing to request remote work on {start_date}.

Reason for remote work: {reason}.

I will ensure work completion on schedule and be available to support the team when needed.

Thank you for your consideration.

{full_name}"""
    }
}

EMAIL_KEYWORDS = {
    "leave": [
        "xin nghỉ phép", "muốn nghỉ phép", "muốn xin nghỉ phép", "xin phép nghỉ",
        "mail xin nghỉ phép", "email xin nghỉ phép", "viết mail nghỉ phép", 
        "gửi email nghỉ phép", "tạo mail xin nghỉ phép", "tạo email xin nghỉ phép", 
        "giúp tôi tạo đơn xin nghỉ phép", "đơn xin nghỉ phép", "đơn xin phép"
    ],
    "quit": [
        "xin nghỉ việc", "muốn nghỉ việc", "muốn xin nghỉ việc", "xin thôi việc", "thôi việc", "từ chức",
        "mail xin nghỉ việc", "email xin nghỉ việc", "viết mail nghỉ việc", 
        "gửi email nghỉ việc", "tạo mail xin nghỉ việc", "tạo email xin nghỉ việc", 
        "giúp tôi tạo đơn xin nghỉ việc", "đơn xin nghỉ việc", "đơn xin việc"
    ],
    "ot": [
        "xin OT", "muốn xin OT", "muốn làm thêm giờ", "xin làm thêm giờ",
        "mail xin OT", "email xin OT", "viết mail OT", 
        "gửi email OT", "tạo mail xin OT", "tạo email xin OT", "giúp tôi tạo đơn xin OT", 
        "đơn xin OT", "đơn xin OT", 
        "mail xin làm thêm giờ", "email xin làm thêm giờ", "viết mail làm thêm giờ", 
        "gửi email làm thêm giờ", "tạo mail xin làm thêm giờ", "tạo email xin làm thêm giờ", 
        "giúp tôi tạo đơn xin làm thêm giờ", "đơn xin làm thêm giờ", "đơn xin làm thêm giờ"
    ],
    "remote": [
        "xin remote", "muốn xin remote", "muốn làm remote", "xin làm việc từ xa", "work from home", "wfh",
        "remote work", "muốn remote work", "xin remote work", "làm remote work",
        "mail xin làm remote", "email xin làm remote", "viết mail làm remote", 
        "gửi email làm remote", "tạo mail xin làm remote", "tạo email xin làm remote", 
        "giúp tôi tạo đơn xin làm remote", "đơn xin làm remote", "đơn xin làm remote",
        "mail xin làm làm việc từ xa", "email xin làm làm việc từ xa", "viết mail làm làm việc từ xa", 
        "gửi email làm làm việc từ xa", "tạo mail xin làm làm việc từ xa", "tạo email xin làm làm việc từ xa", 
        "giúp tôi tạo đơn xin làm làm việc từ xa", "đơn xin làm làm việc từ xa", "đơn xin làm làm việc từ xa"
    ]
}

DEFAULT_CONTACTS = {
    "george": "george@vinova.com.sg",
    "jasmine": "jasmine@vinova.com.sg", 
    "louis": "louis@vinova.sg",
    "steve": "steve@vinova.com.sg",
    "emerald": "emerald@vinova.com.sg",
    "sunny": "sunny@vinova.com.sg",
    "canary": "canary@vinova.com.sg",
    "cara": "cara@vinova.com.sg",
    "kane": "kane.nguyen@vinova.com.sg"
}

TEAM_STRUCTURE_CONFIG = {
    "hcm": {
        "pm": ["thang", "george"],
        "techlead": ["victor", "louis"],
        "hr": ["jasmine", "kane", "sunny"],
        "cc_office": ["steve", "lucy"]
    },
    "danang": {
        "pm": ["steve", "george"],
        "techlead": ["otto"],
        "hr": ["jasmine", "emerald", "canary", "cara"],
        "cc_office": ["emerald", "canary", "cara"]
    },
    "hanoi": {
        "pm": ["hanoi_pm", "george"],
        "techlead": ["hanoi_tl"],
        "hr": ["jasmine", "kane", "sunny"],
        "cc_office": ["hanoi_cc"]
    }
}

ELEAVE_CONFIG = {
    "url": "https://vinova.hrpartner.io/portal/employee/login",
    "approval_threshold_days": 2,
    "approvers": ["george", "jasmine"],
    "note": "Ngoài ra, bạn cần làm đơn xin nghỉ phép qua hệ thống E-leave tại: {url}\n\nNếu nghỉ từ {threshold} ngày trở lên, cần có sự phê duyệt của {approvers} theo quy định.\n\nChúc bạn thuận lợi!"
}

def get_email_template(template_type: str, lang: str = "vi") -> Dict[str, str]:
    """Get email template by type and language"""
    if template_type not in EMAIL_TEMPLATES:
        raise ValueError(f"Unknown template type: {template_type}")
    
    template = EMAIL_TEMPLATES[template_type]
    return {
        "subject": template[f"subject_{lang}"],
        "content": template[f"content_{lang}"]
    }

def get_keywords_for_type(email_type: str) -> List[str]:
    """Get keywords for email type"""
    return EMAIL_KEYWORDS.get(email_type, [])

def get_contacts() -> Dict[str, str]:
    """Get contact emails - có thể load từ database"""
    return DEFAULT_CONTACTS.copy()

def get_team_structure() -> Dict[str, Dict[str, List[str]]]:
    """Get team structure - có thể load từ database"""
    return TEAM_STRUCTURE_CONFIG.copy() 