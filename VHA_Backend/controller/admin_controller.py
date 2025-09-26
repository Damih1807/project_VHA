from flask import Blueprint, request, jsonify, g
import json
from datetime import datetime, date, timedelta
import uuid
from sqlalchemy import func, desc, asc, extract
from models.models_db import db, Users, UserLogs, ConversationSession, ConversationLog, TokenUsage, SystemLog
from utils.admin.auth_utils import require_admin, log_system_action
from utils.admin.session_utils import require_session
from utils.admin.response_utils import api_response
from utils.admin.global_config import get_all_global_configs, set_global_config, delete_global_config, get_global_config
from error.error_codes import ErrorCode
from models.user_types import UserRole, get_user_role, get_default_permissions
admin_bp = Blueprint("admin", __name__, url_prefix="/api/admin")

@admin_bp.route("/users", methods=["GET"])
@require_session
@require_admin
def get_all_users():
    """
    Lấy danh sách tất cả users (Admin only)
    ---
    tags:
      - Admin
    parameters:
      - name: page
        in: query
        type: integer
        required: false
      - name: limit
        in: query
        type: integer
        required: false
      - name: role
        in: query
        type: string
        required: false
      - name: is_active
        in: query
        type: boolean
        required: false
    responses:
      200:
        description: Lấy danh sách users thành công
      403:
        description: Không có quyền admin
    """
    page = int(request.args.get("page", 1))
    limit = int(request.args.get("limit", 5))
    role_param = request.args.get("role")
    is_active_param = request.args.get("is_active")
    search = request.args.get("search", "")
    created_from = request.args.get("created_from")
    created_to = request.args.get("created_to")
    last_login_from = request.args.get("last_login_from")
    last_login_to = request.args.get("last_login_to")
    sort_by = request.args.get("sort_by", "created_at").lower()
    sort_order = request.args.get("sort_order", "desc").lower()

    query = Users.query

    if role_param:
        roles = [r.strip().upper() for r in role_param.split(',') if r.strip()]
        if len(roles) == 1:
            query = query.filter(Users.role == roles[0])
        elif len(roles) > 1:
            query = query.filter(Users.role.in_(roles))

    if is_active_param is not None:
        is_active_bool = str(is_active_param).lower() == 'true'
        query = query.filter(Users.is_active == is_active_bool)

    if search:
        like_expr = f"%{search}%"
        query = query.filter(
            (Users.username.ilike(like_expr)) |
            (Users.email.ilike(like_expr)) |
            (Users.full_name.ilike(like_expr))
        )

    try:
        if created_from:
            created_from_dt = datetime.strptime(created_from, "%Y-%m-%d")
            query = query.filter(Users.created_at >= created_from_dt)
        if created_to:
            created_to_dt = datetime.strptime(created_to, "%Y-%m-%d")
            query = query.filter(Users.created_at <= created_to_dt)
    except ValueError:
        return jsonify(api_response(ErrorCode.BAD_REQUEST, "created_from/created_to không hợp lệ. Định dạng phải là YYYY-MM-DD")), 400

    try:
        if last_login_from:
            last_login_from_dt = datetime.strptime(last_login_from, "%Y-%m-%d")
            query = query.filter(Users.last_login >= last_login_from_dt)
        if last_login_to:
            last_login_to_dt = datetime.strptime(last_login_to, "%Y-%m-%d")
            query = query.filter(Users.last_login <= last_login_to_dt)
    except ValueError:
        return jsonify(api_response(ErrorCode.BAD_REQUEST, "last_login_from/last_login_to không hợp lệ. Định dạng phải là YYYY-MM-DD")), 400

    sort_field_map = {
        "created_at": Users.created_at,
        "last_login": Users.last_login,
        "username": Users.username,
        "email": Users.email,
    }
    sort_col = sort_field_map.get(sort_by, Users.created_at)
    order_by_expr = desc(sort_col) if sort_order == "desc" else asc(sort_col)

    total_count = query.count()
    total_pages = (total_count + limit - 1) // limit

    users = query.order_by(order_by_expr).offset((page - 1) * limit).limit(limit).all()
    
    user_list = []
    for user in users:
        today = date.today()
        token_usage = TokenUsage.query.filter_by(user_id=user.user_id, date=today).first()
        used_tokens = token_usage.tokens_used if token_usage else 0
        
        conversation_count = ConversationSession.query.filter_by(user_id=user.user_id).count()
        
        user_role = get_user_role(user.role)
        
        user_list.append({
            "user_id": user.user_id,
            "username": user.username,
            "email": user.email,
            "full_name": user.full_name,
            "role": user_role.value,
            "is_active": user.is_active,
            "last_login": user.last_login.isoformat() if user.last_login else None,
            "created_at": user.created_at.isoformat(),
            "permissions": user.permissions or get_default_permissions(user_role),
            "stats": {
                "used_tokens_today": used_tokens,
                "conversation_count": conversation_count
            }
        })
    
    log_system_action("VIEW", "USERS", details={"page": page, "limit": limit})
    
    return jsonify(api_response(ErrorCode.SUCCESS, "Users retrieved successfully", {
        "users": user_list,
        "metadata": {
            "page": page,
            "limit": limit,
            "totalPages": total_pages,
            "totalCount": total_count,
            "sort_by": sort_by,
            "sort_order": sort_order
        }
    })), 200

@admin_bp.route("/users/<string:user_id>", methods=["GET"])
@require_session
@require_admin
def get_user_detail(user_id):
    """
    Lấy chi tiết user (Admin only)
    ---
    tags:
      - Admin
    parameters:
      - name: user_id
        in: path
        type: string
        required: true
    responses:
      200:
        description: Lấy chi tiết user thành công
      404:
        description: User không tồn tại
    """
    user = Users.query.filter_by(user_id=user_id).first()
    if not user:
        return jsonify(api_response(ErrorCode.NOT_FOUND, "User not found")), 404
    
    today = date.today()
    token_usage = TokenUsage.query.filter_by(user_id=user_id, date=today).first()
    used_tokens = token_usage.tokens_used if token_usage else 0
    
    recent_conversations = ConversationSession.query.filter_by(user_id=user_id)\
        .order_by(ConversationSession.started_at.desc()).limit(5).all()
    
    recent_logs = UserLogs.query.filter_by(user_id=user_id)\
        .order_by(UserLogs.created_at.desc()).limit(5).all()
    
    user_role = get_user_role(user.role)
    
    user_detail = {
         "user_id": user.user_id,
         "username": user.username,
         "email": user.email,
         "full_name": user.full_name,
         "role": user_role.value,
         "is_active": user.is_active,
         "last_login": user.last_login.isoformat() if user.last_login else None,
         "created_at": user.created_at.isoformat(),
         "updated_at": user.updated_at.isoformat(),
         "permissions": user.permissions or get_default_permissions(user_role),
         "stats": {
             "used_tokens_today": used_tokens,
             "conversation_count": ConversationSession.query.filter_by(user_id=user_id).count(),
             "total_logins": UserLogs.query.filter_by(user_id=user_id).count()
         },
         "recent_conversations": [
             {
                 "id": conv.id,
                 "started_at": conv.started_at.isoformat(),
                 "is_active": conv.is_active
             } for conv in recent_conversations
         ],
         "recent_logins": [
             {
                 "id": log.id,
                 "created_at": log.created_at.isoformat(),
                 "is_active": log.is_active
             } for log in recent_logs
         ]
     }
    
    log_system_action("VIEW", "USER", user_id)
    
    return jsonify(api_response(ErrorCode.SUCCESS, "User detail retrieved successfully", user_detail)), 200

@admin_bp.route("/users/<string:user_id>", methods=["PUT"])
@require_session
@require_admin
def update_user(user_id):
    """
    Cập nhật thông tin user (Admin only)
    ---
    tags:
      - Admin
    parameters:
      - name: user_id
        in: path
        type: string
        required: true
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            role:
              type: string
            is_active:
              type: boolean
            permissions:
              type: object
    responses:
      200:
        description: Cập nhật user thành công
      404:
        description: User không tồn tại
    """
    user = Users.query.filter_by(user_id=user_id).first()
    if not user:
        return jsonify(api_response(ErrorCode.NOT_FOUND, "User not found")), 404
    
    data = request.get_json()
    old_role = user.role
    old_is_active = user.is_active
    
    if "role" in data:
        from models.user_types import is_valid_role
        if is_valid_role(data["role"]):
            user.role = data["role"].upper()
        else:
            return jsonify(api_response(ErrorCode.BAD_REQUEST, "Invalid role")), 400
    if "is_active" in data:
        user.is_active = data["is_active"]
    if "permissions" in data:
        from models.user_types import validate_and_merge_permissions, validate_permission_structure, get_user_role
        
        # Validate permission structure
        is_valid, error_msg = validate_permission_structure(data["permissions"])
        if not is_valid:
            return jsonify(api_response(ErrorCode.BAD_REQUEST, f"Invalid permissions: {error_msg}")), 400
        
        # Merge với default permissions cho role hiện tại
        user_role = get_user_role(user.role)
        user.permissions = validate_and_merge_permissions(user_role, data["permissions"])
    
    user.updated_at = datetime.now()
    db.session.commit()
    
    log_system_action("UPDATE", "USER", user_id, {
        "old_role": old_role,
        "new_role": user.role,
        "old_is_active": old_is_active,
        "new_is_active": user.is_active
    })
    
    return jsonify(api_response(ErrorCode.SUCCESS, "User updated successfully")), 200

@admin_bp.route("/users/<string:user_id>", methods=["DELETE"])
@require_session
@require_admin
def delete_user(user_id):
    """
    Xóa user (Admin only)
    ---
    tags:
      - Admin
    parameters:
      - name: user_id
        in: path
        type: string
        required: true
    responses:
      200:
        description: Xóa user thành công
      404:
        description: User không tồn tại
    """
    user = Users.query.filter_by(user_id=user_id).first()
    if not user:
        return jsonify(api_response(ErrorCode.NOT_FOUND, "User not found")), 404
    
    user.is_active = False
    user.updated_at = datetime.now()
    db.session.commit()
    
    log_system_action("DELETE", "USER", user_id, {"username": user.username, "email": user.email})
    
    return jsonify(api_response(ErrorCode.SUCCESS, "User deleted successfully")), 200


@admin_bp.route("/users", methods=["POST"])
@require_session
@require_admin
def create_user():
    """
    Tạo user mới (Admin only)
    ---
    tags:
      - Admin
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - username
            - email
            - full_name
            - role
          properties:
            username:
              type: string
            email:
              type: string
            full_name:
              type: string
            role:
              type: string
            is_active:
              type: boolean
            permissions:
              type: object
    responses:
      201:
        description: Tạo user thành công
      400:
        description: Dữ liệu không hợp lệ
      409:
        description: Username hoặc email đã tồn tại
    """
    data = request.get_json()
    
    # Validate required fields
    required_fields = ["username", "email", "full_name", "role"]
    for field in required_fields:
        if field not in data or not data[field]:
            return jsonify(api_response(ErrorCode.BAD_REQUEST, f"Missing required field: {field}")), 400
    
    # Validate role
    from models.user_types import is_valid_role, get_user_role, validate_and_merge_permissions, validate_permission_structure
    if not is_valid_role(data["role"]):
        return jsonify(api_response(ErrorCode.BAD_REQUEST, "Invalid role")), 400
    
    # Check if user already exists
    existing_user = Users.query.filter(
        (Users.username == data["username"]) | (Users.email == data["email"])
    ).first()
    
    if existing_user:
        return jsonify(api_response(ErrorCode.CONFLICT, "Username or email already exists")), 409
    
    # Validate permissions if provided
    custom_permissions = data.get("permissions")
    if custom_permissions:
        is_valid, error_msg = validate_permission_structure(custom_permissions)
        if not is_valid:
            return jsonify(api_response(ErrorCode.BAD_REQUEST, f"Invalid permissions: {error_msg}")), 400
    
    # Create user with validated permissions
    user_role = get_user_role(data["role"])
    final_permissions = validate_and_merge_permissions(user_role, custom_permissions)
    
    user = Users(
        user_id=str(uuid.uuid4()),
        username=data["username"],
        email=data["email"],
        full_name=data["full_name"],
        role=user_role.value,
        is_active=data.get("is_active", True),
        permissions=final_permissions
    )
    
    db.session.add(user)
    db.session.commit()
    
    log_system_action("CREATE", "USER", user.user_id, {
        "username": user.username,
        "email": user.email,
        "role": user.role
    })
    
    return jsonify(api_response(ErrorCode.SUCCESS, "User created successfully", {
        "user_id": user.user_id,
        "username": user.username,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "is_active": user.is_active,
        "permissions": user.permissions
    })), 201

@admin_bp.route("/users/<string:user_id>/toggle-status", methods=["PATCH"])
@require_session
@require_admin
def toggle_user_status(user_id):
    """Bật/tắt trạng thái hoạt động của user (Admin only)."""
    user = Users.query.filter_by(user_id=user_id).first()
    if not user:
        return jsonify(api_response(ErrorCode.NOT_FOUND, "User not found")), 404

    old_is_active = user.is_active
    user.is_active = not bool(user.is_active)
    user.updated_at = datetime.now()
    db.session.commit()

    log_system_action(
        "UPDATE",
        "USER_TOGGLE_STATUS",
        user_id,
        {"old_is_active": old_is_active, "new_is_active": user.is_active}
    )

    return jsonify(api_response(ErrorCode.SUCCESS, "User status toggled successfully", {
        "user_id": user.user_id,
        "is_active": user.is_active
    })), 200


@admin_bp.route("/stats", methods=["GET"])
@require_session
@require_admin
def get_system_stats():
    """
    Lấy thống kê hệ thống theo thời gian (Admin only)
    ---
    tags:
      - Admin
    parameters:
      - name: group_by
        in: query
        type: string
        enum: [day, month]
        default: day
        description: Nhóm theo ngày hoặc tháng
      - name: start_date
        in: query
        type: string
        format: date
        description: Ngày bắt đầu (YYYY-MM-DD)
      - name: end_date
        in: query
        type: string
        format: date
        description: Ngày kết thúc (YYYY-MM-DD)
    responses:
      200:
        description: Trả về thống kê theo thời gian
      400:
        description: Lỗi đầu vào
    """
    group_by = request.args.get("group_by", "day").lower()
    if group_by not in ["day", "month"]:
        return jsonify(api_response(ErrorCode.BAD_REQUEST, "group_by phải là 'day' hoặc 'month'")), 400

    start_date_str = request.args.get("start_date")
    end_date_str = request.args.get("end_date")

    try:
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date() if start_date_str else date.today()
        end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date() if end_date_str else date.today()
    except ValueError:
        return jsonify(api_response(ErrorCode.BAD_REQUEST, "Ngày không hợp lệ. Định dạng phải là YYYY-MM-DD")), 400

    if group_by == "month":
        user_stats_raw = db.session.query(
            extract("year", Users.created_at).label("year"),
            extract("month", Users.created_at).label("month"),
            func.count(Users.user_id)
        ).filter(
            Users.created_at.between(start_date, end_date)
        ).group_by("year", "month").order_by("year", "month").all()

        user_stats = [
            {"label": f"{int(y)}-{int(m):02d}", "count": int(c)}
            for y, m, c in user_stats_raw
        ]
    else:
        user_stats_raw = db.session.query(
            func.date(Users.created_at).label("day"),
            func.count(Users.user_id)
        ).filter(
            Users.created_at.between(start_date, end_date)
        ).group_by("day").order_by("day").all()

        user_stats = [
            {"label": str(day), "count": int(c)}
            for day, c in user_stats_raw
        ]

    if group_by == "month":
        token_stats_raw = db.session.query(
            extract("year", TokenUsage.date).label("year"),
            extract("month", TokenUsage.date).label("month"),
            func.sum(TokenUsage.tokens_used)
        ).filter(
            TokenUsage.date.between(start_date, end_date)
        ).group_by("year", "month").order_by("year", "month").all()

        token_stats = [
            {"label": f"{int(y)}-{int(m):02d}", "tokens": int(t or 0)}
            for y, m, t in token_stats_raw
        ]
    else:
        token_stats_raw = db.session.query(
            TokenUsage.date,
            func.sum(TokenUsage.tokens_used)
        ).filter(
            TokenUsage.date.between(start_date, end_date)
        ).group_by(TokenUsage.date).order_by(TokenUsage.date).all()

        token_stats = [
            {"label": str(d), "tokens": int(t or 0)}
            for d, t in token_stats_raw
        ]

    if group_by == "month":
        conv_stats_raw = db.session.query(
            extract("year", ConversationSession.started_at).label("year"),
            extract("month", ConversationSession.started_at).label("month"),
            func.count(ConversationSession.id)
        ).filter(
            ConversationSession.started_at.between(start_date, end_date)
        ).group_by("year", "month").order_by("year", "month").all()

        conversations_stats = [
            {"label": f"{int(y)}-{int(m):02d}", "count": int(c)}
            for y, m, c in conv_stats_raw
        ]
    else:
        conv_stats_raw = db.session.query(
            func.date(ConversationSession.started_at).label("day"),
            func.count(ConversationSession.id)
        ).filter(
            ConversationSession.started_at.between(start_date, end_date)
        ).group_by("day").order_by("day").all()

        conversations_stats = [
            {"label": str(day), "count": int(c)}
            for day, c in conv_stats_raw
        ]

    if group_by == "month":
        msg_stats_raw = db.session.query(
            extract("year", ConversationLog.timestamp).label("year"),
            extract("month", ConversationLog.timestamp).label("month"),
            func.count(ConversationLog.id)
        ).filter(
            ConversationLog.timestamp.between(start_date, end_date)
        ).group_by("year", "month").order_by("year", "month").all()

        messages_stats = [
            {"label": f"{int(y)}-{int(m):02d}", "count": int(c)}
            for y, m, c in msg_stats_raw
        ]
    else:
        msg_stats_raw = db.session.query(
            func.date(ConversationLog.timestamp).label("day"),
            func.count(ConversationLog.id)
        ).filter(
            ConversationLog.timestamp.between(start_date, end_date)
        ).group_by("day").order_by("day").all()

        messages_stats = [
            {"label": str(day), "count": int(c)}
            for day, c in msg_stats_raw
        ]

    log_system_action("VIEW", "SYSTEM_STATS_TIME_SERIES")

    stats = {
        "users_over_time": user_stats,
        "tokens_over_time": token_stats,
        "conversations_over_time": conversations_stats,
        "messages_over_time": messages_stats,
        "meta": {
            "group_by": group_by,
            "start_date": str(start_date),
            "end_date": str(end_date)
        }
    }

    return jsonify(api_response(ErrorCode.SUCCESS, "Thống kê theo thời gian thành công", stats)), 200


@admin_bp.route("/system/logs", methods=["GET"])
@require_session
@require_admin
def get_system_logs():
    """
    Lấy system logs (Admin only)
    ---
    tags:
      - Admin
    parameters:
      - name: page
        in: query
        type: integer
        required: false
      - name: limit
        in: query
        type: integer
        required: false
      - name: action
        in: query
        type: string
        required: false
      - name: resource_type
        in: query
        type: string
        required: false
      - name: search
        in: query
        type: string
        required: false
    responses:
      200:
        description: Lấy logs thành công
    """
    page = int(request.args.get("page", 1))
    limit = int(request.args.get("limit", 50))
    action = request.args.get("action")
    resource_type = request.args.get("resource_type")
    search = request.args.get("search", "")
    
    query = SystemLog.query
    
    if action:
        query = query.filter(SystemLog.action == action)
    if resource_type:
        query = query.filter(SystemLog.resource_type == resource_type)
    if search:
        query = query.filter(SystemLog.details.cast(db.String).ilike(f'%{search}%'))
    
    total_count = query.count()
    total_pages = (total_count + limit - 1) // limit
    
    logs = query.order_by(SystemLog.created_at.desc()).offset((page - 1) * limit).limit(limit).all()
    
    log_list = []
    for log in logs:
        user_info = None
        if log.user_id:
            user = Users.query.filter_by(user_id=log.user_id).first()
            if user:
                user_info = {
                    "user_id": user.user_id,
                    "username": user.username,
                    "email": user.email
                }
        
        log_list.append({
            "id": log.id,
            "action": log.action,
            "resource_type": log.resource_type,
            "resource_id": log.resource_id,
            "details": log.details,
            "user": user_info,
            "ip_address": log.ip_address,
            "user_agent": log.user_agent,
            "created_at": log.created_at.isoformat()
        })
    
    log_system_action("VIEW", "SYSTEM_LOGS", details={"page": page, "limit": limit})
    
    return jsonify(api_response(ErrorCode.SUCCESS, "System logs retrieved successfully", {
        "logs": log_list,
        "metadata": {
            "page": page,
            "limit": limit,
            "totalPages": total_pages,
            "totalCount": total_count
        }
    })), 200

@admin_bp.route("/files", methods=["GET"])
@require_session
@require_admin
def get_admin_files():
    """
    Lấy danh sách files cho admin (Admin only)
    ---
    tags:
      - Admin
    parameters:
      - name: page
        in: query
        type: integer
        required: false
      - name: limit
        in: query
        type: integer
        required: false
      - name: search
        in: query
        type: string
        required: false
    responses:
      200:
        description: Lấy danh sách files thành công
      403:
        description: Không có quyền admin
    """
    page = int(request.args.get("page", 1))
    limit = int(request.args.get("limit", 10))
    search = request.args.get("search", "")
    
    from models.models_db import FileDocument
    
    try:
        query = FileDocument.query.filter(FileDocument.file_name.ilike('%.pdf'))
        
        if search:
            query = query.filter(FileDocument.file_name.ilike(f'%{search}%'))
        
        total_count = query.count()
        total_pages = (total_count + limit - 1) // limit
        
        files_data = query.order_by(FileDocument.uploaded_at.desc()).offset((page - 1) * limit).limit(limit).all()
        
        files = []
        for file_doc in files_data:
            files.append({
                "id": file_doc.id,
                "name": file_doc.file_name,
                "size": file_doc.file_size or 0,
                "modified": file_doc.uploaded_at.isoformat() if file_doc.uploaded_at else None,
                "created": file_doc.uploaded_at.isoformat() if file_doc.uploaded_at else None,
                "path": file_doc.file_url,
                "content_type": file_doc.content_type,
                "uploaded_by": file_doc.uploaded_by,
                "is_public": file_doc.is_public,
                "description": file_doc.description
            })
        
        log_system_action("VIEW", "ADMIN_FILES", details={"page": page, "limit": limit, "search": search})
        
        return jsonify(api_response(ErrorCode.SUCCESS, "Files retrieved successfully", {
            "files": files,
            "metadata": {
                "page": page,
                "limit": limit,
                "totalPages": total_pages,
                "totalCount": total_count
            }
        })), 200
        
    except Exception as e:
        log_system_action("ERROR", "ADMIN_FILES", details={"error": str(e)})
        return jsonify(api_response(ErrorCode.INTERNAL_SERVER_ERROR, f"Error retrieving files: {str(e)}")), 500 

@admin_bp.route("/config/global", methods=["GET"])
@require_session
@require_admin
def get_global_configs():
    """
    Lấy tất cả cấu hình toàn cục (Admin only)
    ---
    tags:
      - Admin
    responses:
      200:
        description: Lấy cấu hình thành công
    """
    try:
        configs = get_all_global_configs()
        log_system_action("VIEW", "GLOBAL_CONFIG")
        
        return jsonify(api_response(ErrorCode.SUCCESS, "Global configs retrieved successfully", configs)), 200
    except Exception as e:
        return jsonify(api_response(ErrorCode.SERVER_ERROR, "Failed to retrieve global configs", {
            "error": str(e)
        })), 500


@admin_bp.route("/config/global", methods=["POST"])
@require_session
@require_admin
def create_global_config():
    """
    Tạo cấu hình toàn cục mới (Admin only)
    ---
    tags:
      - Admin
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            config_key:
              type: string
            config_value:
              type: object
            description:
              type: string
    responses:
      200:
        description: Tạo cấu hình thành công
    """
    try:
        data = request.get_json()
        config_key = data.get("config_key")
        config_value = data.get("config_value")
        description = data.get("description", "")
        
        if not config_key or config_value is None:
            return jsonify(api_response(ErrorCode.BAD_REQUEST, "Missing config_key or config_value")), 400

        if isinstance(config_value, str):
            try:
                config_value = json.loads(config_value)
            except Exception:
                return jsonify(api_response(ErrorCode.INVALID_PARAM, "config_value phải là object hoặc JSON string hợp lệ")), 400
        elif not isinstance(config_value, (dict, list)):
            return jsonify(api_response(ErrorCode.INVALID_PARAM, "config_value phải là object")), 400
        
        user_id = g.user.get("user_id") or g.user.get("id")
        
        success = set_global_config(
            config_key=config_key,
            config_value=config_value,
            description=description,
            updated_by=user_id
        )
        
        if success:
            log_system_action("CREATE", "GLOBAL_CONFIG", details={"config_key": config_key})
            return jsonify(api_response(ErrorCode.SUCCESS, "Global config created successfully", {
                "config_key": config_key,
                "config_value": config_value,
                "description": description
            })), 200
        else:
            return jsonify(api_response(ErrorCode.SERVER_ERROR, "Failed to create global config")), 500
            
    except Exception as e:
        return jsonify(api_response(ErrorCode.SERVER_ERROR, "Failed to create global config", {
            "error": str(e)
        })), 500


@admin_bp.route("/config/global/<string:config_key>", methods=["PUT"])
@require_session
@require_admin
def update_global_config(config_key):
    """
    Cập nhật cấu hình toàn cục (Admin only)
    ---
    tags:
      - Admin
    parameters:
      - name: config_key
        in: path
        type: string
        required: true
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            config_value:
              type: object
            description:
              type: string
    responses:
      200:
        description: Cập nhật thành công
    """
    try:
        data = request.get_json()
        config_value = data.get("config_value")
        description = data.get("description")
        
        if config_value is None:
            return jsonify(api_response(ErrorCode.BAD_REQUEST, "Missing config_value")), 400

        if isinstance(config_value, str):
            try:
                config_value = json.loads(config_value)
            except Exception:
                return jsonify(api_response(ErrorCode.INVALID_PARAM, "config_value phải là object hoặc JSON string hợp lệ")), 400
        elif not isinstance(config_value, (dict, list)):
            return jsonify(api_response(ErrorCode.INVALID_PARAM, "config_value phải là object")), 400
        
        user_id = g.user.get("user_id") or g.user.get("id")
        
        success = set_global_config(
            config_key=config_key,
            config_value=config_value,
            description=description,
            updated_by=user_id
        )
        
        if success:
            log_system_action("UPDATE", "GLOBAL_CONFIG", details={"config_key": config_key})
            return jsonify(api_response(ErrorCode.SUCCESS, "Global config updated successfully", {
                "config_key": config_key,
                "config_value": config_value,
                "description": description
            })), 200
        else:
            return jsonify(api_response(ErrorCode.SERVER_ERROR, "Failed to update global config")), 500
            
    except Exception as e:
        return jsonify(api_response(ErrorCode.SERVER_ERROR, "Failed to update global config", {
            "error": str(e)
        })), 500


@admin_bp.route("/config/global/<string:config_key>", methods=["DELETE"])
@require_session
@require_admin
def remove_global_config(config_key):
    """
    Xóa cấu hình toàn cục (Admin only)
    ---
    tags:
      - Admin
    parameters:
      - name: config_key
        in: path
        type: string
        required: true
    responses:
      200:
        description: Xóa thành công
    """
    try:
        success = delete_global_config(config_key)
        
        if success:
            log_system_action("DELETE", "GLOBAL_CONFIG", details={"config_key": config_key})
            return jsonify(api_response(ErrorCode.SUCCESS, "Global config deleted successfully")), 200
        else:
            return jsonify(api_response(ErrorCode.NOT_FOUND, "Global config not found")), 404
            
    except Exception as e:
        return jsonify(api_response(ErrorCode.SERVER_ERROR, "Failed to delete global config", {
            "error": str(e)
        })), 500


@admin_bp.route("/config/global/chat-settings", methods=["GET"])
@require_session
@require_admin
def get_chat_global_config():
    """
    Lấy cấu hình chat toàn cục (Admin only)
    ---
    tags:
      - Admin
    responses:
      200:
        description: Lấy cấu hình thành công
    """
    try:
        chat_config = get_global_config("chat_settings")
        
        if chat_config is None:
            chat_config = {
                "retrieve_k": 15,
                "rerank_k": 5,
                "enable_rerank": True,
                "model": "gpt-4o-mini"
            }
        
        return jsonify(api_response(ErrorCode.SUCCESS, "Chat global config retrieved successfully", chat_config)), 200
    except Exception as e:
        return jsonify(api_response(ErrorCode.SERVER_ERROR, "Failed to retrieve chat global config", {
            "error": str(e)
        })), 500


@admin_bp.route("/config/global/chat-settings", methods=["POST"])
@require_session
@require_admin
def set_chat_global_config():
    """
    Set cấu hình chat toàn cục (Admin only)
    ---
    tags:
      - Admin
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            retrieve_k:
              type: integer
            rerank_k:
              type: integer
            enable_rerank:
              type: boolean
            model:
              type: string
    responses:
      200:
        description: Set cấu hình thành công
    """
    try:
        data = request.get_json()
        retrieve_k = data.get("retrieve_k")
        rerank_k = data.get("rerank_k")
        enable_rerank = data.get("enable_rerank")
        model = data.get("model")
        
        if not isinstance(retrieve_k, int) or not isinstance(rerank_k, int):
            return jsonify(api_response(ErrorCode.INVALID_PARAM, "retrieve_k và rerank_k phải là số")), 400
        if not isinstance(enable_rerank, bool):
            return jsonify(api_response(ErrorCode.INVALID_PARAM, "enable_rerank phải là boolean")), 400
        if not isinstance(model, str):
            return jsonify(api_response(ErrorCode.INVALID_PARAM, "model phải là chuỗi")), 400
        
        user_id = g.user.get("user_id") or g.user.get("id")
        
        chat_config = {
            "retrieve_k": retrieve_k,
            "rerank_k": rerank_k,
            "enable_rerank": enable_rerank,
            "model": model
        }
        
        success = set_global_config(
            config_key="chat_settings",
            config_value=chat_config,
            description="Global chat configuration for all users",
            updated_by=user_id
        )
        
        if success:
            log_system_action("UPDATE", "CHAT_GLOBAL_CONFIG", details=chat_config)
            return jsonify(api_response(ErrorCode.SUCCESS, "Chat global config set successfully")), 200
        else:
            return jsonify(api_response(ErrorCode.SERVER_ERROR, "Failed to set chat global config")), 500
            
    except Exception as e:
        return jsonify(api_response(ErrorCode.SERVER_ERROR, "Failed to set chat global config", {
            "error": str(e)
        })), 500


@admin_bp.route("/config/global/system-settings", methods=["GET"])
@require_session
@require_admin
def get_system_global_config():
    """
    Lấy cấu hình hệ thống (Admin only)
    ---
    tags:
      - Admin
    responses:
      200:
        description: Lấy cấu hình thành công
    """
    try:
        system_config = get_global_config("system_settings")

        if system_config is None:
            system_config = {
                "max_tokens_per_day": 10000,
                "max_conversations_per_user": 50,
                "session_timeout_minutes": 30,
            }

        return jsonify(
            api_response(
                ErrorCode.SUCCESS,
                "System global config retrieved successfully",
                system_config,
            )
        ), 200
    except Exception as e:
        return jsonify(
            api_response(
                ErrorCode.SERVER_ERROR,
                "Failed to retrieve system global config",
                {"error": str(e)},
            )
        ), 500
@admin_bp.route("/config/global/system-settings", methods=["POST"])
@require_session
@require_admin
def set_system_global_config():
    """
    Set cấu hình hệ thống (Admin only)
    ---
    tags:
      - Admin
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            max_tokens_per_day:
              type: integer
            max_conversations_per_user:
              type: integer
            session_timeout_minutes:
              type: integer
    responses:
      200:
        description: Set cấu hình thành công
    """
    try:
        data = request.get_json() or {}

        max_tokens_per_day = data.get("max_tokens_per_day")
        max_conversations_per_user = data.get("max_conversations_per_user")
        session_timeout_minutes = data.get("session_timeout_minutes")

        if not isinstance(max_tokens_per_day, int):
            return (
                jsonify(
                    api_response(
                        ErrorCode.INVALID_PARAM,
                        "max_tokens_per_day phải là số nguyên",
                    )
                ),
                400,
            )
        if not isinstance(max_conversations_per_user, int):
            return (
                jsonify(
                    api_response(
                        ErrorCode.INVALID_PARAM,
                        "max_conversations_per_user phải là số nguyên",
                    )
                ),
                400,
            )
        if not isinstance(session_timeout_minutes, int):
            return (
                jsonify(
                    api_response(
                        ErrorCode.INVALID_PARAM,
                        "session_timeout_minutes phải là số nguyên",
                    )
                ),
                400,
            )

        if max_tokens_per_day <= 0:
            return jsonify(api_response(ErrorCode.INVALID_PARAM, "max_tokens_per_day phải > 0")), 400
        if max_conversations_per_user <= 0:
            return jsonify(api_response(ErrorCode.INVALID_PARAM, "max_conversations_per_user phải > 0")), 400
        if session_timeout_minutes <= 0 or session_timeout_minutes > 24 * 60:
            return jsonify(api_response(ErrorCode.INVALID_PARAM, "session_timeout_minutes phải trong khoảng 1..1440")), 400

        user_id = g.user.get("user_id") or g.user.get("id")

        system_config = {
            "max_tokens_per_day": max_tokens_per_day,
            "max_conversations_per_user": max_conversations_per_user,
            "session_timeout_minutes": session_timeout_minutes,
        }

        success = set_global_config(
            config_key="system_settings",
            config_value=system_config,
            description="Global system configuration",
            updated_by=user_id,
        )

        if success:
            log_system_action("UPDATE", "SYSTEM_GLOBAL_CONFIG", details=system_config)
            return jsonify(api_response(ErrorCode.SUCCESS, "System global config set successfully")), 200
        else:
            return jsonify(api_response(ErrorCode.SERVER_ERROR, "Failed to set system global config")), 500

    except Exception as e:
        return jsonify(
            api_response(
                ErrorCode.SERVER_ERROR,
                "Failed to set system global config",
                {"error": str(e)},
            )
        ), 500

@admin_bp.route("/config/clear-user-configs", methods=["POST"])
@require_session
@require_admin
def clear_all_user_configs():
    """
    Xóa tất cả cấu hình cá nhân của user (Admin only)
    ---
    tags:
      - Admin
    responses:
      200:
        description: Xóa thành công
    """
    try:
        from models.models_db import UserFormConfig
        
        deleted_count = db.session.query(UserFormConfig).delete()
        db.session.commit()
        
        log_system_action("DELETE", "ALL_USER_CONFIGS", details={"deleted_count": deleted_count})
        
        return jsonify(api_response(ErrorCode.SUCCESS, f"Cleared {deleted_count} user configurations successfully")), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify(api_response(ErrorCode.SERVER_ERROR, "Failed to clear user configs", {
            "error": str(e)
        })), 500 

@admin_bp.route("/chat-logs", methods=["GET"])
@require_session
@require_admin
def get_chat_logs_by_topic():
    """
    Lấy log chat và tổng hợp theo chủ đề (Admin only)
    ---
    tags:
      - Admin
    parameters:
      - name: start_date
        in: query
        type: string
        required: false
        description: Ngày bắt đầu (YYYY-MM-DD)
      - name: end_date
        in: query
        type: string
        required: false
        description: Ngày kết thúc (YYYY-MM-DD)
      - name: topic
        in: query
        type: string
        required: false
        description: Lọc theo chủ đề cụ thể
      - name: user_id
        in: query
        type: string
        required: false
        description: Lọc theo user_id
      - name: email
        in: query
        type: string
        required: false
        description: Lọc theo email
      - name: page
        in: query
        type: integer
        required: false
        description: Trang hiện tại
      - name: limit
        in: query
        type: integer
        required: false
        description: Số lượng item mỗi trang
      - name: include_summary
        in: query
        type: boolean
        required: false
        description: Có bao gồm tổng hợp theo chủ đề không (chỉ dựa trên topic đã lưu)
    responses:
      200:
        description: Lấy log chat thành công
      400:
        description: Tham số không hợp lệ
      403:
        description: Không có quyền admin
    """
    try:
        start_date_str = request.args.get("start_date")
        end_date_str = request.args.get("end_date")
        topic_filter = request.args.get("topic")
        user_id_filter = request.args.get("user_id")
        email_filter = request.args.get("email")
        page = int(request.args.get("page", 1))
        limit = int(request.args.get("limit", 20))
        include_summary = request.args.get("include_summary", "true").lower() == "true"

        query = db.session.query(
            ConversationLog.id,
            ConversationLog.con_id,
            ConversationLog.user_id,
            ConversationLog.email,
            ConversationLog.question,
            ConversationLog.answer,
            ConversationLog.timestamp,
            ConversationLog.topic,
            ConversationSession.started_at.label("session_started_at")
        ).join(
            ConversationSession,
            ConversationLog.con_id == ConversationSession.id
        )

        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
                query = query.filter(ConversationLog.timestamp >= start_date)
            except ValueError:
                return jsonify(api_response(ErrorCode.BAD_REQUEST, "start_date không hợp lệ. Định dạng phải là YYYY-MM-DD")), 400

        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, "%Y-%m-%d")
                end_date = end_date + timedelta(days=1)
                query = query.filter(ConversationLog.timestamp < end_date)
            except ValueError:
                return jsonify(api_response(ErrorCode.BAD_REQUEST, "end_date không hợp lệ. Định dạng phải là YYYY-MM-DD")), 400

        if user_id_filter:
            query = query.filter(ConversationLog.user_id == user_id_filter)

        if email_filter:
            query = query.filter(ConversationLog.email.ilike(f"%{email_filter}%"))

        if topic_filter:
            try:
                query = query.filter(func.lower(ConversationLog.topic) == topic_filter.lower())
            except Exception:
                query = query.filter(ConversationLog.topic.ilike(f"%{topic_filter}%"))

        query = query.order_by(ConversationLog.timestamp.desc())

        total_count = query.count()

        offset = (page - 1) * limit
        results = query.offset(offset).limit(limit).all()

        chat_logs = []
        for row in results:
            topic = row.topic
            chat_logs.append({
                "id": row.id,
                "con_id": row.con_id,
                "user_id": row.user_id,
                "email": row.email,
                "question": row.question,
                "answer": row.answer,
                "timestamp": row.timestamp.isoformat() if row.timestamp else None,
                "session_started_at": row.session_started_at.isoformat() if row.session_started_at else None,
                "topic": topic
            })

        response_data = {
            "chat_logs": chat_logs,
            "pagination": {
                "page": page,
                "limit": limit,
                "total_count": total_count,
                "total_pages": (total_count + limit - 1) // limit
            }
        }

        if include_summary:
            topic_summary = get_topic_summary(query)
            response_data["topic_summary"] = topic_summary

        return jsonify(api_response(ErrorCode.SUCCESS, "Chat logs retrieved successfully", response_data)), 200

    except Exception as e:
        return jsonify(api_response(ErrorCode.SERVER_ERROR, "Failed to retrieve chat logs", {
            "error": str(e)
        })), 500

def classify_question_topic(question, use_llm=True):
    """
    Phân loại chủ đề cho câu hỏi
    Sử dụng LLM nếu use_llm=True, ngược lại sử dụng keyword matching
    """
    if use_llm:
        try:
            from utils.user.llm_services import classify_topic_with_llm
            llm_result = classify_topic_with_llm(question, "vi")
            return llm_result['topic']
        except Exception as e:
            print(f"[WARNING] LLM classification failed: {e}, falling back to keyword matching")
            use_llm = False
    
    if not use_llm:
        question_lower = question.lower()
        
        topic_keywords = {
            "nghỉ phép": [
                "chính sách nghỉ phép", "leave", "nghỉ", "phép", "xin nghỉ", "đơn xin nghỉ", "nghỉ năm", 
                "annual leave", "paid leave", "unpaid leave", "nghỉ ốm", "sick leave", "maternity leave", 
                "paternity leave", "compassionate leave", "nghỉ bù", "day off"
            ],
            "làm thêm giờ": [
                "làm thêm giờ", "overtime", "ot", "thêm giờ", "tăng ca", "extra hours", "after hours", 
                "làm ca đêm", "night shift", "ca tối", "weekend work", "holiday work", "double pay"
            ],
            "làm việc từ xa": [
                "làm việc từ xa", "remote", "work from home", "wfh", "từ xa", "telework", "telecommute", 
                "online work", "virtual work", "hybrid work", "offsite work", "remote policy"
            ],
            "nghỉ việc": [
                "nghỉ việc", "quit", "resign", "thôi việc", "xin nghỉ việc", "termination", "end contract", 
                "nghỉ hưu", "retirement", "chấm dứt hợp đồng", "sa thải", "fired", "layoff", "voluntary leave"
            ],
            "quy định": [
                "policy", "quy định", "nội quy", "quy chế", "rules", "regulation", "guidelines", 
                "code of conduct", "standard operating procedure", "SOP", "company policy"
            ],
            "lương thưởng": [
                "chính sách về lương", "lương", "thưởng", "salary", "bonus", "tiền", "lương bổng", 
                "pay", "compensation", "allowance", "phụ cấp", "thu nhập", "payroll", "wage", 
                "commission", "incentive", "13th month salary"
            ],
            "bảo hiểm": [
                "bảo hiểm", "insurance", "bhxh", "bhyt", "bảo hiểm xã hội", "bảo hiểm y tế", 
                "social insurance", "health insurance", "unemployment insurance", "life insurance", 
                "medical coverage", "bảo hiểm thất nghiệp"
            ],
            "đào tạo": [
                "đào tạo", "training", "học", "course", "khóa học", "onboarding", "orientation", 
                "seminar", "workshop", "mentoring", "coaching", "professional development", 
                "technical training", "soft skills training"
            ],
            "công việc": [
                "công việc", "work", "job", "task", "dự án", "project", "assignment", "responsibility", 
                "job description", "JD", "duty", "role", "performance", "KPI", "objective"
            ],
            "chitchat": [
                "xin chào", "hello", "hi", "cảm ơn", "thank", "tạm biệt", "bye", "chào", "good morning", 
                "good afternoon", "good evening", "how are you", "nice to meet you", "see you", 
                "have a nice day"
            ]
        }
        
        for topic, keywords in topic_keywords.items():
            for keyword in keywords:
                if keyword in question_lower:
                    return topic
        
        return "khác"

def get_topic_summary(query):
    """
    Tạo tổng hợp theo chủ đề từ query
    Chỉ sử dụng topic đã lưu trong database, không tự phân loại lại
    """
    try:
        all_results = query.all()
        
        topic_counts = {}
        total_questions = len(all_results)
        
        for row in all_results:
            topic = getattr(row, 'topic', None)
            if not topic:
                topic = 'khác'
            
            topic_counts[topic] = topic_counts.get(topic, 0) + 1
        
        topic_summary = []
        for topic, count in sorted(topic_counts.items(), key=lambda x: x[1], reverse=True):
            percentage = (count / total_questions * 100) if total_questions > 0 else 0
            topic_summary.append({
                "topic": topic,
                "count": count,
                "percentage": round(percentage, 2)
            })
        
        result = {
            "total_questions": total_questions,
            "topics": topic_summary
        }
        
        return result
        
    except Exception as e:
        print(f"Error generating topic summary: {e}")
        return {
            "total_questions": 0,
            "topics": []
        } 

@admin_bp.route("/chat-stats", methods=["GET"])
@require_session
@require_admin
def get_chat_statistics():
    """
    Lấy thống kê tổng quan về chat logs (Admin only)
    ---
    tags:
      - Admin
    parameters:
      - name: start_date
        in: query
        type: string
        required: false
        description: Ngày bắt đầu (YYYY-MM-DD)
      - name: end_date
        in: query
        type: string
        required: false
        description: Ngày kết thúc (YYYY-MM-DD)
      - name: group_by
        in: query
        type: string
        required: false
        description: Nhóm theo (day, week, month)
    responses:
        200:
            description: Lấy thống kê thành công
      400:
        description: Tham số không hợp lệ
      403:
        description: Không có quyền admin
    """
    try:
        start_date_str = request.args.get("start_date")
        end_date_str = request.args.get("end_date")
        group_by = request.args.get("group_by", "day")

        query = db.session.query(ConversationLog)

        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
                query = query.filter(ConversationLog.timestamp >= start_date)
            except ValueError:
                return jsonify(api_response(ErrorCode.BAD_REQUEST, "start_date không hợp lệ. Định dạng phải là YYYY-MM-DD")), 400

        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, "%Y-%m-%d")
                end_date = end_date + timedelta(days=1)
                query = query.filter(ConversationLog.timestamp < end_date)
            except ValueError:
                return jsonify(api_response(ErrorCode.BAD_REQUEST, "end_date không hợp lệ. Định dạng phải là YYYY-MM-DD")), 400

        total_messages = query.count()
        unique_users = query.with_entities(func.count(func.distinct(ConversationLog.user_id))).scalar()
        unique_sessions = query.with_entities(func.count(func.distinct(ConversationLog.con_id))).scalar()

        topic_rows = query.with_entities(ConversationLog.topic).all()
        topic_stats = {}
        for (topic,) in topic_rows:
            topic_key = topic or 'khác'
            topic_stats[topic_key] = topic_stats.get(topic_key, 0) + 1

        sorted_topics = sorted(topic_stats.items(), key=lambda x: x[1], reverse=True)
        top_topics = [{"topic": topic, "count": count} for topic, count in sorted_topics[:5]]

        time_stats = get_time_based_stats(query, group_by)

        top_users = get_top_users(query)

        response_data = {
            "overview": {
                "total_messages": total_messages,
                "unique_users": unique_users,
                "unique_sessions": unique_sessions,
                "avg_messages_per_user": round(total_messages / unique_users, 2) if unique_users > 0 else 0,
                "avg_messages_per_session": round(total_messages / unique_sessions, 2) if unique_sessions > 0 else 0
            },
            "top_topics": top_topics,
            "topic_distribution": topic_stats,
            "time_stats": time_stats,
            "top_users": top_users
        }

        return jsonify(api_response(ErrorCode.SUCCESS, "Chat statistics retrieved successfully", response_data)), 200

    except Exception as e:
        return jsonify(api_response(ErrorCode.SERVER_ERROR, "Failed to retrieve chat statistics", {
            "error": str(e)
        })), 500

def get_time_based_stats(query, group_by):
    """
    Lấy thống kê theo thời gian
    """
    try:
        if group_by == "day":
            time_format = "%Y-%m-%d"
            group_expr = func.date(ConversationLog.timestamp)
        elif group_by == "week":
            time_format = "%Y-W%U"
            group_expr = func.concat(
                func.extract('year', ConversationLog.timestamp),
                '-W',
                func.extract('week', ConversationLog.timestamp)
            )
        elif group_by == "month":
            time_format = "%Y-%m"
            group_expr = func.date_format(ConversationLog.timestamp, '%Y-%m')
        else:
            time_format = "%Y-%m-%d"
            group_expr = func.date(ConversationLog.timestamp)

        time_stats = db.session.query(
            group_expr.label('period'),
            func.count(ConversationLog.id).label('count')
        ).filter(
            query.whereclause
        ).group_by(
            group_expr
        ).order_by(
            group_expr
        ).all()

        return [
            {
                "period": str(row.period),
                "count": row.count
            }
            for row in time_stats
        ]

    except Exception as e:
        print(f"Error getting time-based stats: {e}")
        return []

def get_top_users(query):
    """
    Lấy top users theo số lượng tin nhắn
    """
    try:
        top_users = db.session.query(
            ConversationLog.user_id,
            ConversationLog.email,
            func.count(ConversationLog.id).label('message_count')
        ).filter(
            query.whereclause
        ).group_by(
            ConversationLog.user_id,
            ConversationLog.email
        ).order_by(
            func.count(ConversationLog.id).desc()
        ).limit(10).all()

        return [
            {
                "user_id": row.user_id,
                "email": row.email,
                "message_count": row.message_count
            }
            for row in top_users
        ]

    except Exception as e:
        print(f"Error getting top users: {e}")
        return [] 

@admin_bp.route("/chat-logs/<int:log_id>", methods=["GET"])
@require_session
@require_admin
def get_chat_log_detail(log_id):
    """
    Xem chi tiết một chat log cụ thể (Admin only)
    ---
    tags:
      - Admin
    parameters:
      - name: log_id
        in: path
        type: integer
        required: true
        description: ID của chat log
    responses:
      200:
        description: Lấy chi tiết chat log thành công
      404:
        description: Chat log không tồn tại
      403:
        description: Không có quyền admin
    """
    try:
        chat_log = db.session.query(
            ConversationLog.id,
            ConversationLog.con_id,
            ConversationLog.user_id,
            ConversationLog.email,
            ConversationLog.question,
            ConversationLog.answer,
            ConversationLog.timestamp,
            ConversationLog.topic,
            ConversationSession.started_at.label("session_started_at"),
            ConversationSession.last_asked_at.label("session_last_asked"),
            ConversationSession.is_active.label("session_is_active")
        ).join(
            ConversationSession,
            ConversationLog.con_id == ConversationSession.id
        ).filter(
            ConversationLog.id == log_id
        ).first()

        if not chat_log:
            return jsonify(api_response(ErrorCode.NOT_FOUND, "Chat log not found")), 404

        topic = getattr(chat_log, 'topic', None) or 'khác'

        user_info = None
        if chat_log.user_id:
            user = Users.query.filter_by(user_id=chat_log.user_id).first()
            if user:
                user_info = {
                    "user_id": user.user_id,
                    "username": user.username,
                    "email": user.email,
                    "full_name": user.full_name,
                    "role": user.role,
                    "is_active": user.is_active
                }

        conversation_history = db.session.query(
            ConversationLog.id,
            ConversationLog.question,
            ConversationLog.answer,
            ConversationLog.timestamp
        ).filter(
            ConversationLog.con_id == chat_log.con_id
        ).order_by(
            ConversationLog.timestamp.asc()
        ).all()

        conversation_timeline = []
        for idx, msg in enumerate(conversation_history):
            conversation_timeline.append({
                "id": msg.id,
                "sequence": idx + 1,
                "question": msg.question,
                "answer": msg.answer,
                "timestamp": msg.timestamp.isoformat() if msg.timestamp else None,
                "is_current": msg.id == log_id,
                "topic": msg.topic if hasattr(msg, 'topic') else None
            })

        session_stats = {
            "total_messages": len(conversation_history),
            "session_duration_minutes": 0,
            "topics_covered": list(set([(msg.topic if hasattr(msg, 'topic') and msg.topic else 'khác') for msg in conversation_history]))
        }

        if len(conversation_history) >= 2:
            first_msg = conversation_history[0]
            last_msg = conversation_history[-1]
            if first_msg.timestamp and last_msg.timestamp:
                duration = (last_msg.timestamp - first_msg.timestamp).total_seconds() / 60
                session_stats["session_duration_minutes"] = round(duration, 2)

        response_data = {
            "chat_log": {
                "id": chat_log.id,
                "con_id": chat_log.con_id,
                "user_id": chat_log.user_id,
                "email": chat_log.email,
                "question": chat_log.question,
                "answer": chat_log.answer,
                "timestamp": chat_log.timestamp.isoformat() if chat_log.timestamp else None,
                "topic": topic
            },
            "session_info": {
                "session_id": chat_log.con_id,
                "started_at": chat_log.session_started_at.isoformat() if chat_log.session_started_at else None,
                "last_asked_at": chat_log.session_last_asked.isoformat() if chat_log.session_last_asked else None,
                "is_active": chat_log.session_is_active
            },
            "user_info": user_info,
            "conversation_timeline": conversation_timeline,
            "session_stats": session_stats
        }

        log_system_action("VIEW", "CHAT_LOG_DETAIL", log_id, {
            "con_id": chat_log.con_id,
            "user_id": chat_log.user_id,
            "topic": topic
        })

        return jsonify(api_response(ErrorCode.SUCCESS, "Chat log detail retrieved successfully", response_data)), 200

    except Exception as e:
        return jsonify(api_response(ErrorCode.SERVER_ERROR, "Failed to retrieve chat log detail", {
            "error": str(e)
        })), 500

@admin_bp.route("/chat-logs/<int:log_id>/update", methods=["PUT"])
@require_session
@require_admin
def update_chat_log(log_id):
    """
    Cập nhật chat log (Admin only)
    ---
    tags:
      - Admin
    parameters:
      - name: log_id
        in: path
        type: integer
        required: true
        description: ID của chat log
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            question:
              type: string
            answer:
              type: string
    responses:
      200:
        description: Cập nhật thành công
      404:
        description: Chat log không tồn tại
      400:
        description: Dữ liệu không hợp lệ
      403:
        description: Không có quyền admin
    """
    try:
        chat_log = ConversationLog.query.get(log_id)
        if not chat_log:
            return jsonify(api_response(ErrorCode.NOT_FOUND, "Chat log not found")), 404

        data = request.get_json()
        old_question = chat_log.question
        old_answer = chat_log.answer

        if "question" in data:
            chat_log.question = data["question"].strip()
        if "answer" in data:
            chat_log.answer = data["answer"].strip()

        if not chat_log.question or not chat_log.answer:
            return jsonify(api_response(ErrorCode.BAD_REQUEST, "Question and answer cannot be empty")), 400

        chat_log.timestamp = datetime.now()
        db.session.commit()

        log_system_action("UPDATE", "CHAT_LOG", log_id, {
            "con_id": chat_log.con_id,
            "user_id": chat_log.user_id,
            "old_question": old_question,
            "new_question": chat_log.question,
            "old_answer": old_answer,
            "new_answer": chat_log.answer
        })

        return jsonify(api_response(ErrorCode.SUCCESS, "Chat log updated successfully", {
            "id": chat_log.id,
            "question": chat_log.question,
            "answer": chat_log.answer,
            "timestamp": chat_log.timestamp.isoformat()
        })), 200

    except Exception as e:
        db.session.rollback()
        return jsonify(api_response(ErrorCode.SERVER_ERROR, "Failed to update chat log", {
            "error": str(e)
        })), 500

@admin_bp.route("/chat-logs/<int:log_id>", methods=["DELETE"])
@require_session
@require_admin
def delete_chat_log(log_id):
    """
    Xóa chat log (Admin only)
    ---
    tags:
      - Admin
    parameters:
      - name: log_id
        in: path
        type: integer
        required: true
        description: ID của chat log
    responses:
      200:
        description: Xóa thành công
      404:
        description: Chat log không tồn tại
      403:
        description: Không có quyền admin
    """
    try:
        chat_log = ConversationLog.query.get(log_id)
        if not chat_log:
            return jsonify(api_response(ErrorCode.NOT_FOUND, "Chat log not found")), 404

        log_info = {
            "con_id": chat_log.con_id,
            "user_id": chat_log.user_id,
            "email": chat_log.email,
            "question": chat_log.question,
            "answer": chat_log.answer
        }

        db.session.delete(chat_log)
        db.session.commit()

        log_system_action("DELETE", "CHAT_LOG", log_id, log_info)

        return jsonify(api_response(ErrorCode.SUCCESS, "Chat log deleted successfully")), 200

    except Exception as e:
        db.session.rollback()
        return jsonify(api_response(ErrorCode.SERVER_ERROR, "Failed to delete chat log", {
            "error": str(e)
        })), 500 