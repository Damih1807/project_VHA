#!/usr/bin/env python3
"""
Fix chat_settings configuration
"""

from app import app
from models.models_db import GlobalConfig
from config.database import db

with app.app_context():
    config = GlobalConfig.query.filter_by(config_key='chat_settings').first()
    if config:
        config.is_active = True
        db.session.commit()
        print("✅ Fixed chat_settings is_active to True")
    else:
        print("❌ chat_settings not found")
    
    all_configs = GlobalConfig.query.all()
    print("\n=== All Configs ===")
    for c in all_configs:
        print(f"Key: {c.config_key}, Active: {c.is_active}, Value: {c.config_value[:50]}...")
