from flask_jwt_extended import (
    create_access_token as jwt_create_access_token,
    create_refresh_token as jwt_create_refresh_token,
)
from models.models_db import Users, UserLogs
from config.database import db
import time
import os

from jose import jwt as jose_jwt
from jose.utils import base64url_decode
import requests
import logging
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
from utils.redis_client import redis_client

import jwt as pyjwt
import os
from functools import wraps
from flask import g, request, jsonify
from models.models_db import Users
from utils.admin.response_utils import api_response
from error.error_codes import ErrorCode



def get_public_keys():
    try:
        response = requests.get(f"{os.getenv('KEYCLOAK_ISSUER')}/protocol/openid-connect/certs")
        return response.json()["keys"]
    except Exception as e:
        logging.error(f"Cannot get JWKS: {e}")
        return []

def decode_token(token):
    """
    Decode SSO JWT token từ Keycloak
    """
    keys = get_public_keys()
    for jwk in keys:
        try:
            public_key = construct_rsa_public_key(jwk)
            payload = jose_jwt.decode(
                token,
                public_key,
                algorithms=["RS256"],
                audience=os.getenv("KEYCLOAK_AUDIENCE"),
                issuer=os.getenv("KEYCLOAK_ISSUER"),
            )
            return payload
        except Exception as e:
            logging.warning(f"Token verification failed with one key: {e}")
            continue
    return None

def construct_rsa_public_key(jwk):
    """
    Convert a JWK key (JSON Web Key) to an RSA public key
    """
    e = base64url_decode(jwk["e"].encode("utf-8"))
    n = base64url_decode(jwk["n"].encode("utf-8"))
    public_numbers = rsa.RSAPublicNumbers(
        int.from_bytes(e, "big"),
        int.from_bytes(n, "big")
    )
    return public_numbers.public_key(backend=default_backend())
def get_email_from_token(token: str) -> str | None:
    keys = get_public_keys()
    for jwk in keys:
        try:
            public_key = construct_rsa_public_key(jwk)
            payload = jose_jwt.decode(
                token,
                public_key,
                algorithms=["RS256"],
                audience=os.getenv("KEYCLOAK_AUDIENCE"),
                issuer=os.getenv("KEYCLOAK_ISSUER"),
            )
            return payload.get("email")
        except Exception as e:
            logging.warning(f"Token verification failed with one key: {e}")
            continue
    return None

def limit_user_logs(email=None, username=None):
    """
    Giới hạn số lượng log đăng nhập cho mỗi user
    """
    from models.models_db import UserLogs
    from config.database import db
    
    if email:
        logs = UserLogs.query.filter_by(email=email).order_by(UserLogs.created_at.desc()).all()
        if len(logs) > 5:
            for log in logs[5:]:
                db.session.delete(log)
            db.session.commit()

def save_token_to_redis(jti, user_id, token_type, ttl_seconds):
    """
    Lưu token vào Redis
    """
    from utils.redis_client import redis_client
    key = f"{token_type}:{user_id}"
    redis_client.setex(key, ttl_seconds, jti)
    
def revoke_tokens(user_id: str):
    redis_client.delete(f"access_token:{user_id}")
    redis_client.delete(f"refresh_token:{user_id}")

def require_admin(f):
    """
    Decorator kiểm tra quyền admin
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = g.user
        if not user:
            return jsonify(api_response(ErrorCode.UNAUTHORIZED, "Authentication required")), 401
        
        if user.get('is_active') is False:
            return jsonify(api_response(ErrorCode.FORBIDDEN, "Tài khoản của bạn đã bị vô hiệu hóa")), 403

        user_role = user.get('role', '').upper()
        print(f"require_admin - User role: {user_role}, Required: ADMIN")
        
        if user_role != 'ADMIN':
            return jsonify(api_response(ErrorCode.FORBIDDEN, "Admin access required")), 403
        
        return f(*args, **kwargs)
    return decorated_function

def require_member_or_admin(f):
    """
    Decorator cho phép cả member và admin
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = g.user
        if not user:
            return jsonify(api_response(ErrorCode.UNAUTHORIZED, "Authentication required")), 401
        
        if user.get('is_active') is False:
            return jsonify(api_response(ErrorCode.FORBIDDEN, "Tài khoản của bạn đã bị vô hiệu hóa")), 403

        user_role = user.get('role', '').upper()
        print(f"require_member_or_admin - User role: {user_role}, Allowed: ['MEMBER', 'ADMIN']")
        
        if user_role not in ['MEMBER', 'ADMIN']:
            return jsonify(api_response(ErrorCode.FORBIDDEN, "Access denied")), 403
        
        return f(*args, **kwargs)
    return decorated_function

def require_permission(permission):
    """
    Decorator kiểm tra permission cụ thể
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user = g.user
            if not user:
                return jsonify(api_response(ErrorCode.UNAUTHORIZED, "Authentication required")), 401
            
            if user.get('role') == 'ADMIN':
                return f(*args, **kwargs)
            
            permissions = user.get('permissions', {})
            if permission not in permissions or not permissions[permission]:
                return jsonify(api_response(ErrorCode.FORBIDDEN, f"Permission '{permission}' required")), 403
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def log_system_action(action, resource_type, resource_id=None, details=None):
    """
    Log các hành động hệ thống
    """
    from models.models_db import SystemLog, db
    from datetime import datetime
    
    try:
        user_id = g.user.get('user_id') if g.user else None
        
        log = SystemLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent'),
            created_at=datetime.now()
        )
        
        db.session.add(log)
        db.session.commit()
        
    except Exception as e:
        print(f"Error logging system action: {e}")
        db.session.rollback()
