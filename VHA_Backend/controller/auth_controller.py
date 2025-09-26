import os
from flask import Blueprint, request, jsonify
from models.models_db import Users, UserLogs
from config.database import db
from utils.admin.auth_utils import decode_token, limit_user_logs
from utils.admin.response_utils import api_response, message_response
from error.error_codes import ErrorCode
import uuid
from datetime import datetime, timedelta
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    decode_token as jwt_decode_token,
    get_jwt,
    get_jwt_identity,
    jwt_required,
    verify_jwt_in_request,
)
from utils.admin.auth_utils import save_token_to_redis
from utils.redis_client import redis_client
from models.user_types import UserRole, get_user_role, get_default_permissions

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


@auth_bp.route("/login", methods=["POST"])
def sso_login():
    """
    Đăng nhập SSO
    ---
    tags:
      - Auth
    parameters:
      - name: Authorization
        in: header
        type: string
        required: true
        description: Bearer token
    responses:
      200:
        description: Đăng nhập thành công
      400:
        description: Thiếu thông tin người dùng
      401:
        description: Token không hợp lệ
      500:
        description: Lỗi server
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return jsonify(api_response(ErrorCode.UNAUTHORIZED)), 401

    token = auth_header.split(" ")[1]
    payload = decode_token(token)
    print("Token:", token)
    print("Payload:", payload)

    if not payload:
        return jsonify(api_response(ErrorCode.UNAUTHORIZED)), 401

    sso_id = payload.get("sub")
    email = payload.get("email")
    username = payload.get("preferred_username")
    full_name = payload.get("name")
    jti = payload.get("jti")
    exp = payload.get("exp")

    if not sso_id or not email or not username or not jti or not exp:
        return jsonify(api_response(ErrorCode.BAD_REQUEST, "Missing required user info")), 400

    try:
        user = Users.query.filter_by(sso_id=sso_id).first()

        if not user:
            user = Users.query.filter(
                (Users.email == email) | (Users.username == username)
            ).first()

        if user:
            user.username = username
            user.email = email
            user.full_name = full_name
            user.sso_id = sso_id
            user.last_login = datetime.now()
            message = "User logged in"
        else:
            default_role = UserRole.MEMBER
            default_permissions = get_default_permissions(default_role)
            
            user = Users(
                user_id=str(uuid.uuid4()),
                sso_id=sso_id,
                username=username,
                email=email,
                full_name=full_name,
                role=default_role.value,
                is_active=True,
                permissions=default_permissions
            )
            db.session.add(user)
            message = "New user created"

        db.session.flush()

        refresh_token = create_refresh_token(identity=str(user.user_id))

        limit_user_logs(email=email, username=username)

        log = UserLogs(
            id=str(uuid.uuid4()),
            user_id=user.user_id,
            username=user.username,
            email=user.email,
            full_name=user.full_name,
            is_active=True,
            created_at=datetime.now(),
            refresh_token=refresh_token
        )
        db.session.add(log)

        db.session.commit()

        access_token = create_access_token(
            identity=str(user.user_id),
            expires_delta=timedelta(minutes=int(os.getenv("JWT_ACCESS_TOKEN_EXPIRES"))),
            additional_claims={
                "email": user.email,
                "username": user.username,
                "full_name": user.full_name,
                "role": user.role,
                "permissions": user.permissions or {},
                "is_active": user.is_active
            }
        )

        decoded_access = jwt_decode_token(access_token)
        decoded_refresh = jwt_decode_token(refresh_token)

        save_token_to_redis(decoded_access["jti"], user.user_id, "access_token", ttl_seconds=int(os.getenv("JWT_ACCESS_TOKEN_EXPIRES"))*60)
        save_token_to_redis(decoded_refresh["jti"], user.user_id, "refresh_token", ttl_seconds=604800)

        user_role = get_user_role(user.role)
        
        return jsonify(api_response(ErrorCode.SUCCESS, message, {
            "user": {
                "id": user.user_id,
                "email": user.email,
                "full_name": user.full_name,
                "username": user.username,
                "role": user_role.value,
                "permissions": user.permissions or get_default_permissions(user_role),
                "created_at": user.created_at.isoformat(),
                "is_active": user.is_active
            },
            "token": {
                "access_token": access_token,
                "refresh_token": refresh_token
            }
        })), 200

    except Exception as e:
        db.session.rollback()
        return jsonify(api_response(ErrorCode.SERVER_ERROR, data={"error": str(e)})), 500


@auth_bp.route("/logout", methods=["POST"])
@jwt_required()
def sso_logout():
    """
    Đăng xuất
    ---
    tags:
      - Auth
    security:
      - Bearer: []
    responses:
      200:
        description: Đăng xuất thành công
      400:
        description: Thiếu thông tin người dùng
      404:
        description: Không tìm thấy người dùng
      500:
        description: Lỗi server
    """
    try:
        jwt_payload = get_jwt()
        user_id = get_jwt_identity()
        email = jwt_payload.get("email")
        username = jwt_payload.get("username")

        if not user_id or not email or not username:
            return jsonify(api_response(ErrorCode.BAD_REQUEST, "Missing user info in token")), 400

        user = Users.query.filter_by(user_id=user_id).first()
        if not user:
            return jsonify(api_response(ErrorCode.NOT_FOUND, "User not found")), 404

        all_logs = UserLogs.query.filter_by(email=email, username=username).all()

        if not all_logs:
            return jsonify(api_response(ErrorCode.NOT_FOUND, "No login session found")), 404

        for log in all_logs:
            db.session.delete(log)
        redis_client.delete(f"access_token:{user_id}")
        redis_client.delete(f"refresh_token:{user_id}")

        db.session.commit()
        return jsonify(api_response(ErrorCode.SUCCESS, "User logged out successfully")), 200

    except Exception as e:
        db.session.rollback()
        import traceback
        traceback.print_exc()
        return jsonify(api_response(ErrorCode.SERVER_ERROR, data={"error": str(e)})), 500


@auth_bp.route("/refresh-token", methods=["POST"])
@jwt_required(refresh=True)
def refresh_token():
    try:
        user_id = get_jwt_identity()

        active_log = UserLogs.query.filter_by(user_id=user_id, is_active=True)\
            .order_by(UserLogs.created_at.desc()).first()

        user = Users.query.filter_by(user_id=user_id).first()
        
        new_access_token = create_access_token(
            identity=user_id,
            expires_delta=timedelta(minutes=int(os.getenv("JWT_ACCESS_TOKEN_EXPIRES"))),
            additional_claims={
                "email": active_log.email,
                "username": active_log.username,
                "full_name": getattr(active_log, "full_name", ""),
                "role": user.role if user else "MEMBER",
                "permissions": user.permissions if user else {},
                "is_active": user.is_active if user else True
            }
        )

        decoded_access = jwt_decode_token(new_access_token)
        save_token_to_redis(
            decoded_access["jti"],
            user_id,
            "access_token",
            ttl_seconds=int(os.getenv("JWT_ACCESS_TOKEN_EXPIRES"))*60
        )
        return jsonify(api_response(ErrorCode.SUCCESS, "Token refreshed successfully", {
            "access_token": new_access_token
        })), 200
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify(api_response(ErrorCode.SERVER_ERROR, data={"error": str(e)})), 500





@auth_bp.route("/userinfo", methods=["GET", "OPTIONS"])
def get_user_info():
    if request.method == "OPTIONS":
        return "", 200
    
    try:
        verify_jwt_in_request()
    except:
        return jsonify(api_response(ErrorCode.UNAUTHORIZED, "Invalid token")), 401
    
    user_id = get_jwt_identity()
    jwt_data = get_jwt()
    """
    Lấy thông tin user với format giống Keycloak + role và permissions từ database
    ---
    tags:
      - Auth
    security:
      - Bearer: []
    responses:
      200:
        description: Lấy thông tin user thành công
      401:
        description: Token không hợp lệ
    """
    try:
        user_id = get_jwt_identity()
        jwt_data = get_jwt()
        
        user = Users.query.filter_by(user_id=user_id).first()
        
        if not user:
            return jsonify(api_response(ErrorCode.NOT_FOUND, "User not found")), 404
        
        user_info = {
            "sub": user.user_id,
            "email_verified": True,
            "name": user.full_name,
            "preferred_username": user.username,
            "given_name": user.full_name,
            "email": user.email,
            "role": user.role,
            "permissions": user.permissions or {}
        }
        
        return jsonify(user_info), 200
        
    except Exception as e:
        return jsonify(api_response(ErrorCode.SERVER_ERROR, f"Error retrieving user info: {str(e)}")), 500

@auth_bp.route("/roles", methods=["GET"])
def get_available_roles():
    """
    Lấy danh sách các role có sẵn
    ---
    tags:
      - Auth
    responses:
      200:
        description: Lấy danh sách roles thành công
    """
    try:
        from models.user_types import UserRole
        
        roles = [role.value for role in UserRole]
        
        return jsonify(api_response(ErrorCode.SUCCESS, "Roles retrieved successfully", {
            "roles": roles
        })), 200
        
    except Exception as e:
        return jsonify(api_response(ErrorCode.SERVER_ERROR, f"Error retrieving roles: {str(e)}")), 500


