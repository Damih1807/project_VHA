from flask import request, jsonify, g
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity, get_jwt
from utils.redis_client import redis_client
from utils.admin.response_utils import api_response
from error.error_codes import ErrorCode
from functools import wraps





def require_session(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            verify_jwt_in_request()
            jwt_data = get_jwt()
            user_id = get_jwt_identity()
            jti = jwt_data.get("jti")
            redis_key = f"access_token:{user_id}"
            stored_jti = redis_client.get(redis_key)
            print("Token jti:", jti)
            print("Stored jti from Redis:", stored_jti)

            if stored_jti != jti:
                return jsonify(api_response(ErrorCode.UNAUTHORIZED, "Session expired")), 401

            print("Token jti:", jti)
            print("Stored jti in Redis:", stored_jti)            
            
            from models.models_db import Users
            user = Users.query.filter_by(user_id=user_id).first()
            
            jwt_role = jwt_data.get("role")
            jwt_permissions = jwt_data.get("permissions")
            jwt_is_active = jwt_data.get("is_active")
            
            if user:
                db_role = user.role.upper() if user.role else "MEMBER"
                final_role = jwt_role.upper() if jwt_role else db_role
                
                g.user = {
                    "user_id": user_id,
                    "email": jwt_data.get("email"),
                    "username": jwt_data.get("username"),
                    "full_name": jwt_data.get("full_name"),
                    "role": final_role,
                    "permissions": jwt_permissions if jwt_permissions else (user.permissions or {}),
                    "is_active": jwt_is_active if jwt_is_active is not None else user.is_active
                }
                print(f"User found in DB - Role: {user.role}, JWT Role: {jwt_role}, Final Role: {g.user['role']}")
            else:
                final_role = jwt_role.upper() if jwt_role else "MEMBER"
                g.user = {
                    "user_id": user_id,
                    "email": jwt_data.get("email"),
                    "username": jwt_data.get("username"),
                    "full_name": jwt_data.get("full_name"),
                    "role": final_role,
                    "permissions": jwt_permissions if jwt_permissions else {},
                    "is_active": jwt_is_active if jwt_is_active is not None else True
                }
                print(f"User not found in DB - JWT Role: {jwt_role}, Final Role: {g.user['role']}")

        except Exception as e:
            return jsonify(api_response(ErrorCode.UNAUTHORIZED, "Unauthorized", {"error": str(e)})), 401

        return f(*args, **kwargs)
    return decorated_function

