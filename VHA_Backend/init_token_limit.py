#!/usr/bin/env python3
"""
Script để khởi tạo và kiểm tra token limit từ Admin Global Settings
"""

import os
import json
from flask import Flask
from models.models_db import db, GlobalConfig
from utils.admin.global_config import get_global_config, set_global_config, initialize_default_global_configs

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:postgres@localhost:5432/vha_db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

def init_and_check_token_limit():
    """Khởi tạo và kiểm tra token limit"""
    print("🔧 Khởi tạo và kiểm tra Token Limit:")
    print("=" * 50)
    
    with app.app_context():
        try:
            initialize_default_global_configs()
            print("✅ Đã khởi tạo default global configs")
            
            system_settings = get_global_config("system_settings")
            if system_settings:
                if isinstance(system_settings, str):
                    try:
                        system_settings = json.loads(system_settings)
                    except:
                        system_settings = {}
                
                max_tokens = system_settings.get("max_tokens_per_day")
                print(f"✅ Token limit từ Admin Settings: {max_tokens}")
                
                print(f"📋 System Settings hiện tại:")
                for key, value in system_settings.items():
                    print(f"   - {key}: {value}")
                    
            else:
                print("❌ Không tìm thấy system_settings")
                
        except Exception as e:
            print(f"❌ Lỗi: {e}")
    
    print("=" * 50)
    print("💡 Lưu ý: Hệ thống giờ chỉ sử dụng Admin Global Settings")
    print("   Không còn fallback về environment variable")

if __name__ == "__main__":
    init_and_check_token_limit()
