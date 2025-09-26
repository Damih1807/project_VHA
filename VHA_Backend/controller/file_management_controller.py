from flask import Blueprint, request, jsonify, g
from datetime import datetime
import uuid
import os
from sqlalchemy import func, desc
from models.models_db import db, FileDocument, Users, SystemLog
from utils.admin.auth_utils import require_admin, require_member_or_admin, log_system_action
from utils.admin.session_utils import require_session
from utils.admin.response_utils import api_response, get_file_info_by_id
from utils.admin.upload_s3_utils import download_from_s3, delete_file_from_registry, delete_file_complete
from utils.admin.vector_utils import (
    advanced_semantic_split,
    create_vector_store,
)
from utils.aws_client import bedrock_client
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.embeddings import BedrockEmbeddings
from error.error_codes import ErrorCode
from urllib.parse import unquote_plus

file_bp = Blueprint("file", __name__, url_prefix="/api/files")

@file_bp.route("/upload", methods=["POST"])
@require_session
@require_admin
def upload_file():
    """
    Upload file PDF để tạo vector store (Admin only)
    ---
    tags:
      - File Management
    consumes:
      - multipart/form-data
    parameters:
      - name: file
        in: formData
        type: file
        required: true
        description: File PDF cần upload
      - name: description
        in: formData
        type: string
        required: false
        description: Mô tả file
      - name: is_public
        in: formData
        type: boolean
        required: false
        description: File có public không
    responses:
      200:
        description: Upload thành công
      400:
        description: Thiếu file
      500:
        description: Lỗi server
    """
    if "file" not in request.files:
        return jsonify(api_response(ErrorCode.BAD_REQUEST, "No file provided")), 400

    try:
        file = request.files["file"]
        description = request.form.get("description", "")
        is_public = request.form.get("is_public", "true").lower() == "true"
        
        if file.filename == "":
            return jsonify(api_response(ErrorCode.BAD_REQUEST, "No file selected")), 400

        file_bytes = file.read()
        original_filename = file.filename
        file_size = len(file_bytes)

        if file_size > 50 * 1024 * 1024:
            return jsonify(api_response(ErrorCode.BAD_REQUEST, "File size too large (max 50MB)")), 400

        base_name = os.path.splitext(original_filename)[0].replace(" ", "_")
        unique_filename = str(uuid.uuid4())

        data_dir = os.getenv("DATA_DIR", "data")
        os.makedirs(data_dir, exist_ok=True)
        local_pdf_path = os.path.join(data_dir, f"{unique_filename}.pdf")

        with open(local_pdf_path, "wb") as f:
            f.write(file_bytes)

        loader = PyPDFLoader(local_pdf_path)
        pages = loader.load_and_split()
        docs = advanced_semantic_split(pages, chunk_size=300, overlap=50)

        final_unique_filename = create_vector_store(
            request_id=unique_filename,
            documents=docs,
            original_filename=original_filename,
            bedrock_embeddings=BedrockEmbeddings(
                model_id=os.getenv("MODEL_ID"),
                client=bedrock_client
            )
        )

        file_doc = FileDocument(
            id=str(uuid.uuid4()),
            file_name=original_filename,
            content_type=file.content_type,
            file_url=f"s3://your-bucket/{final_unique_filename}",
            uploaded_by=g.user.get("user_id"),
            uploaded_at=datetime.now(),
            is_public=is_public,
            file_size=file_size,
            description=description
        )
        
        db.session.add(file_doc)
        db.session.commit()

        log_system_action("CREATE", "FILE", file_doc.id, {
            "filename": original_filename,
            "file_size": file_size,
            "is_public": is_public
        })

        return jsonify(api_response(ErrorCode.SUCCESS, "File uploaded successfully", {
            "file_id": file_doc.id,
            "filename": original_filename,
            "unique_filename": final_unique_filename,
            "file_size": file_size
        })), 200

    except Exception as e:
        db.session.rollback()
        return jsonify(api_response(ErrorCode.SERVER_ERROR, f"Upload failed: {str(e)}")), 500

@file_bp.route("/<string:file_id>", methods=["GET"])
@require_session
@require_member_or_admin
def get_file_info(file_id):
    """
    Lấy thông tin file (Member và Admin)
    ---
    tags:
      - File Management
    parameters:
      - name: file_id
        in: path
        type: string
        required: true
    responses:
      200:
        description: Lấy thông tin file thành công
      404:
        description: File không tồn tại
    """
    file_doc = FileDocument.query.filter_by(id=file_id).first()
    if not file_doc:
        return jsonify(api_response(ErrorCode.NOT_FOUND, "File not found")), 404
    
    user_role = g.user.get("role")
    if user_role != "ADMIN" and not file_doc.is_public:
        return jsonify(api_response(ErrorCode.FORBIDDEN, "Access denied")), 403
    
    file_info = {
        "id": file_doc.id,
        "file_name": file_doc.file_name,
        "content_type": file_doc.content_type,
        "file_size": file_doc.file_size,
        "description": file_doc.description,
        "is_public": file_doc.is_public,
        "uploaded_at": file_doc.uploaded_at.isoformat(),
        "uploaded_by": file_doc.uploaded_by
    }
    
    if user_role == "ADMIN":
        file_info["file_url"] = file_doc.file_url
    
    log_system_action("VIEW", "FILE", file_id)
    
    return jsonify(api_response(ErrorCode.SUCCESS, "File info retrieved successfully", file_info)), 200

@file_bp.route("/<string:file_id>/download", methods=["GET"])
@require_session
@require_admin
def download_file(file_id):
    """
    Download file (Member và Admin)
    ---
    tags:
      - File Management
    parameters:
      - name: file_id
        in: path
        type: string
        required: true
    responses:
      200:
        description: Download thành công
      404:
        description: File không tồn tại
    """
    file_doc = FileDocument.query.filter_by(id=file_id).first()
    if not file_doc:
        return jsonify(api_response(ErrorCode.NOT_FOUND, "File not found")), 404
    
    user_role = g.user.get("role")
    if user_role != "ADMIN" and not file_doc.is_public:
        return jsonify(api_response(ErrorCode.FORBIDDEN, "Access denied")), 403
    
    try:
        file_content = download_pdf_from_s3(file_doc.file_url)
        
        from flask import send_file
        import io
        
        file_obj = io.BytesIO(file_content)
        file_obj.seek(0)
        
        log_system_action("DOWNLOAD", "FILE", file_id)
        
        return send_file(
            file_obj,
            as_attachment=True,
            download_name=file_doc.file_name,
            mimetype=file_doc.content_type
        )
        
    except Exception as e:
        return jsonify(api_response(ErrorCode.SERVER_ERROR, f"Download failed: {str(e)}")), 500

@file_bp.route("/<string:file_id>", methods=["PUT"])
@require_session
@require_admin
def update_file(file_id):
    """
    Cập nhật thông tin file (Admin only)
    ---
    tags:
      - File Management
    parameters:
      - name: file_id
        in: path
        type: string
        required: true
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            description:
              type: string
            is_public:
              type: boolean
    responses:
      200:
        description: Cập nhật thành công
      404:
        description: File không tồn tại
    """
    file_doc = FileDocument.query.filter_by(id=file_id).first()
    if not file_doc:
        return jsonify(api_response(ErrorCode.NOT_FOUND, "File not found")), 404
    
    data = request.get_json()
    old_description = file_doc.description
    old_is_public = file_doc.is_public
    
    if "description" in data:
        file_doc.description = data["description"]
    if "is_public" in data:
        file_doc.is_public = data["is_public"]
    
    db.session.commit()
    
    log_system_action("UPDATE", "FILE", file_id, {
        "old_description": old_description,
        "new_description": file_doc.description,
        "old_is_public": old_is_public,
        "new_is_public": file_doc.is_public
    })
    
    return jsonify(api_response(ErrorCode.SUCCESS, "File updated successfully")), 200

@file_bp.route("/<string:file_id>", methods=["DELETE"])
@require_session
@require_admin
def delete_file(file_id):
    """
    Xóa file (Admin only)
    ---
    tags:
      - File Management
    parameters:
      - name: file_id
        in: path
        type: string
        required: true
    responses:
      200:
        description: Xóa thành công
      404:
        description: File không tồn tại
    """
    file_doc = FileDocument.query.filter_by(id=file_id).first()
    if not file_doc:
        return jsonify(api_response(ErrorCode.NOT_FOUND, "File not found")), 404
    
    try:
        success, message = delete_file_complete(file_doc.file_name)
        
        if success:
            log_system_action("DELETE", "FILE", file_id, {
                "filename": file_doc.file_name,
                "file_size": file_doc.file_size,
                "details": message
            })
            
            return jsonify(api_response(ErrorCode.SUCCESS, "File deleted successfully", {
                "details": message
            })), 200
        else:
            return jsonify(api_response(ErrorCode.SERVER_ERROR, f"Delete failed: {message}")), 500
        
    except Exception as e:
        return jsonify(api_response(ErrorCode.SERVER_ERROR, f"Delete failed: {str(e)}")), 500

@file_bp.route("/list", methods=["GET"])
@require_session
@require_member_or_admin
def list_files():
    """
    Lấy danh sách files (Member và Admin)
    ---
    tags:
      - File Management
    parameters:
      - name: page
        in: query
        type: integer
        required: false
      - name: limit
        in: query
        type: integer
        required: false
      - name: is_public
        in: query
        type: boolean
        required: false
    responses:
      200:
        description: Lấy danh sách thành công
    """
    page = int(request.args.get("page", 1))
    limit = int(request.args.get("limit", 20))
    is_public = request.args.get("is_public")
    
    query = FileDocument.query
    
    user_role = g.user.get("role")
    if user_role != "ADMIN":
        query = query.filter(FileDocument.is_public == True)
    elif is_public is not None:
        is_public_bool = is_public.lower() == 'true'
        query = query.filter(FileDocument.is_public == is_public_bool)
    
    total_count = query.count()
    total_pages = (total_count + limit - 1) // limit
    
    files = query.order_by(FileDocument.uploaded_at.desc()).offset((page - 1) * limit).limit(limit).all()
    
    file_list = []
    for file_doc in files:
        file_info = {
            "id": file_doc.id,
            "file_name": file_doc.file_name,
            "content_type": file_doc.content_type,
            "file_size": file_doc.file_size,
            "description": file_doc.description,
            "is_public": file_doc.is_public,
            "uploaded_at": file_doc.uploaded_at.isoformat()
        }
        
        if user_role == "ADMIN":
            file_info["uploaded_by"] = file_doc.uploaded_by
            file_info["file_url"] = file_doc.file_url
        
        file_list.append(file_info)
    
    log_system_action("VIEW", "FILES", details={"page": page, "limit": limit})
    
    return jsonify(api_response(ErrorCode.SUCCESS, "Files retrieved successfully", {
        "files": file_list,
        "metadata": {
            "page": page,
            "limit": limit,
            "totalPages": total_pages,
            "totalCount": total_count
        }
    })), 200 