import os
import time
import json
import uuid
import threading
import boto3
import pdfplumber
import requests
import io
from datetime import datetime
from utils.aws_client import session, s3_client
from botocore.exceptions import ClientError
from urllib.parse import urlparse
from models.models_db import FileDocument
from config.database import db
s3_lock = threading.Lock()

BUCKET_NAME = os.getenv("BUCKET_NAME")
BUCKET_NAME_2 = os.getenv("BUCKET_NAME_2")

DATA_DIR = os.path.join(os.getcwd(), "data")
os.makedirs(DATA_DIR, exist_ok=True)

def generate_unique_filename(base_name, timestamp=None):
    """Tạo unique filename ngắn hơn để đảm bảo không vượt quá 36 ký tự"""
    if timestamp is None:
        timestamp = int(time.time())
    unique_id = str(uuid.uuid4())
    return unique_id

def update_file_registry(unique_filename, original_filename, timestamp, request_id):
    registry_key = "faiss_indexes/file_registry.json"
    try:
        if not all([unique_filename, original_filename, request_id]) or not isinstance(timestamp, (int, float)):
            return None, "Invalid input parameters"

        try:
            response = s3_client.get_object(Bucket=BUCKET_NAME, Key=registry_key)
            registry = json.loads(response['Body'].read().decode('utf-8'))
        except s3_client.exceptions.NoSuchKey:
            registry = {"files": []}
        except ClientError as e:
            return None, f"Error accessing registry: {str(e)}"

        if isinstance(timestamp, str) and timestamp.isdigit():
            timestamp = int(timestamp)
        elif not isinstance(timestamp, int):
            try:
                timestamp = int(float(timestamp))
            except (ValueError, TypeError):
                timestamp = int(time.time())

        file_entry = {
            "unique_filename": unique_filename,
            "original_filename": original_filename,
            "request_id": request_id,
            "timestamp": timestamp,
            "upload_date": datetime.fromtimestamp(timestamp).isoformat(),
            "faiss_key": f"faiss_indexes/{unique_filename}.faiss",
            "pkl_key": f"faiss_indexes/{unique_filename}.pkl"
        }

        registry["files"].append(file_entry)
        registry["last_updated"] = timestamp

        try:
            registry_body = json.dumps(registry, indent=2)
            s3_client.put_object(Bucket=BUCKET_NAME, Key=registry_key, Body=registry_body)
            return file_entry, None
        except ClientError as e:
            return None, f"Error writing registry to S3: {str(e)}"

    except Exception as e:
        return None, f"Unexpected error: {str(e)}"

def delete_file_from_registry(filename):
    registry_key = "faiss_indexes/file_registry.json"
    try:
        try:
            response = s3_client.get_object(Bucket=BUCKET_NAME, Key=registry_key)
            registry = json.loads(response['Body'].read().decode('utf-8'))
        except s3_client.exceptions.NoSuchKey:
            print(f"Registry file {registry_key} not found in S3")
            return False, "Registry file not found in S3"
        except ClientError as e:
            print(f"Error accessing registry file: {e}")
            return False, f"Error accessing registry: {str(e)}"

        if not any(f["unique_filename"] == filename for f in registry.get("files", [])):
            print(f"Filename {filename} not found in registry")
            return False, f"File {filename} not found in registry"

        s3_deletion_errors = []
        for key in [f"faiss_indexes/{filename}.faiss", f"faiss_indexes/{filename}.pkl"]:
            try:
                s3_client.delete_object(Bucket=BUCKET_NAME, Key=key)
                print(f"Deleted S3 object: {key}")
            except ClientError as e:
                s3_deletion_errors.append(f"Failed to delete S3 object {key}: {str(e)}")

        local_deletion_errors = []
        for ext in [".faiss", ".pkl"]:
            local_path = os.path.join(DATA_DIR, f"{filename}{ext}")
            if os.path.exists(local_path):
                try:
                    os.remove(local_path)
                    print(f"Deleted local file: {local_path}")
                except OSError as e:
                    local_deletion_errors.append(f"Failed to delete local file {local_path}: {str(e)}")
            else:
                print(f"Local file not found: {local_path}")

        registry["files"] = [f for f in registry.get("files", []) if f["unique_filename"] != filename]
        registry["last_updated"] = int(time.time())

        try:
            updated_body = json.dumps(registry, indent=2)
            s3_client.put_object(Bucket=BUCKET_NAME, Key=registry_key, Body=updated_body)
            print(f"Updated registry: {registry_key}")
        except ClientError as e:
            print(f"Error updating registry: {e}")
            return False, f"Error updating registry: {str(e)}"
        if s3_deletion_errors or local_deletion_errors:
            error_message = "Deletion completed with issues: " + "; ".join(s3_deletion_errors + local_deletion_errors)
            return True, error_message
        return True, "File deleted successfully from S3, local storage, and registry"

    except Exception as e:
        print(f"Unexpected error in delete_file_from_registry: {e}")
        return False, f"Unexpected error: {str(e)}"

def list_registry():
    registry_key = "faiss_indexes/file_registry.json"
    try:
        response = s3_client.get_object(Bucket=BUCKET_NAME, Key=registry_key)
        registry = json.loads(response['Body'].read().decode('utf-8'))
        return registry.get("files", [])
    except s3_client.exceptions.NoSuchKey:
        return []
    except Exception:
        return []

def download_from_s3(unique_filename):
    faiss_key = f"faiss_indexes/{unique_filename}.faiss"
    pkl_key = f"faiss_indexes/{unique_filename}.pkl"
    local_faiss_path = os.path.join(DATA_DIR, f"{unique_filename}.faiss")
    local_pkl_path = os.path.join(DATA_DIR, f"{unique_filename}.pkl")

    try:
        s3_client.download_file(BUCKET_NAME, faiss_key, local_faiss_path)
        s3_client.download_file(BUCKET_NAME, pkl_key, local_pkl_path)
        return True
    except Exception:
        return False

def get_file_name_from_url(url):
    return url.split('/')[-1]
def save_file_metadata_if_not_exists(file_name, file_url, content_type):
    existing = FileDocument.query.filter_by(file_name=file_name).first()
    if existing:
        return existing, False

    file_doc = FileDocument(
        id=str(uuid.uuid4()),
        file_name=file_name,
        file_url=file_url,
        content_type=content_type
    )
    db.session.add(file_doc)
    db.session.commit()
    return file_doc, True

def read_text_from_url(file_url: str, content_type: str) -> str:
    response = requests.get(file_url)
    if not response.ok:
        raise Exception(f"Không thể tải file từ URL: {file_url}")

    if content_type == "text/plain":
        return response.text

    elif content_type == "application/pdf":
        with pdfplumber.open(io.BytesIO(response.content)) as pdf:
            all_text = "\n".join(page.extract_text() or "" for page in pdf.pages)
            return all_text.strip()

    else:
        raise Exception(f"Chưa hỗ trợ loại file: {content_type}")

def download_pdf_from_s3(file_url: str) -> bytes:
    """
    Download PDF file từ S3 URL
    """
    try:
        response = requests.get(file_url)
        if not response.ok:
            raise Exception(f"Không thể tải file từ URL: {file_url}")
        return response.content
    except Exception as e:
        raise Exception(f"Download failed: {str(e)}")

def download_pdf_from_s3_by_key(s3_key: str) -> bytes:
    """
    Download PDF file từ S3 bằng key
    """
    try:
        bucket_name_2 = os.getenv("BUCKET_NAME_2")
        if not bucket_name_2:
            raise Exception("BUCKET_NAME_2 not configured")
        
        response = s3_client.get_object(Bucket=bucket_name_2, Key=s3_key)
        return response['Body'].read()
    except Exception as e:
        raise Exception(f"Download failed: {str(e)}")

def delete_file_complete(filename):
    """
    Xóa file hoàn toàn từ database, S3 BUCKET_NAME_2 và S3 BUCKET_NAME
    """
    try:
        db_deletion_success = False
        db_error = None
        unique_filename = None
        
        try:
            file_doc = FileDocument.query.filter_by(file_name=filename).first()
            
            if not file_doc:
                file_doc = FileDocument.query.filter_by(id=filename).first()
                if file_doc:
                    unique_filename = filename
                else:
                    print(f"File {filename} not found in database")
                    return False, f"File {filename} not found in database"
            else:
                unique_filename = file_doc.id
            
            db.session.delete(file_doc)
            db.session.commit()
            db_deletion_success = True
            print(f"Deleted from database: {filename}")
            
        except Exception as e:
            db_error = str(e)
            print(f"Error deleting from database: {e}")
            db.session.rollback()

        s3_bucket2_deletion_errors = []
        try:
            bucket_name_2 = os.getenv("BUCKET_NAME_2")
            if bucket_name_2:
                s3_keys_to_try = [
                    f"{unique_filename}.pdf",
                    f"{filename}"
                ]
                
                for s3_key in s3_keys_to_try:
                    try:
                        s3_client.delete_object(Bucket=bucket_name_2, Key=s3_key)
                        print(f"Deleted from S3 BUCKET_NAME_2: {s3_key}")
                        break
                    except ClientError as e:
                        if e.response['Error']['Code'] != 'NoSuchKey':
                            s3_bucket2_deletion_errors.append(f"Failed to delete from BUCKET_NAME_2 {s3_key}: {str(e)}")
                        else:
                            print(f"File not found in BUCKET_NAME_2: {s3_key}")
            else:
                print("BUCKET_NAME_2 not configured")
        except Exception as e:
            s3_bucket2_deletion_errors.append(f"Error accessing BUCKET_NAME_2: {str(e)}")

        s3_bucket1_deletion_errors = []
        try:
            actual_unique_filename = None
            try:
                registry_key = "faiss_indexes/file_registry.json"
                response = s3_client.get_object(Bucket=BUCKET_NAME, Key=registry_key)
                registry = json.loads(response['Body'].read().decode('utf-8'))
                
                for file_entry in registry.get("files", []):
                    if (file_entry.get("unique_filename") == unique_filename or 
                        file_entry.get("unique_filename") == filename or
                        file_entry.get("original_filename") == filename):
                        actual_unique_filename = file_entry.get("unique_filename")
                        print(f"Found actual unique_filename in registry: {actual_unique_filename}")
                        break
            except Exception as e:
                print(f"Error reading registry: {e}")
            
            faiss_keys_to_try = []
            if actual_unique_filename:
                faiss_keys_to_try.extend([
                    f"faiss_indexes/{actual_unique_filename}.faiss",
                    f"faiss_indexes/{actual_unique_filename}.pkl"
                ])
            
            faiss_keys_to_try.extend([
                f"faiss_indexes/{unique_filename}.faiss",
                f"faiss_indexes/{unique_filename}.pkl",
                f"faiss_indexes/{filename}.faiss",
                f"faiss_indexes/{filename}.pkl"
            ])
            
            faiss_keys_to_try = list(set(faiss_keys_to_try))
            
            for key in faiss_keys_to_try:
                try:
                    s3_client.delete_object(Bucket=BUCKET_NAME, Key=key)
                    print(f"Deleted from S3 BUCKET_NAME: {key}")
                except ClientError as e:
                    if e.response['Error']['Code'] != 'NoSuchKey':
                        s3_bucket1_deletion_errors.append(f"Failed to delete from BUCKET_NAME {key}: {str(e)}")
                    else:
                        print(f"File not found in BUCKET_NAME: {key}")
        except Exception as e:
            s3_bucket1_deletion_errors.append(f"Error accessing BUCKET_NAME: {str(e)}")

        registry_deletion_success = False
        registry_error = None
        try:
            registry_key = "faiss_indexes/file_registry.json"
            try:
                response = s3_client.get_object(Bucket=BUCKET_NAME, Key=registry_key)
                registry = json.loads(response['Body'].read().decode('utf-8'))
                
                original_count = len(registry.get("files", []))
                
                entries_to_remove = []
                for f in registry.get("files", []):
                    if (f["unique_filename"] == unique_filename or 
                        f["unique_filename"] == filename or
                        f["original_filename"] == filename or
                        f["request_id"] == unique_filename or
                        f["request_id"] == filename):
                        entries_to_remove.append(f["unique_filename"])
                
                registry["files"] = [f for f in registry.get("files", []) 
                                   if f["unique_filename"] not in entries_to_remove]
                registry["last_updated"] = int(time.time())
                
                updated_body = json.dumps(registry, indent=2)
                s3_client.put_object(Bucket=BUCKET_NAME, Key=registry_key, Body=updated_body)
                registry_deletion_success = True
                removed_count = original_count - len(registry["files"])
                print(f"Updated registry: removed {removed_count} entries")
            except s3_client.exceptions.NoSuchKey:
                print(f"Registry file {registry_key} not found in S3")
            except ClientError as e:
                registry_error = str(e)
                print(f"Error updating registry: {e}")
        except Exception as e:
            registry_error = str(e)
            print(f"Unexpected error updating registry: {e}")

        local_deletion_errors = []
        for ext in [".faiss", ".pkl", ".pdf"]:
            for name in [unique_filename, filename]:
                local_path = os.path.join(DATA_DIR, f"{name}{ext}")
                if os.path.exists(local_path):
                    try:
                        os.remove(local_path)
                        print(f"Deleted local file: {local_path}")
                    except OSError as e:
                        local_deletion_errors.append(f"Failed to delete local file {local_path}: {str(e)}")

        all_errors = []
        if db_error:
            all_errors.append(f"Database: {db_error}")
        if s3_bucket2_deletion_errors:
            all_errors.extend(s3_bucket2_deletion_errors)
        if s3_bucket1_deletion_errors:
            all_errors.extend(s3_bucket1_deletion_errors)
        if registry_error:
            all_errors.append(f"Registry: {registry_error}")
        if local_deletion_errors:
            all_errors.extend(local_deletion_errors)

        if all_errors:
            error_message = "Deletion completed with issues: " + "; ".join(all_errors)
            return True, error_message
        else:
            return True, "File deleted successfully from all locations"

    except Exception as e:
        print(f"Unexpected error in delete_file_complete: {e}")
        return False, f"Unexpected error: {str(e)}"