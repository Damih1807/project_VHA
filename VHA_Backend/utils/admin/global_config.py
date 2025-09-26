import json
from typing import Dict, Any, Optional
from models.models_db import GlobalConfig
from config.database import db
import config.rerank as rerank


def get_global_config(config_key: str) -> Optional[Any]:
    """Lấy giá trị cấu hình toàn cục"""
    try:
        config = db.session.query(GlobalConfig).filter_by(
            config_key=config_key, 
            is_active=True
        ).first()
        
        if config:
            return json.loads(config.config_value)
        return None
    except Exception as e:
        print(f"[ERROR] Error getting global config {config_key}: {e}")
        return None


def set_global_config(config_key: str, config_value: Any, description: str = None, updated_by: str = None) -> bool:
    """Set giá trị cấu hình toàn cục"""
    try:
        config = db.session.query(GlobalConfig).filter_by(config_key=config_key).first()
        
        if config:
            config.config_value = json.dumps(config_value)
            config.description = description
            config.updated_by = updated_by
            if config.is_active is False:
                config.is_active = True
        else:
            config = GlobalConfig(
                config_key=config_key,
                config_value=json.dumps(config_value),
                description=description,
                updated_by=updated_by
            )
            db.session.add(config)
        
        db.session.commit()
        return True
    except Exception as e:
        print(f"[ERROR] Error setting global config {config_key}: {e}")
        db.session.rollback()
        return False


def get_all_global_configs() -> Dict[str, Any]:
    """Lấy tất cả cấu hình toàn cục"""
    try:
        configs = db.session.query(GlobalConfig).filter_by(is_active=True).all()
        result = {}
        for config in configs:
            result[config.config_key] = {
                "value": json.loads(config.config_value),
                "description": config.description,
                "updated_at": config.updated_at.isoformat() if config.updated_at else None,
                "updated_by": config.updated_by
            }
        return result
    except Exception as e:
        print(f"[ERROR] Error getting all global configs: {e}")
        return {}


def delete_global_config(config_key: str) -> bool:
    """Xóa cấu hình toàn cục (soft delete)"""
    try:
        config = db.session.query(GlobalConfig).filter_by(config_key=config_key).first()
        if config:
            config.is_active = False
            db.session.commit()
            return True
        return False
    except Exception as e:
        print(f"[ERROR] Error deleting global config {config_key}: {e}")
        db.session.rollback()
        return False


def get_effective_config(user_id: str = None) -> Dict[str, Any]:
    """Lấy cấu hình hiệu quả (chỉ sử dụng global config)"""
    default_config = {
        "retrieve_k": 10,
        "rerank_k": rerank.RERANK_TOP_K,
        "enable_rerank": rerank.ENABLE_RERANKER,
        "model": "gpt-4.1-mini"
    }
    
    global_config = get_global_config("chat_settings")
    
    effective_config = default_config.copy()
    
    if global_config:
        effective_config.update(global_config)
    
    return effective_config


def initialize_default_global_configs():
    """Khởi tạo các cấu hình toàn cục mặc định"""
    default_configs = {
        "chat_settings": {
            "retrieve_k": 15,
            "rerank_k": 5,
            "enable_rerank": True,
            "model": "gpt-4o-mini"
        },
        "system_settings": {
            "max_tokens_per_day": 10000,
            "max_conversations_per_user": 50,
            "session_timeout_minutes": 30
        }
    }
    
    for key, value in default_configs.items():
        existing = get_global_config(key)
        if existing is None:
            set_global_config(
                config_key=key,
                config_value=value,
                description=f"Default configuration for {key}"
            )
            print(f"[INFO] Initialized global config: {key}")
