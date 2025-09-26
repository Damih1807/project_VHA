import os
import re
import argparse
from pathlib import Path

def remove_hash_comments(content, preserve_shebang=True):
    """
    Xóa các comment bắt đầu bằng
    
    Args:
        content (str): Nội dung file
        preserve_shebang (bool): Giữ lại shebang line (
    
    Returns:
        str: Nội dung đã xóa comments
    """
    lines = content.split('\n')
    cleaned_lines = []
    
    for i, line in enumerate(lines):
        if i == 0 and preserve_shebang and line.startswith('#!'):
            cleaned_lines.append(line)
            continue
            
        comment_pos = find_comment_position(line)
        
        if comment_pos == -1:
            cleaned_lines.append(line)
        elif comment_pos == 0:
            continue
        else:
            code_part = line[:comment_pos].rstrip()
            if code_part:
                cleaned_lines.append(code_part)
    
    return '\n'.join(cleaned_lines)

def find_comment_position(line):
    """
    Tìm vị trí của comment
    
    Returns:
        int: Vị trí của
    """
    in_string = False
    string_char = None
    i = 0
    
    while i < len(line):
        char = line[i]
        
        if char == '\\' and in_string:
            i += 2
            continue
            
        if char in ['"', "'"]:
            if not in_string:
                in_string = True
                string_char = char
            elif char == string_char:
                in_string = False
                string_char = None
        
        elif char == '#' and not in_string:
            return i
            
        i += 1
    
    return -1

def should_process_file(file_path, extensions):
    """
    Kiểm tra xem file có nên được xử lý không
    """
    return file_path.suffix.lower() in extensions

def process_file(file_path, backup=True, preserve_shebang=True):
    """
    Xử lý một file đơn lẻ
    
    Args:
        file_path (Path): Đường dẫn file
        backup (bool): Tạo backup trước khi xử lý
        preserve_shebang (bool): Giữ lại shebang line
    
    Returns:
        bool: True nếu thành công
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            original_content = f.read()
        
        cleaned_content = remove_hash_comments(original_content, preserve_shebang)
        
        if original_content == cleaned_content:
            print(f"✓ {file_path}: No comments to remove")
            return True
        
        if backup:
            backup_path = file_path.with_suffix(file_path.suffix + '.bak')
            with open(backup_path, 'w', encoding='utf-8') as f:
                f.write(original_content)
            print(f"📁 Backup created: {backup_path}")
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(cleaned_content)
        
        print(f"✅ {file_path}: Comments removed successfully")
        return True
        
    except Exception as e:
        print(f"❌ {file_path}: Error - {str(e)}")
        return False

def process_directory(directory_path, extensions, recursive=True, backup=True, preserve_shebang=True):
    """
    Xử lý tất cả files trong thư mục
    
    Args:
        directory_path (Path): Đường dẫn thư mục
        extensions (set): Set các extension cần xử lý
        recursive (bool): Xử lý recursive
        backup (bool): Tạo backup
        preserve_shebang (bool): Giữ lại shebang
    
    Returns:
        tuple: (số file thành công, tổng số file)
    """
    pattern = "**/*" if recursive else "*"
    files = [f for f in directory_path.glob(pattern) if f.is_file() and should_process_file(f, extensions)]
    
    if not files:
        print(f"No files found with extensions {extensions} in {directory_path}")
        return 0, 0
    
    success_count = 0
    total_count = len(files)
    
    print(f"Found {total_count} file(s) to process...")
    print("-" * 50)
    
    for file_path in files:
        if process_file(file_path, backup, preserve_shebang):
            success_count += 1
    
    return success_count, total_count

def main():
    parser = argparse.ArgumentParser(
        description="Remove hash (#) comments from files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python remove_comments.py file.py
  
  python remove_comments.py . --ext .py
  
  python remove_comments.py . --ext .py --recursive --no-backup
  
  python remove_comments.py . --ext .py .sh .conf --recursive
        """
    )
    
    parser.add_argument(
        'path',
        help='File or directory path to process'
    )
    
    parser.add_argument(
        '--ext', '--extensions',
        nargs='+',
        default=['.py'],
        help='File extensions to process (default: .py)'
    )
    
    parser.add_argument(
        '--recursive', '-r',
        action='store_true',
        help='Process directories recursively'
    )
    
    parser.add_argument(
        '--no-backup',
        action='store_true',
        help='Do not create backup files'
    )
    
    parser.add_argument(
        '--no-shebang',
        action='store_true',
        help='Remove shebang lines (#!/usr/bin/env python)'
    )
    
    args = parser.parse_args()
    
    extensions = set(ext if ext.startswith('.') else f'.{ext}' for ext in args.ext)
    
    path = Path(args.path)
    backup = not args.no_backup
    preserve_shebang = not args.no_shebang
    
    if not path.exists():
        print(f"❌ Path does not exist: {path}")
        return 1
    
    print(f"🔧 Comment Remover")
    print(f"Path: {path}")
    print(f"Extensions: {', '.join(extensions)}")
    print(f"Backup: {'Yes' if backup else 'No'}")
    print(f"Preserve shebang: {'Yes' if preserve_shebang else 'No'}")
    print("=" * 50)
    
    if path.is_file():
        if should_process_file(path, extensions):
            success = process_file(path, backup, preserve_shebang)
            return 0 if success else 1
        else:
            print(f"❌ File extension not in allowed list: {path}")
            return 1
    
    elif path.is_dir():
        success_count, total_count = process_directory(
            path, extensions, args.recursive, backup, preserve_shebang
        )
        
        print("-" * 50)
        print(f"✅ Processing complete: {success_count}/{total_count} files successful")
        
        if success_count < total_count:
            print(f"⚠️  {total_count - success_count} files failed")
            return 1
        
        return 0
    
    else:
        print(f"❌ Invalid path type: {path}")
        return 1

if __name__ == "__main__":
    exit(main())