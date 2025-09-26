from flask import Blueprint, request, jsonify, g, redirect, Response
from datetime import datetime
import os
import uuid
from utils.admin.response_utils import api_response, url_response
from utils.admin.vector_utils import (
    advanced_semantic_split,
    create_vector_store,
    list_registry,
    update_file_registry,
)
from utils.admin.auth_utils import decode_token, limit_user_logs
from utils.admin.upload_s3_utils import delete_file_from_registry, delete_file_complete, get_file_name_from_url, read_text_from_url
from utils.user.chat_utils import get_response_from_multiple_sources
from utils.user.email_utils import get_email_content_cache
from utils.user.vector_store_utils import (
    load_multiple_vector_stores,
    get_latest_n_files,
    load_faiss_index
)
from utils.aws_client import bedrock_embeddings
from utils.redis_client import redis_client
from utils.admin.session_utils import require_session
from utils.aws_client import bedrock_client
from models.models_db import db, ConversationLog, Users
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.embeddings import BedrockEmbeddings
from models.models_db import FileDocument
from error.error_codes import ErrorCode
from urllib.parse import unquote_plus
from utils.admin.auth_utils import require_admin, require_member_or_admin

chatbot_bp = Blueprint("chatbot", __name__, url_prefix="/api/chatbot")


@chatbot_bp.route("/upload-pdf", methods=["POST"])
@require_session
@require_admin
def upload_pdf():
    """
    Upload file PDF để tạo vector store
    ---
    tags:
      - Chatbot
    consumes:
      - multipart/form-data
    parameters:
      - name: file
        in: formData
        type: file
        required: true
        description: File PDF cần upload
    responses:
      200:
        description: Upload thành công
      400:
        description: Thiếu file
      500:
        description: Lỗi server
    """
    if "file" not in request.files:
        return jsonify(api_response(ErrorCode.BAD_REQUEST, ErrorCode.get_message(ErrorCode.BAD_REQUEST))), 400

    try:
        file = request.files["file"]
        file_bytes = file.read()
        original_filename = file.filename

        base_name = os.path.splitext(original_filename)[0].replace(" ", "_")
        unique_filename = str(uuid.uuid4())

        pdf_url = None
        try:
            from utils.aws_client import s3_client
            bucket_name_2 = os.getenv("BUCKET_NAME_2")
            print(f"BUCKET_NAME_2: {bucket_name_2}")
            
            if bucket_name_2:
                s3_key = f"{unique_filename}.pdf"
                print(f"Uploading to S3 - Bucket: {bucket_name_2}, Key: {s3_key}")
                
                response = s3_client.put_object(
                    Bucket=bucket_name_2,
                    Key=s3_key,
                    Body=file_bytes,
                    ContentType='application/pdf',
                    ACL='public-read'
                )
                print(f"S3 upload response: {response}")
                
                pdf_url = f"https://{bucket_name_2}.s3.amazonaws.com/{s3_key}"
                print(f"PDF uploaded to S3: {pdf_url}")
            else:
                print("BUCKET_NAME_2 not configured")
                return jsonify(api_response(ErrorCode.SERVER_ERROR, "S3 bucket not configured")), 500
        except Exception as s3_error:
            print(f"Error uploading to S3: {str(s3_error)}")
            print(f"Error type: {type(s3_error)}")
            return jsonify(api_response(ErrorCode.SERVER_ERROR, f"Failed to upload to S3: {str(s3_error)}")), 500
        
        try:
            from models.models_db import FileDocument
            file_doc = FileDocument(
                id=unique_filename,
                file_name=original_filename,
                content_type='application/pdf',
                file_url=pdf_url,
                uploaded_by=g.user.get('user_id'),
                file_size=len(file_bytes),
                description=f"Uploaded via chatbot API - {original_filename}",
                is_public=True
            )
            db.session.add(file_doc)
            db.session.commit()
            print(f"File document saved to database: {unique_filename}")
        except Exception as db_error:
            print(f"Error saving to database: {str(db_error)}")
            try:
                s3_client.delete_object(Bucket=bucket_name_2, Key=s3_key)
                print(f"Cleaned up S3 object: {s3_key}")
            except:
                pass
            return jsonify(api_response(ErrorCode.SERVER_ERROR, f"Failed to save to database: {str(db_error)}")), 500

        try:

            
            s3_response = s3_client.get_object(Bucket=bucket_name_2, Key=s3_key)
            pdf_content = s3_response['Body'].read()
            
            import tempfile
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_file:
                temp_file.write(pdf_content)
                temp_file_path = temp_file.name
            
            try:
                loader = PyPDFLoader(temp_file_path)
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
            finally:
                if os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)
                    
        except Exception as vector_error:
            print(f"Error creating vector store: {str(vector_error)}")
            return jsonify(api_response(ErrorCode.SERVER_ERROR, f"Failed to create vector store: {str(vector_error)}")), 500

        return jsonify(api_response(ErrorCode.SUCCESS, "File uploaded successfully", {
            "unique_filename": final_unique_filename,
            "pdf_url": pdf_url
        })), 200

    except Exception as e:
        return jsonify(api_response(ErrorCode.SERVER_ERROR, ErrorCode.get_message(ErrorCode.SERVER_ERROR), {
            "error": str(e)
        })), 500



@chatbot_bp.route("/files/<filename>", methods=["DELETE"])
@require_session
@require_admin
def delete_file(filename):
    """
    Xóa file đã upload từ database, S3 BUCKET_NAME_2 và S3 BUCKET_NAME
    ---
    tags:
      - Chatbot
    parameters:
      - name: filename
        in: path
        type: string
        required: true
        description: Tên file cần xóa
    responses:
      200:
        description: Xóa file thành công
      404:
        description: Không tìm thấy file
    """
    success, message = delete_file_complete(filename)
    if success:
        return jsonify(api_response(ErrorCode.SUCCESS, f"Deleted file {filename} successfully", {
            "filename": filename,
            "details": message
        })), 200
    else:
        return jsonify(api_response(ErrorCode.NOT_FOUND, f"File {filename} not found or could not be deleted", {
            "error": message
        })), 404


@chatbot_bp.route("/files", methods=["GET"])
@require_session
@require_admin
def get_files():
    """
    Lấy danh sách file đã upload
    ---
    tags:
      - Chatbot
    responses:
      200:
        description: Lấy danh sách file thành công
    """
    files = list_registry()
    return jsonify(api_response(ErrorCode.SUCCESS, "File list retrieved", files)), 200


@chatbot_bp.route("/files/latest", methods=["GET"])
@require_session
@require_member_or_admin    
def list_uploaded_files():
    """
    Lấy danh sách 5 file upload gần nhất
    ---
    tags:
      - Chatbot
    responses:
      200:
        description: Lấy danh sách file gần nhất thành công
      500:
        description: Lỗi server
    """
    try:
        files = get_latest_n_files(n=30)
        result = [
            {
                "original_filename": f["original_filename"],
                "upload_date": f.get("upload_date", "unknown"),
                "unique_filename": f["unique_filename"]
            }
            for f in files
        ]
        return jsonify(api_response(ErrorCode.SUCCESS, "Latest files retrieved", result)), 200
    except Exception as e:
        return jsonify(api_response(ErrorCode.SERVER_ERROR, ErrorCode.get_message(ErrorCode.SERVER_ERROR), {
            "error": str(e)
        })), 500


@chatbot_bp.route("/log", methods=["POST"])
@require_session
@require_member_or_admin
def log_chat():
    """
    Lưu log chat vào hệ thống
    ---
    tags:
      - Chatbot
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            con_id:
              type: string
            question:
              type: string
            answer:
              type: string
    responses:
      200:
        description: Lưu log thành công
      400:
        description: Thiếu trường bắt buộc
      500:
        description: Lỗi server
    """
    try:
        data = request.get_json()
        con_id = data.get("con_id")
        question = data.get("question")
        answer = data.get("answer")
        email = g.user["email"]

        if not all([con_id, email, question, answer]):
            return jsonify(api_response(ErrorCode.BAD_REQUEST, "Missing required fields")), 400

        topic = None
        try:
            from utils.user.llm_services import classify_topic_with_keywords_caching
            topic_result = classify_topic_with_keywords_caching(question, "vi")
            topic = topic_result.get('topic', 'khác')
        except Exception as e:
            print(f"[WARNING] Failed to classify topic for question: {e}")
            topic = 'khác'
        
        new_log = ConversationLog(
            con_id=con_id,
            email=email,
            question=question,
            answer=answer,
            topic=topic,
            timestamp=datetime.now()
        )
        db.session.add(new_log)
        db.session.commit()

        return jsonify(api_response(ErrorCode.SUCCESS, "Chat log saved to PostgreSQL")), 200

    except Exception as e:
        db.session.rollback()
        return jsonify(api_response(ErrorCode.SERVER_ERROR, ErrorCode.get_message(ErrorCode.SERVER_ERROR), {
            "error": str(e)
        })), 500


@chatbot_bp.route("/full_doc", methods=["GET"])
@require_session
@require_member_or_admin
def get_full_doc():
    """
    Lấy toàn bộ nội dung document (dưới dạng các đoạn, mỗi đoạn có section id)
    ---
    tags:
      - Chatbot
    parameters:
      - name: file
        in: query
        type: string
        required: true
        description: unique_filename của file
    responses:
      200:
        description: Trả về toàn bộ nội dung document
      404:
        description: Không tìm thấy file
    """
    unique_filename = request.args.get("file")
    if not unique_filename:
        return jsonify(api_response(ErrorCode.BAD_REQUEST, "Missing file")), 400

    try:
        from utils.user.vector_store_utils import load_faiss_index
        from utils.aws_client import bedrock_embeddings
        vectorstore = load_faiss_index(unique_filename, bedrock_embeddings)
        if not vectorstore:
            return jsonify(api_response(ErrorCode.NOT_FOUND, "File not found")), 404

        docs = vectorstore.docstore._dict.values()
        doc_list = []
        for doc in docs:
            doc_list.append({
                "section": doc.metadata.get("section", ""),
                "content": doc.page_content,
                "metadata": doc.metadata
            })

        return jsonify(api_response(ErrorCode.SUCCESS, "Full document loaded", doc_list)), 200

    except Exception as e:
        return jsonify(api_response(ErrorCode.SERVER_ERROR, "Error loading document", {
            "error": str(e)
        })), 500

@chatbot_bp.route('/file', methods=['POST'])
@require_session
@require_member_or_admin
def create_file():
    """
    Lưu thông tin file (URL + metadata) vào DB
    ---
    requestBody:
      content:
        application/json:
          schema:
            type: object
            properties:
              file_url:
                type: string
              content_type:
                type: string
    """
    data = request.get_json()
    file_url = data.get("file_url")
    content_type = data.get("content_type")

    if not file_url or not content_type:
        return jsonify({"error": "Thiếu file_url hoặc content_type"}), 400
    file_name = unquote_plus(get_file_name_from_url(file_url))
    existing = FileDocument.query.filter_by(file_name=file_name).first()
    if existing:
        return jsonify({
            "message": "File đã tồn tại",
            "id": existing.id,
            "file_url": existing.file_url
        }), 200

    file_doc = FileDocument(
        id=str(uuid.uuid4()),
        file_name=file_name,
        file_url=file_url,
        content_type=content_type
    )
    db.session.add(file_doc)
    db.session.commit()
    return jsonify({
        "message": "Đã lưu file",
        "id": file_doc.id,
        "file_url": file_doc.file_url
    }), 201
    
@chatbot_bp.route('/file/<string:file_id>', methods=['GET'])
@require_session
@require_member_or_admin
def get_file(file_id):
    """
    Lấy thông tin file theo ID từ database
    ---
    parameters:
      - name: file_id
        in: path
        type: string
        required: true
        description: ID của file
    responses:
      200:
        description: File retrieved successfully
      404:
        description: File not found
    """
    try:
        file_doc = FileDocument.query.get(file_id)
        if not file_doc:
            return jsonify(api_response(ErrorCode.NOT_FOUND, "File not found")), 404
        
        file_info = {
            "id": file_doc.id,
            "file_name": file_doc.file_name,
            "file_url": file_doc.file_url,
            "content_type": file_doc.content_type,
            "uploaded_by": file_doc.uploaded_by,
            "uploaded_at": file_doc.uploaded_at.isoformat() if file_doc.uploaded_at else None,
            "is_public": file_doc.is_public,
            "file_size": file_doc.file_size,
            "description": file_doc.description
        }
        
        return jsonify(api_response(ErrorCode.SUCCESS, "File retrieved from database", file_info)), 200
    except Exception as e:
        return jsonify(api_response(ErrorCode.SERVER_ERROR, f"Error retrieving file: {str(e)}")), 500



@chatbot_bp.route('/file/all', methods=['GET'])
@require_session
@require_member_or_admin
def get_all_files():
    """
    Lấy danh sách tất cả các file đã lưu từ database
    ---
    responses:
      200:
        description: Danh sách file
        content:
          application/json:
            schema:
              type: array
              items:
                type: object
                properties:
                  id:
                    type: string
                  file_name:
                    type: string
                  file_url:
                    type: string
                  content_type:
                    type: string
                  uploaded_by:
                    type: string
                  uploaded_at:
                    type: string
                  is_public:
                    type: boolean
                  file_size:
                    type: integer
                  description:
                    type: string
    """
    try:
        files = FileDocument.query.filter(
            FileDocument.file_name.ilike('%.pdf')
        ).all()
        
        data = []
        for f in files:
            file_info = {
                "id": f.id,
                "file_name": f.file_name,
                "file_url": f.file_url,
                "content_type": f.content_type,
                "uploaded_by": f.uploaded_by,
                "uploaded_at": f.uploaded_at.isoformat() if f.uploaded_at else None,
                "is_public": f.is_public,
                "file_size": f.file_size,
                "description": f.description
            }
            data.append(file_info)

        return jsonify(api_response(ErrorCode.SUCCESS, "File list retrieved from database", data)), 200
        
    except Exception as e:
        return jsonify(api_response(ErrorCode.SERVER_ERROR, f"Error retrieving files: {str(e)}")), 500



@chatbot_bp.route("/download-email-txt/<user_id>", methods=["GET"])
@require_session
@require_member_or_admin
def download_email_txt(user_id):
    """
    Download email content dưới dạng file txt
    ---
    tags:
      - Chatbot
    parameters:
      - name: user_id
        in: path
        type: string
        required: true
        description: ID của user
    responses:
      200:
        description: File txt chứa email content
        content:
          text/plain:
            schema:
              type: string
      404:
        description: Không tìm thấy email content
    """
    try:
        email_content = get_email_content_cache(user_id)
        
        if not email_content:
            return api_response(
                success=False,
                message="Không tìm thấy email content cho user này",
                error_code=ErrorCode.NOT_FOUND,
                status_code=404
            )
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"leave_email_{user_id}_{timestamp}.txt"
        
        return Response(
            email_content,
            mimetype='text/plain',
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Content-Type': 'text/plain; charset=utf-8'
            }
        )
        
    except Exception as e:
        return api_response(
            success=False,
            message=f"Lỗi khi download email: {str(e)}",
            error_code=ErrorCode.INTERNAL_ERROR,
            status_code=500
        )


