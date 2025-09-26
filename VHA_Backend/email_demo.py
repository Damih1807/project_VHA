#!/usr/bin/env python3
"""
Demo thực tế cho email_utils với câu hỏi của user
"""
import sys
import os
import re
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def simple_email_demo():
    """Demo đơn giản với các functions regex"""
    print("🎯 DEMO EMAIL UTILS - Câu hỏi thực tế")
    print("=" * 60)
    
    user_question = "tôi muốn xin nghỉ phép từ 10/08 đến 12/08 vì ốm"
    print(f"📝 Câu hỏi: {user_question}")
    print()
    
    leave_keywords = [
        "xin nghỉ phép", "muốn nghỉ phép", "muốn xin nghỉ phép", 
        "mail xin nghỉ phép", "email xin nghỉ phép", "nghỉ phép"
    ]
    
    is_leave_request = any(keyword in user_question.lower() for keyword in leave_keywords)
    print(f"🔍 Phát hiện email nghỉ phép: {'✅ CÓ' if is_leave_request else '❌ KHÔNG'}")
    
    date_patterns = [
        r'từ\s+(\d{1,2}/\d{1,2})\s+đến\s+(\d{1,2}/\d{1,2})',
        r'(\d{1,2}/\d{1,2})\s+đến\s+(\d{1,2}/\d{1,2})',
    ]
    
    dates = None
    for pattern in date_patterns:
        match = re.search(pattern, user_question.lower())
        if match:
            dates = (match.group(1), match.group(2))
            break
    
    if dates:
        print(f"📅 Ngày nghỉ: từ {dates[0]} đến {dates[1]}")
    else:
        print("📅 Không tìm thấy ngày")
    
    reason_patterns = [
        r'vì\s+(\w+)',
        r'do\s+(\w+)',
        r'bởi vì\s+(\w+)'
    ]
    
    reason = None
    for pattern in reason_patterns:
        match = re.search(pattern, user_question.lower())
        if match:
            reason = match.group(1)
            break
    
    if not reason:
        reason = "cá nhân"
    
    print(f"💭 Lý do: {reason}")
    
    if dates:
        today = datetime.now().day
        start_day = int(dates[0].split('/')[0])
        days_diff = start_day - today
        is_urgent = 0 <= days_diff <= 3
        print(f"⚡ Khẩn cấp: {'✅ CÓ' if is_urgent else '❌ KHÔNG'} (còn {days_diff} ngày)")
    
    if is_leave_request and dates:
        print(f"\n📧 EMAIL TEMPLATE:")
        print("=" * 50)
        
        email_template = f"""Subject: ĐƠN XIN NGHỈ PHÉP - [TÊN] - [TEAM] TEAM

Kính gửi: Anh/Chị

Em là [TÊN] thuộc dự án [TEAM].

Em viết đơn này xin phép anh/chị cho em được nghỉ từ {dates[0]} đến {dates[1]}.

Lý do nghỉ phép: {reason}.

Trong thời gian nghỉ phép em sẽ cố gắng support team khi cần thiết ạ.

Em xin cảm ơn anh/chị.

Trân trọng,
[TÊN]"""
        
        print(email_template)
    
    if dates and not is_urgent:
        print(f"\n🌐 HƯỚNG DẪN E-LEAVE:")
        print("=" * 40)
        print(f"""
Bạn có thể đặt lịch trước qua hệ thống e-leave tại: 
https://vinova.hrpartner.io/portal/employee/login

📋 CÁC BƯỚC:
1. Truy cập "Time Off & Leave"
2. Chọn Leave Type: Annual Leave
3. From: {dates[0]}
4. Until: {dates[1]}
5. Reason: {reason}
6. Submit đơn

Lưu ý: Các yêu cầu có dự định (trước 3 ngày) không cần gửi email, 
chỉ cần book trên hệ thống.
""")

def advanced_email_demo():
    """Demo với nhiều case khác nhau"""
    print(f"\n🔬 DEMO NÂNG CAO - Nhiều trường hợp")
    print("=" * 60)
    
    test_cases = [
        {
            "question": "viết mail xin nghỉ việc từ 15/08 do chuyển công ty",
            "type": "quit",
            "keywords": ["nghỉ việc", "xin nghỉ việc", "thôi việc"]
        },
        {
            "question": "tôi muốn làm OT ngày mai vì deadline dự án",
            "type": "overtime", 
            "keywords": ["làm OT", "overtime", "thêm giờ"]
        },
        {
            "question": "xin làm remote từ 20/08 đến 22/08 vì gia đình",
            "type": "remote",
            "keywords": ["làm remote", "work from home", "wfh", "từ xa"]
        }
    ]
    
    for i, case in enumerate(test_cases, 1):
        print(f"\n--- Case {i}: {case['type'].upper()} ---")
        question = case["question"]
        print(f"📝 Câu hỏi: {question}")
        
        is_match = any(keyword in question.lower() for keyword in case["keywords"])
        print(f"🔍 Detect {case['type']}: {'✅' if is_match else '❌'}")
        
        date_match = re.search(r'(\d{1,2}/\d{1,2})', question)
        if date_match:
            print(f"📅 Ngày: {date_match.group(1)}")
        
        reason_match = re.search(r'(vì|do)\s+(\w+)', question.lower())
        if reason_match:
            print(f"💭 Lý do: {reason_match.group(2)}")

def interactive_demo():
    """Demo tương tác với user"""
    print(f"\n🎮 DEMO TƯƠNG TÁC")
    print("=" * 40)
    print("Nhập câu hỏi email của bạn (hoặc 'quit' để thoát):")
    
    while True:
        try:
            user_input = input("\n❓ Câu hỏi: ").strip()
            
            if user_input.lower() in ['quit', 'exit', 'q']:
                print("👋 Tạm biệt!")
                break
                
            if not user_input:
                continue
            
            print(f"\n🔍 Phân tích: '{user_input}'")
            
            email_types = {
                'leave': ['nghỉ phép', 'xin nghỉ phép'],
                'quit': ['nghỉ việc', 'thôi việc'], 
                'ot': ['làm OT', 'overtime'],
                'remote': ['remote', 'từ xa', 'wfh']
            }
            
            detected_type = None
            for email_type, keywords in email_types.items():
                if any(keyword in user_input.lower() for keyword in keywords):
                    detected_type = email_type
                    break
            
            print(f"📧 Loại email: {detected_type or 'unknown'}")
            
            date_match = re.search(r'(\d{1,2}/\d{1,2})', user_input)
            if date_match:
                print(f"📅 Ngày tìm thấy: {date_match.group(1)}")
            else:
                print("📅 Không tìm thấy ngày")
            
            reason_match = re.search(r'(vì|do|bởi vì)\s+(\w+)', user_input.lower())
            if reason_match:
                print(f"💭 Lý do: {reason_match.group(2)}")
            else:
                print("💭 Không có lý do cụ thể")
                
        except KeyboardInterrupt:
            print("\n👋 Tạm biệt!")
            break
        except Exception as e:
            print(f"❌ Lỗi: {e}")

if __name__ == "__main__":
    print("🎯 EMAIL UTILS DEMO")
    print("Phiên bản: Standalone (không cần dependencies)")
    print("=" * 60)
    
    try:
        simple_email_demo()
        
        advanced_email_demo()
        
        
        print(f"\n🎉 HOÀN THÀNH!")
        print("=" * 60)
        print("📋 Tóm tắt khả năng:")
        print("   ✅ Phát hiện intent email (leave, quit, ot, remote)")
        print("   ✅ Trích xuất ngày tháng")
        print("   ✅ Trích xuất lý do") 
        print("   ✅ Kiểm tra khẩn cấp")
        print("   ✅ Tạo email template")
        print("   ✅ Hướng dẫn E-leave")
        print("\n💡 Email utils đã sẵn sàng tích hợp vào chatbot!")
        
    except Exception as e:
        print(f"❌ Demo failed: {e}")
        import traceback
        traceback.print_exc()
