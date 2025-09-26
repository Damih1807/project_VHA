#!/usr/bin/env python3
import os
import re
import sys
from pathlib import Path

def remove_all_comments(source_code):
    lines = source_code.split('\n')
    modified_lines = []
    
    in_multiline_string = False
    string_delimiter = None
    
    for line in lines:
        original_line = line
        
        if not in_multiline_string:
            if '"""' in line:
                triple_quote_count = line.count('"""')
                if triple_quote_count % 2 == 1:
                    in_multiline_string = True
                    string_delimiter = '"""'
                    continue
            elif "'''" in line:
                triple_quote_count = line.count("'''")
                if triple_quote_count % 2 == 1:
                    in_multiline_string = True
                    string_delimiter = "'''"
                    continue
        else:
            if string_delimiter in line:
                in_multiline_string = False
                string_delimiter = None
            continue
        
        if in_multiline_string:
            continue
            
        cleaned_line = remove_line_comments(line)
        
        if cleaned_line.strip():
            modified_lines.append(cleaned_line)
    
    return '\n'.join(modified_lines)

def remove_line_comments(line):
    if line.strip().startswith('#'):
        return ""
    
    in_string = False
    string_char = None
    result = ""
    i = 0
    
    while i < len(line):
        char = line[i]
        
        if char in ['"', "'"] and (i == 0 or line[i-1] != '\\'):
            if not in_string:
                in_string = True
                string_char = char
            elif char == string_char:
                in_string = False
                string_char = None
        
        if char == '#' and not in_string:
            break
            
        result += char
        i += 1
    
    return result.rstrip()

def clean_file(file_path):
    try:
        print(f"Cleaning: {file_path}")
        
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        cleaned_content = remove_all_comments(content)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(cleaned_content)
            
        print(f"✅ Done: {file_path}")
        
    except Exception as e:
        print(f"❌ Error: {file_path} - {e}")

def main():
    root_dir = Path(".")
    python_files = list(root_dir.rglob("*.py"))
    
    print(f"Found {len(python_files)} Python files")
    print("=" * 50)
    
    python_files = [f for f in python_files if f.name not in ["clean_comments.py", "clean_comments_v2.py"]]
    
    for file_path in python_files:
        clean_file(file_path)
    
    print("=" * 50)
    print(f"✅ Cleaned {len(python_files)} files")

if __name__ == "__main__":
    main()
