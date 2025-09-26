
from flask import Blueprint, request, jsonify, g
import json
import os
from datetime import datetime
from werkzeug.utils import secure_filename
from utils.admin.response_utils import api_response
from utils.admin.auth_utils import require_admin
from utils.admin.session_utils import require_session
from error.error_codes import ErrorCode
import shutil

admin_hr_bp = Blueprint("admin_hr", __name__, url_prefix="/api/admin/hr")

# File paths
HR_QUICK_RESPONSES_PATH = os.path.join(os.path.dirname(__file__), '..', 'data_chatting', 'hr_quick_responses.json')
CHITCHAT_DATA_PATH = os.path.join(os.path.dirname(__file__), '..', 'data_chatting', 'enhanced_chitchat_data.json')
HR_TRAINING_DATA_PATH = os.path.join(os.path.dirname(__file__), '..', 'data_chatting', 'hr_training_data.json')

def create_backup(file_path: str) -> str:
    """Create backup of existing file"""
    if os.path.exists(file_path):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = f"{file_path}.backup_{timestamp}"
        shutil.copy2(file_path, backup_path)
        return backup_path
    return None

def validate_hr_quick_responses(data):
    """Validate HR quick responses JSON structure"""
    if not isinstance(data, list):
        return False, "Data must be a list of objects"
    
    required_fields = ['question', 'response']
    optional_fields = ['category']
    
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            return False, f"Item {i} must be an object"
        
        for field in required_fields:
            if field not in item:
                return False, f"Item {i} missing required field: {field}"
            if not isinstance(item[field], str) or not item[field].strip():
                return False, f"Item {i} field '{field}' must be a non-empty string"
        
        # Check for unknown fields
        known_fields = required_fields + optional_fields
        for field in item.keys():
            if field not in known_fields:
                return False, f"Item {i} contains unknown field: {field}"
    
    return True, "Valid"

def validate_chitchat_data(data):
    """Validate chitchat data JSON structure"""
    if not isinstance(data, list):
        return False, "Data must be a list of objects"
    
    required_fields = ['question', 'response']
    
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            return False, f"Item {i} must be an object"
        
        for field in required_fields:
            if field not in item:
                return False, f"Item {i} missing required field: {field}"
            if not isinstance(item[field], str) or not item[field].strip():
                return False, f"Item {i} field '{field}' must be a non-empty string"
    
    return True, "Valid"

@admin_hr_bp.route("/upload-hr-responses", methods=["PATCH"])
@require_session
@require_admin
def upload_hr_responses():
    """
    Upload HR quick responses JSON file
    ---
    tags:
      - Admin HR
    parameters:
      - name: file
        in: formData
        type: file
        required: true
        description: JSON file chứa HR quick responses
      - name: merge_mode
        in: formData
        type: string
        required: false
        description: 'replace' (thay thế hoàn toàn) hoặc 'merge' (gộp với dữ liệu hiện tại)
    responses:
      200:
        description: Upload thành công
      400:
        description: File không hợp lệ
      500:
        description: Lỗi server
    """
    try:
        if 'file' not in request.files:
            return jsonify(api_response(ErrorCode.BAD_REQUEST, "No file uploaded")), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify(api_response(ErrorCode.BAD_REQUEST, "No file selected")), 400
        
        if not file.filename.lower().endswith('.json'):
            return jsonify(api_response(ErrorCode.BAD_REQUEST, "File must be a JSON file")), 400
        
        merge_mode = request.form.get('merge_mode', 'replace')
        if merge_mode not in ['replace', 'merge']:
            return jsonify(api_response(ErrorCode.BAD_REQUEST, "merge_mode must be 'replace' or 'merge'")), 400
        
        # Read and validate JSON
        try:
            file_content = file.read().decode('utf-8')
            new_data = json.loads(file_content)
        except json.JSONDecodeError as e:
            return jsonify(api_response(ErrorCode.BAD_REQUEST, f"Invalid JSON format: {str(e)}")), 400
        except UnicodeDecodeError:
            return jsonify(api_response(ErrorCode.BAD_REQUEST, "File encoding must be UTF-8")), 400
        
        # Validate structure
        is_valid, message = validate_hr_quick_responses(new_data)
        if not is_valid:
            return jsonify(api_response(ErrorCode.BAD_REQUEST, f"Invalid data structure: {message}")), 400
        
        final_data = new_data
        
        # Handle merge mode
        if merge_mode == 'merge' and os.path.exists(HR_QUICK_RESPONSES_PATH):
            try:
                with open(HR_QUICK_RESPONSES_PATH, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
                
                # Merge by adding new items (simple append)
                final_data = existing_data + new_data
                
                # Remove duplicates based on question similarity
                unique_data = []
                seen_questions = set()
                
                for item in final_data:
                    question_key = item['question'].lower().strip()
                    if question_key not in seen_questions:
                        unique_data.append(item)
                        seen_questions.add(question_key)
                
                final_data = unique_data
                
            except Exception as e:
                return jsonify(api_response(ErrorCode.INTERNAL_SERVER_ERROR, f"Failed to merge data: {str(e)}")), 500
        
        # Write new data
        os.makedirs(os.path.dirname(HR_QUICK_RESPONSES_PATH), exist_ok=True)
        with open(HR_QUICK_RESPONSES_PATH, 'w', encoding='utf-8') as f:
            json.dump(final_data, f, ensure_ascii=False, indent=2)
        
        # Clear cache to reload data
        from utils.user.fast_response_utils import fast_response_handler
        fast_response_handler.data_loaded = False
        
        result = {
            "total_items": len(final_data),
            "backup_created": False,
            "merge_mode": merge_mode
        }
        
        return jsonify(api_response(ErrorCode.SUCCESS, "HR responses uploaded successfully", result)), 200
        
    except Exception as e:
        return jsonify(api_response(ErrorCode.INTERNAL_SERVER_ERROR, f"Upload failed: {str(e)}")), 500

@admin_hr_bp.route("/upload-chitchat-data", methods=["PATCH"])
@require_session
@require_admin
def upload_chitchat_data():
    """
    Upload chitchat data JSON file
    ---
    tags:
      - Admin HR
    parameters:
      - name: file
        in: formData
        type: file
        required: true
        description: JSON file chứa chitchat data
      - name: merge_mode
        in: formData
        type: string
        required: false
        description: 'replace' (thay thế hoàn toàn) hoặc 'merge' (gộp với dữ liệu hiện tại)
    responses:
      200:
        description: Upload thành công
      400:
        description: File không hợp lệ
      500:
        description: Lỗi server
    """
    try:
        if 'file' not in request.files:
            return jsonify(api_response(ErrorCode.BAD_REQUEST, "No file uploaded")), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify(api_response(ErrorCode.BAD_REQUEST, "No file selected")), 400
        
        if not file.filename.lower().endswith('.json'):
            return jsonify(api_response(ErrorCode.BAD_REQUEST, "File must be a JSON file")), 400
        
        merge_mode = request.form.get('merge_mode', 'replace')
        if merge_mode not in ['replace', 'merge']:
            return jsonify(api_response(ErrorCode.BAD_REQUEST, "merge_mode must be 'replace' or 'merge'")), 400
        
        # Read and validate JSON
        try:
            file_content = file.read().decode('utf-8')
            new_data = json.loads(file_content)
        except json.JSONDecodeError as e:
            return jsonify(api_response(ErrorCode.BAD_REQUEST, f"Invalid JSON format: {str(e)}")), 400
        except UnicodeDecodeError:
            return jsonify(api_response(ErrorCode.BAD_REQUEST, "File encoding must be UTF-8")), 400
        
        # Validate structure
        is_valid, message = validate_chitchat_data(new_data)
        if not is_valid:
            return jsonify(api_response(ErrorCode.BAD_REQUEST, f"Invalid data structure: {message}")), 400
        
        final_data = new_data
        
        # Handle merge mode
        if merge_mode == 'merge' and os.path.exists(CHITCHAT_DATA_PATH):
            try:
                with open(CHITCHAT_DATA_PATH, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
                
                # Merge by adding new items
                final_data = existing_data + new_data
                
                # Remove duplicates based on question similarity
                unique_data = []
                seen_questions = set()
                
                for item in final_data:
                    question_key = item['question'].lower().strip()
                    if question_key not in seen_questions:
                        unique_data.append(item)
                        seen_questions.add(question_key)
                
                final_data = unique_data
                
            except Exception as e:
                return jsonify(api_response(ErrorCode.INTERNAL_SERVER_ERROR, f"Failed to merge data: {str(e)}")), 500
        
        # Write new data
        os.makedirs(os.path.dirname(CHITCHAT_DATA_PATH), exist_ok=True)
        with open(CHITCHAT_DATA_PATH, 'w', encoding='utf-8') as f:
            json.dump(final_data, f, ensure_ascii=False, indent=2)
        
        # Clear cache to reload data
        from utils.user.fast_response_utils import fast_response_handler
        fast_response_handler.data_loaded = False
        
        result = {
            "total_items": len(final_data),
            "backup_created": False,
            "merge_mode": merge_mode
        }
        
        return jsonify(api_response(ErrorCode.SUCCESS, "Chitchat data uploaded successfully", result)), 200
        
    except Exception as e:
        return jsonify(api_response(ErrorCode.INTERNAL_SERVER_ERROR, f"Upload failed: {str(e)}")), 500

@admin_hr_bp.route("/hr-responses", methods=["GET"])
@require_session
@require_admin
def get_hr_responses():
    """
    Lấy danh sách HR quick responses hiện tại
    ---
    tags:
      - Admin HR
    responses:
      200:
        description: Lấy dữ liệu thành công
      404:
        description: File không tồn tại
      500:
        description: Lỗi server
    """
    try:
        if not os.path.exists(HR_QUICK_RESPONSES_PATH):
            return jsonify(api_response(ErrorCode.NOT_FOUND, "HR responses file not found")), 404
        
        with open(HR_QUICK_RESPONSES_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        result = {
            "total_items": len(data),
            "data": data,
            "file_modified": datetime.fromtimestamp(os.path.getmtime(HR_QUICK_RESPONSES_PATH)).isoformat()
        }
        
        return jsonify(api_response(ErrorCode.SUCCESS, "HR responses retrieved", result)), 200
        
    except Exception as e:
        return jsonify(api_response(ErrorCode.INTERNAL_SERVER_ERROR, f"Failed to get HR responses: {str(e)}")), 500

@admin_hr_bp.route("/chitchat-data", methods=["GET"])
@require_session
@require_admin
def get_chitchat_data():
    """
    Lấy danh sách chitchat data hiện tại
    ---
    tags:
      - Admin HR
    responses:
      200:
        description: Lấy dữ liệu thành công
      404:
        description: File không tồn tại
      500:
        description: Lỗi server
    """
    try:
        if not os.path.exists(CHITCHAT_DATA_PATH):
            return jsonify(api_response(ErrorCode.NOT_FOUND, "Chitchat data file not found")), 404
        
        with open(CHITCHAT_DATA_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        result = {
            "total_items": len(data),
            "data": data,
            "file_modified": datetime.fromtimestamp(os.path.getmtime(CHITCHAT_DATA_PATH)).isoformat()
        }
        
        return jsonify(api_response(ErrorCode.SUCCESS, "Chitchat data retrieved", result)), 200
        
    except Exception as e:
        return jsonify(api_response(ErrorCode.INTERNAL_SERVER_ERROR, f"Failed to get chitchat data: {str(e)}")), 500

@admin_hr_bp.route("/add-hr-response", methods=["POST"])
@require_session
@require_admin
def add_hr_response():
    """
    Thêm một HR response mới
    ---
    tags:
      - Admin HR
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            question:
              type: string
            response:
              type: string
            category:
              type: string
          required: ["question", "response"]
    responses:
      200:
        description: Thêm thành công
      400:
        description: Dữ liệu không hợp lệ
      500:
        description: Lỗi server
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify(api_response(ErrorCode.BAD_REQUEST, "No JSON data provided")), 400
        
        question = data.get('question', '').strip()
        response = data.get('response', '').strip()
        category = data.get('category', '').strip()
        
        if not question or not response:
            return jsonify(api_response(ErrorCode.BAD_REQUEST, "question and response are required")), 400
        
        # Load existing data
        if os.path.exists(HR_QUICK_RESPONSES_PATH):
            with open(HR_QUICK_RESPONSES_PATH, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
        else:
            existing_data = []
        
        # Add new item
        new_item = {
            "question": question,
            "response": response
        }
        if category:
            new_item["category"] = category
        
        existing_data.append(new_item)
        
        # Write updated data
        os.makedirs(os.path.dirname(HR_QUICK_RESPONSES_PATH), exist_ok=True)
        with open(HR_QUICK_RESPONSES_PATH, 'w', encoding='utf-8') as f:
            json.dump(existing_data, f, ensure_ascii=False, indent=2)
        
        # Cập nhật cache để có hiệu lực ngay
        from utils.user.fast_response_utils import fast_response_handler
        try:
            if fast_response_handler.hr_quick_data is None:
                fast_response_handler.hr_quick_data = []
            normalized_new = new_item["question"].strip().lower()
            replaced = False
            for idx, item in enumerate(fast_response_handler.hr_quick_data):
                if isinstance(item, dict) and item.get("question", "").strip().lower() == normalized_new:
                    fast_response_handler.hr_quick_data[idx] = new_item
                    replaced = True
                    break
            if not replaced:
                fast_response_handler.hr_quick_data.append(new_item)
            fast_response_handler.data_loaded = True
        except Exception:
            # Nếu có lỗi khi cập nhật cache, fallback: lần sau sẽ reload từ file
            fast_response_handler.data_loaded = False
        
        result = {
            "total_items": len(existing_data),
            "added_item": new_item,
            "backup_created": False
        }
        
        return jsonify(api_response(ErrorCode.SUCCESS, "HR response added successfully", result)), 200
        
    except Exception as e:
        return jsonify(api_response(ErrorCode.INTERNAL_SERVER_ERROR, f"Failed to add HR response: {str(e)}")), 500

@admin_hr_bp.route("/test-fast-response", methods=["POST"])
@require_session
@require_admin
def test_fast_response():
    """
    Test fast response system
    ---
    tags:
      - Admin HR
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            question:
              type: string
            intent:
              type: string
          required: ["question"]
    responses:
      200:
        description: Test thành công
      400:
        description: Dữ liệu không hợp lệ
      500:
        description: Lỗi server
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify(api_response(ErrorCode.BAD_REQUEST, "No JSON data provided")), 400
        
        question = data.get('question', '').strip()
        intent = data.get('intent', 'hr_inquiry')
        
        if not question:
            return jsonify(api_response(ErrorCode.BAD_REQUEST, "question is required")), 400
        
        # Test fast response
        from utils.user.fast_response_utils import get_immediate_response, is_fast_response_available
        
        is_available = is_fast_response_available(intent)
        fast_response = get_immediate_response(question, intent) if is_available else None
        
        # Also test intent analysis
        from utils.user.email_utils import analyze_intent_with_llm
        try:
            intent_analysis = analyze_intent_with_llm(question, "vi")
            detected_intent = intent_analysis.get('intent', 'unknown')
        except Exception as e:
            detected_intent = f"error: {str(e)}"
        
        result = {
            "question": question,
            "provided_intent": intent,
            "detected_intent": detected_intent,
            "fast_response_available": is_available,
            "fast_response": fast_response,
            "response_found": fast_response is not None
        }
        
        return jsonify(api_response(ErrorCode.SUCCESS, "Fast response test completed", result)), 200
        
    except Exception as e:
        return jsonify(api_response(ErrorCode.INTERNAL_SERVER_ERROR, f"Test failed: {str(e)}")), 500

@admin_hr_bp.route("/reload-data", methods=["POST"])
@require_session
@require_admin
def reload_fast_response_data():
    """
    Reload fast response data from files
    ---
    tags:
      - Admin HR
    responses:
      200:
        description: Reload thành công
      500:
        description: Lỗi server
    """
    try:
        from utils.user.fast_response_utils import fast_response_handler
        
        # Force reload data
        fast_response_handler.data_loaded = False
        fast_response_handler.load_data()
        
        # Get statistics
        hr_count = len(fast_response_handler.hr_quick_data) if fast_response_handler.hr_quick_data else 0
        chitchat_count = len(fast_response_handler.chitchat_data) if fast_response_handler.chitchat_data else 0
        hr_training_count = len(fast_response_handler.hr_data) if fast_response_handler.hr_data else 0
        
        result = {
            "hr_quick_responses": hr_count,
            "chitchat_data": chitchat_count,
            "hr_training_data": hr_training_count,
            "reload_timestamp": datetime.now().isoformat()
        }
        
        return jsonify(api_response(ErrorCode.SUCCESS, "Fast response data reloaded successfully", result)), 200
        
    except Exception as e:
        return jsonify(api_response(ErrorCode.INTERNAL_SERVER_ERROR, f"Reload failed: {str(e)}")), 500

@admin_hr_bp.route("/delete-hr-response", methods=["DELETE"])
@require_session
@require_admin
def delete_hr_response():
    """
    Xóa một HR response theo question hoặc index
    ---
    tags:
      - Admin HR
    parameters:
      - name: index
        in: query
        type: integer
        required: false
        description: Index của item cần xóa (0-based)
      - name: body
        in: body
        required: false
        schema:
          type: object
          properties:
            question:
              type: string
              description: Câu hỏi cần xóa (phải khớp chính xác)
          required: ["question"]
    responses:
      200:
        description: Xóa thành công
      400:
        description: Dữ liệu không hợp lệ
      404:
        description: Không tìm thấy câu hỏi hoặc index không hợp lệ
      500:
        description: Lỗi server
    """
    try:
        # Check for index parameter first (for Frontend compatibility)
        index_param = request.args.get('index')
        if index_param is not None:
            try:
                index = int(index_param)
                if index < 0:
                    return jsonify(api_response(ErrorCode.BAD_REQUEST, "Index must be non-negative")), 400
            except ValueError:
                return jsonify(api_response(ErrorCode.BAD_REQUEST, "Index must be a valid integer")), 400
            
            # Load existing data
            if not os.path.exists(HR_QUICK_RESPONSES_PATH):
                return jsonify(api_response(ErrorCode.NOT_FOUND, "HR responses file not found")), 404
            
            with open(HR_QUICK_RESPONSES_PATH, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
            
            # Check if index is valid
            if index >= len(existing_data):
                return jsonify(api_response(ErrorCode.NOT_FOUND, f"Index {index} is out of range. Total items: {len(existing_data)}")), 404
            
            # Remove item by index
            original_count = len(existing_data)
            deleted_item = existing_data.pop(index)
            
            # Create backup
            backup_path = create_backup(HR_QUICK_RESPONSES_PATH)
            
            # Write updated data
            with open(HR_QUICK_RESPONSES_PATH, 'w', encoding='utf-8') as f:
                json.dump(existing_data, f, ensure_ascii=False, indent=2)
            
            # Clear cache
            from utils.user.fast_response_utils import fast_response_handler
            fast_response_handler.data_loaded = False
            
            result = {
                "total_items": len(existing_data),
                "deleted_item": deleted_item,
                "backup_created": backup_path is not None,
                "items_removed": original_count - len(existing_data),
                "deleted_index": index
            }
            
            if backup_path:
                result["backup_path"] = os.path.basename(backup_path)
            
            return jsonify(api_response(ErrorCode.SUCCESS, "HR response deleted successfully", result)), 200
        
        # Fallback to JSON body method
        data = request.get_json()
        if not data:
            return jsonify(api_response(ErrorCode.BAD_REQUEST, "No JSON data provided or index parameter")), 400
        
        question = data.get('question', '').strip()
        if not question:
            return jsonify(api_response(ErrorCode.BAD_REQUEST, "question is required")), 400
        
        # Load existing data
        if not os.path.exists(HR_QUICK_RESPONSES_PATH):
            return jsonify(api_response(ErrorCode.NOT_FOUND, "HR responses file not found")), 404
        
        with open(HR_QUICK_RESPONSES_PATH, 'r', encoding='utf-8') as f:
            existing_data = json.load(f)
        
        # Find and remove the item
        original_count = len(existing_data)
        deleted_item = None
        
        for i, item in enumerate(existing_data):
            if item.get('question', '').strip() == question:
                deleted_item = existing_data.pop(i)
                break
        
        if not deleted_item:
            return jsonify(api_response(ErrorCode.NOT_FOUND, f"Question not found: {question}")), 404
        
        # Create backup
        backup_path = create_backup(HR_QUICK_RESPONSES_PATH)
        
        # Write updated data
        with open(HR_QUICK_RESPONSES_PATH, 'w', encoding='utf-8') as f:
            json.dump(existing_data, f, ensure_ascii=False, indent=2)
        
        # Clear cache
        from utils.user.fast_response_utils import fast_response_handler
        fast_response_handler.data_loaded = False
        
        result = {
            "total_items": len(existing_data),
            "deleted_item": deleted_item,
            "backup_created": backup_path is not None,
            "items_removed": original_count - len(existing_data)
        }
        
        if backup_path:
            result["backup_path"] = os.path.basename(backup_path)
        
        return jsonify(api_response(ErrorCode.SUCCESS, "HR response deleted successfully", result)), 200
        
    except Exception as e:
        return jsonify(api_response(ErrorCode.INTERNAL_SERVER_ERROR, f"Failed to delete HR response: {str(e)}")), 500

@admin_hr_bp.route("/delete-chitchat-data", methods=["DELETE"])
@require_session
@require_admin
def delete_chitchat_data():
    """
    Xóa một chitchat data theo question hoặc index
    ---
    tags:
      - Admin HR
    parameters:
      - name: index
        in: query
        type: integer
        required: false
        description: Index của item cần xóa (0-based)
      - name: body
        in: body
        required: false
        schema:
          type: object
          properties:
            question:
              type: string
              description: Câu hỏi cần xóa (phải khớp chính xác)
          required: ["question"]
    responses:
      200:
        description: Xóa thành công
      400:
        description: Dữ liệu không hợp lệ
      404:
        description: Không tìm thấy câu hỏi hoặc index không hợp lệ
      500:
        description: Lỗi server
    """
    try:
        # Check for index parameter first (for Frontend compatibility)
        index_param = request.args.get('index')
        if index_param is not None:
            try:
                index = int(index_param)
                if index < 0:
                    return jsonify(api_response(ErrorCode.BAD_REQUEST, "Index must be non-negative")), 400
            except ValueError:
                return jsonify(api_response(ErrorCode.BAD_REQUEST, "Index must be a valid integer")), 400
            
            # Load existing data
            if not os.path.exists(CHITCHAT_DATA_PATH):
                return jsonify(api_response(ErrorCode.NOT_FOUND, "Chitchat data file not found")), 404
            
            with open(CHITCHAT_DATA_PATH, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
            
            # Check if index is valid
            if index >= len(existing_data):
                return jsonify(api_response(ErrorCode.NOT_FOUND, f"Index {index} is out of range. Total items: {len(existing_data)}")), 404
            
            # Remove item by index
            original_count = len(existing_data)
            deleted_item = existing_data.pop(index)
            
            # Create backup
            backup_path = create_backup(CHITCHAT_DATA_PATH)
            
            # Write updated data
            with open(CHITCHAT_DATA_PATH, 'w', encoding='utf-8') as f:
                json.dump(existing_data, f, ensure_ascii=False, indent=2)
            
            # Clear cache
            from utils.user.fast_response_utils import fast_response_handler
            fast_response_handler.data_loaded = False
            
            result = {
                "total_items": len(existing_data),
                "deleted_item": deleted_item,
                "backup_created": backup_path is not None,
                "items_removed": original_count - len(existing_data),
                "deleted_index": index
            }
            
            if backup_path:
                result["backup_path"] = os.path.basename(backup_path)
            
            return jsonify(api_response(ErrorCode.SUCCESS, "Chitchat data deleted successfully", result)), 200
        
        # Fallback to JSON body method
        data = request.get_json()
        if not data:
            return jsonify(api_response(ErrorCode.BAD_REQUEST, "No JSON data provided or index parameter")), 400
        
        question = data.get('question', '').strip()
        if not question:
            return jsonify(api_response(ErrorCode.BAD_REQUEST, "question is required")), 400
        
        # Load existing data
        if not os.path.exists(CHITCHAT_DATA_PATH):
            return jsonify(api_response(ErrorCode.NOT_FOUND, "Chitchat data file not found")), 404
        
        with open(CHITCHAT_DATA_PATH, 'r', encoding='utf-8') as f:
            existing_data = json.load(f)
        
        # Find and remove the item
        original_count = len(existing_data)
        deleted_item = None
        
        for i, item in enumerate(existing_data):
            if item.get('question', '').strip() == question:
                deleted_item = existing_data.pop(i)
                break
        
        if not deleted_item:
            return jsonify(api_response(ErrorCode.NOT_FOUND, f"Question not found: {question}")), 404
        
        # Create backup
        backup_path = create_backup(CHITCHAT_DATA_PATH)
        
        # Write updated data
        with open(CHITCHAT_DATA_PATH, 'w', encoding='utf-8') as f:
            json.dump(existing_data, f, ensure_ascii=False, indent=2)
        
        # Clear cache
        from utils.user.fast_response_utils import fast_response_handler
        fast_response_handler.data_loaded = False
        
        result = {
            "total_items": len(existing_data),
            "deleted_item": deleted_item,
            "backup_created": backup_path is not None,
            "items_removed": original_count - len(existing_data)
        }
        
        if backup_path:
            result["backup_path"] = os.path.basename(backup_path)
        
        return jsonify(api_response(ErrorCode.SUCCESS, "Chitchat data deleted successfully", result)), 200
        
    except Exception as e:
        return jsonify(api_response(ErrorCode.INTERNAL_SERVER_ERROR, f"Failed to delete chitchat data: {str(e)}")), 500

@admin_hr_bp.route("/delete-hr-responses-batch", methods=["DELETE"])
@require_session
@require_admin
def delete_hr_responses_batch():
    """
    Xóa nhiều HR responses theo danh sách questions
    ---
    tags:
      - Admin HR
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            questions:
              type: array
              items:
                type: string
              description: Danh sách câu hỏi cần xóa
          required: ["questions"]
    responses:
      200:
        description: Xóa thành công
      400:
        description: Dữ liệu không hợp lệ
      500:
        description: Lỗi server
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify(api_response(ErrorCode.BAD_REQUEST, "No JSON data provided")), 400
        
        questions = data.get('questions', [])
        if not isinstance(questions, list) or not questions:
            return jsonify(api_response(ErrorCode.BAD_REQUEST, "questions must be a non-empty array")), 400
        
        # Load existing data
        if not os.path.exists(HR_QUICK_RESPONSES_PATH):
            return jsonify(api_response(ErrorCode.NOT_FOUND, "HR responses file not found")), 404
        
        with open(HR_QUICK_RESPONSES_PATH, 'r', encoding='utf-8') as f:
            existing_data = json.load(f)
        
        # Find and remove items
        original_count = len(existing_data)
        deleted_items = []
        questions_set = {q.strip() for q in questions if q.strip()}
        
        # Remove items in reverse order to avoid index issues
        for i in range(len(existing_data) - 1, -1, -1):
            item_question = existing_data[i].get('question', '').strip()
            if item_question in questions_set:
                deleted_items.append(existing_data.pop(i))
        
        if not deleted_items:
            return jsonify(api_response(ErrorCode.BAD_REQUEST, "No matching questions found")), 400
        
        # Create backup
        backup_path = create_backup(HR_QUICK_RESPONSES_PATH)
        
        # Write updated data
        with open(HR_QUICK_RESPONSES_PATH, 'w', encoding='utf-8') as f:
            json.dump(existing_data, f, ensure_ascii=False, indent=2)
        
        # Clear cache
        from utils.user.fast_response_utils import fast_response_handler
        fast_response_handler.data_loaded = False
        
        result = {
            "total_items": len(existing_data),
            "deleted_items": deleted_items,
            "backup_created": backup_path is not None,
            "items_removed": len(deleted_items),
            "requested_count": len(questions_set),
            "successful_deletions": len(deleted_items)
        }
        
        if backup_path:
            result["backup_path"] = os.path.basename(backup_path)
        
        return jsonify(api_response(ErrorCode.SUCCESS, "HR responses deleted successfully", result)), 200
        
    except Exception as e:
        return jsonify(api_response(ErrorCode.INTERNAL_SERVER_ERROR, f"Failed to delete HR responses: {str(e)}")), 500

@admin_hr_bp.route("/delete-chitchat-data-batch", methods=["DELETE"])
@require_session
@require_admin
def delete_chitchat_data_batch():
    """
    Xóa nhiều chitchat data theo danh sách questions
    ---
    tags:
      - Admin HR
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            questions:
              type: array
              items:
                type: string
              description: Danh sách câu hỏi cần xóa
          required: ["questions"]
    responses:
      200:
        description: Xóa thành công
      400:
        description: Dữ liệu không hợp lệ
      500:
        description: Lỗi server
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify(api_response(ErrorCode.BAD_REQUEST, "No JSON data provided")), 400
        
        questions = data.get('questions', [])
        if not isinstance(questions, list) or not questions:
            return jsonify(api_response(ErrorCode.BAD_REQUEST, "questions must be a non-empty array")), 400
        
        # Load existing data
        if not os.path.exists(CHITCHAT_DATA_PATH):
            return jsonify(api_response(ErrorCode.NOT_FOUND, "Chitchat data file not found")), 404
        
        with open(CHITCHAT_DATA_PATH, 'r', encoding='utf-8') as f:
            existing_data = json.load(f)
        
        # Find and remove items
        original_count = len(existing_data)
        deleted_items = []
        questions_set = {q.strip() for q in questions if q.strip()}
        
        # Remove items in reverse order to avoid index issues
        for i in range(len(existing_data) - 1, -1, -1):
            item_question = existing_data[i].get('question', '').strip()
            if item_question in questions_set:
                deleted_items.append(existing_data.pop(i))
        
        if not deleted_items:
            return jsonify(api_response(ErrorCode.BAD_REQUEST, "No matching questions found")), 400
        
        # Create backup
        backup_path = create_backup(CHITCHAT_DATA_PATH)
        
        # Write updated data
        with open(CHITCHAT_DATA_PATH, 'w', encoding='utf-8') as f:
            json.dump(existing_data, f, ensure_ascii=False, indent=2)
        
        # Clear cache
        from utils.user.fast_response_utils import fast_response_handler
        fast_response_handler.data_loaded = False
        
        result = {
            "total_items": len(existing_data),
            "deleted_items": deleted_items,
            "backup_created": backup_path is not None,
            "items_removed": len(deleted_items),
            "requested_count": len(questions_set),
            "successful_deletions": len(deleted_items)
        }
        
        if backup_path:
            result["backup_path"] = os.path.basename(backup_path)
        
        return jsonify(api_response(ErrorCode.SUCCESS, "Chitchat data deleted successfully", result)), 200
        
    except Exception as e:
        return jsonify(api_response(ErrorCode.INTERNAL_SERVER_ERROR, f"Failed to delete chitchat data: {str(e)}")), 500
