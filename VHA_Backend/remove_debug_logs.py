#!/usr/bin/env python3
"""
Script để xóa tất cả debug logs không cần thiết để tăng tốc độ hệ thống
"""

import os
import re
import glob

def remove_debug_logs():
    """Xóa tất cả debug logs không cần thiết"""
    
    files_to_process = [
        "utils/user/vector_store_utils.py",
        "utils/admin/response_utils.py", 
        "utils/user/chat_utils.py",
        "utils/user/chitchat_classifier.py",
        "utils/user/enhanced_chitchat_classifier.py",
        "utils/admin/vector_utils.py",
        "controller/file_management_controller.py",
        "controller/chatbot_controller.py",
        "controller/user_controller.py",
        "controller/admin_controller.py"
    ]
    
    debug_patterns = [
        r'print\(f"\[DEBUG\].*?"\)',
        r'print\(f"\[INFO\].*?"\)',
        r'print\(f"\[WARNING\].*?"\)',
        r'print\(f"\[ERROR\].*?"\)',
        r'print\(f"\[PERF\].*?"\)',
    ]
    
    keep_patterns = [
        r'print\(f"\[ERROR\].*?"\)',
        r'print\(f"\[WARNING\].*?No.*?"\)',
        r'print\(f"\[INFO\].*?Loaded.*?"\)',
        r'print\(f"\[INFO\].*?Successfully.*?"\)',
    ]
    
    total_removed = 0
    
    for file_path in files_to_process:
        if not os.path.exists(file_path):
            print(f"⚠️  File không tồn tại: {file_path}")
            continue
            
        print(f"🔍 Xử lý file: {file_path}")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_lines = content.split('\n')
        new_lines = []
        removed_count = 0
        
        for line in original_lines:
            should_keep = False
            
            is_debug = any(re.search(pattern, line) for pattern in debug_patterns)
            
            is_important = any(re.search(pattern, line) for pattern in keep_patterns)
            
            if is_debug and not is_important:
                removed_count += 1
                continue
            else:
                new_lines.append(line)
        
        new_content = '\n'.join(new_lines)
        
        if new_content != content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            print(f"✅ Đã xóa {removed_count} debug logs từ {file_path}")
            total_removed += removed_count
        else:
            print(f"ℹ️  Không có debug logs nào cần xóa trong {file_path}")
    
    print(f"\n🎉 Hoàn thành! Đã xóa tổng cộng {total_removed} debug logs")
    
    optimize_specific_files()
    
def optimize_specific_files():
    """Tối ưu hóa một số file cụ thể"""
    
    response_utils_path = "utils/admin/response_utils.py"
    if os.path.exists(response_utils_path):
        print(f"\n🔧 Tối ưu hóa {response_utils_path}")
        
        with open(response_utils_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        patterns_to_remove = [
            r'print\(f"\[DEBUG\] Extracting references from.*?"\)',
            r'print\(f"\[DEBUG\] Question:.*?"\)',
            r'print\(f"\[DEBUG\] Response:.*?"\)',
            r'print\(f"\[DEBUG\] Database files:"\)',
            r'print\(f"\[DEBUG\] -.*?"\)',
            r'print\(f"\[DEBUG\] Doc \d+ source:.*?"\)',
            r'print\(f"\[DEBUG\] Doc \d+ \(.*?\) scores:"\)',
            r'print\(f"\[DEBUG\]   - Question relevance:.*?"\)',
            r'print\(f"\[DEBUG\]   - Content similarity:.*?"\)',
            r'print\(f"\[DEBUG\]   - Fact similarity:.*?"\)',
            r'print\(f"\[DEBUG\]   - Retrieval score:.*?"\)',
            r'print\(f"\[DEBUG\]   - FINAL usage score:.*?"\)',
            r'print\(f"\[DEBUG\]   - Common facts:.*?"\)',
            r'print\(f"\[DEBUG\] === DOCUMENT RANKING ==="\)',
            r'print\(f"\[DEBUG\] \d+\. .*? - Score:.*?"\)',
            r'print\(f"\[DEBUG\] ✅ SELECTED:.*?"\)',
            r'print\(f"\[DEBUG\] 📋 FALLBACK:.*?"\)',
            r'print\(f"\[DEBUG\] ❌ No documents available.*?"\)',
            r'print\(f"\[DEBUG\] Added single reference:.*?"\)',
            r'print\(f"\[DEBUG\] No documents met criteria.*?"\)',
            r'print\(f"\[DEBUG\] Added fallback reference:.*?"\)',
        ]
        
        for pattern in patterns_to_remove:
            content = re.sub(pattern, '', content)
        
        content = re.sub(r'\n\s*\n\s*\n', '\n\n', content)
        
        with open(response_utils_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"✅ Đã tối ưu hóa {response_utils_path}")
    
    chat_utils_path = "utils/user/chat_utils.py"
    if os.path.exists(chat_utils_path):
        print(f"\n🔧 Tối ưu hóa {chat_utils_path}")
        
        with open(chat_utils_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        patterns_to_remove = [
            r'print\(f"\[INFO\] Processing email workflow"\)',
            r'print\(f"\[INFO\] Unified classification:.*?"\)',
            r'print\(f"\[INFO\] Using FAISS predefined response"\)',
            r'print\(f"\[INFO\] Handling as chitchat"\)',
            r'print\(f"\[INFO\] Context analysis:.*?"\)',
            r'print\(f"\[INFO\] Enhanced question for search:.*?"\)',
            r'print\(f"\[INFO\] Retrieved \d+ documents"\)',
            r'print\(f"\[PERF\] Response generated in.*?"\)',
        ]
        
        for pattern in patterns_to_remove:
            content = re.sub(pattern, '', content)
        
        content = re.sub(r'\n\s*\n\s*\n', '\n\n', content)
        
        with open(chat_utils_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"✅ Đã tối ưu hóa {chat_utils_path}")

def create_backup():
    """Tạo backup trước khi xóa"""
    import shutil
    from datetime import datetime
    
    backup_dir = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    os.makedirs(backup_dir, exist_ok=True)
    
    files_to_backup = [
        "utils/user/vector_store_utils.py",
        "utils/admin/response_utils.py", 
        "utils/user/chat_utils.py",
        "utils/user/chitchat_classifier.py",
        "utils/user/enhanced_chitchat_classifier.py",
        "utils/admin/vector_utils.py",
        "controller/file_management_controller.py",
        "controller/chatbot_controller.py",
        "controller/user_controller.py",
        "controller/admin_controller.py"
    ]
    
    for file_path in files_to_backup:
        if os.path.exists(file_path):
            backup_path = os.path.join(backup_dir, file_path)
            os.makedirs(os.path.dirname(backup_path), exist_ok=True)
            shutil.copy2(file_path, backup_path)
    
    print(f"💾 Đã tạo backup trong thư mục: {backup_dir}")

if __name__ == "__main__":
    print("🚀 Bắt đầu xóa debug logs...")
    
    create_backup()
    
    remove_debug_logs()
    
    print("\n✨ Hoàn thành! Hệ thống sẽ chạy nhanh hơn đáng kể.")
    print("📝 Lưu ý: Backup đã được tạo trong thư mục backup_*")
