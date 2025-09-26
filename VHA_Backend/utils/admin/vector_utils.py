import os
import time
import json
import hashlib
import uuid
import boto3
import re

from datetime import datetime
from langchain_community.embeddings import BedrockEmbeddings
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.vectorstores import FAISS
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema import Document
from langchain.text_splitter import CharacterTextSplitter
from .upload_s3_utils import DATA_DIR, s3_lock, list_registry
from utils.aws_client import s3_client, bedrock_embeddings
from typing import List
from langchain.schema import Document

    



    
import re
from langchain_core.documents import Document

def advanced_semantic_split(pages, chunk_size=300, overlap=50, source_filename=None):
    """
    Cắt tài liệu dạng handbook thành các đoạn nhỏ dựa trên heading (1.1, 1.2.3, v.v).
    Gán section là heading gần nhất, thêm metadata về source_file, page_number, và heading_level.
    Sửa lỗi OCR cơ bản để tăng độ chính xác.
    Tối ưu hóa cho việc xử lý nhiều file handbook riêng biệt.
    """
    """
    Cắt tài liệu dạng handbook thành các đoạn nhỏ dựa trên heading (1.1, 1.2.3, v.v).
    Gán section là heading gần nhất, thêm metadata về source_file, page_number, và heading_level.
    Sửa lỗi OCR cơ bản để tăng độ chính xác.
    """
    def clean_ocr_text(text):
        """Sửa lỗi OCR cơ bản."""
        corrections = {
            "Sô tay": "Sổ tay",
            "thutơng": "thương",
            "chám dút": "chấm dứt",
            "thù việc": "thử việc",
            "đi làm": "đi làm",
            "tháng chức": "thăng chức",
            "Sư": "Sứ",
            "dào tạo": "đào tạo",
            "phật triển": "phát triển",
            "thành toán": "thanh toán",
            "phuc vụu": "phục vụ",
            "bbi thường": "bồi thường",
            "hu hơng": "hư hỏng",
            "luơng": "lương",
            "tô đã": "tối đa"
        }
        for wrong, correct in corrections.items():
            text = text.replace(wrong, correct)
        return text

    raw_text = ""
    page_numbers = {}
    for page in pages:
        if page and page.page_content:
            start_idx = len(raw_text)
            raw_text += page.page_content + "\n"
            page_numbers[start_idx] = page.metadata.get("page_number", "unknown")

    raw_text = clean_ocr_text(raw_text)
    lines = raw_text.split('\n')

    heading_pattern = re.compile(r"^\s*(\d+(\.\d+)*)(\.|\s)\s+(.+)")
    
    handbook_type = "Sổ tay nhân viên Vinova"
    if source_filename:
        filename_lower = source_filename.lower()
        if "luong" in filename_lower or "thuong" in filename_lower:
            handbook_type = "CHÍNH SÁCH VỀ LƯƠNG, PHÚC LỢI VÀ THƯỞNG"
        elif "nghi" in filename_lower or "thoi gian" in filename_lower:
            handbook_type = "CHÍNH SÁCH NGHỈ VÀ THỜI GIAN LÀM VIỆC"
        elif "bao hiem" in filename_lower or "phuc loi" in filename_lower:
            handbook_type = "CHÍNH SÁCH BẢO HIỂM & PHÚC LỢI XÃ HỘI"
        elif "tuyen dung" in filename_lower or "dao tao" in filename_lower:
            handbook_type = "TUYỂN DỤNG, THỬ VIỆC VÀ ĐÀO TẠO"
        elif "danh gia" in filename_lower or "ky luat" in filename_lower:
            handbook_type = "ĐÁNH GIÁ, KỶ LUẬT VÀ NGHỈ VIỆC"
    heading_indices = []
    current_heading = "Sổ tay nhân viên Vinova"
    heading_level = 0

    for idx, line in enumerate(lines):
        line = line.strip()
        if heading_pattern.match(line):
            heading_indices.append((idx, line, len(re.match(r"^\s*\d+(\.\d+)*", line).group(0).split('.'))))
            current_heading = line
            heading_level = len(re.match(r"^\s*\d+(\.\d+)*", line).group(0).split('.'))

    if not heading_indices:
        heading_indices.append((0, handbook_type, 0))
    heading_indices.append((len(lines), "", 0))

    chunks = []
    for i in range(len(heading_indices) - 1):
        start_idx, heading, level = heading_indices[i]
        end_idx = heading_indices[i + 1][0]
        section_lines = lines[start_idx:end_idx]
        section_text = "\n".join(line.strip() for line in section_lines if line.strip())

        if len(section_text) < 30:
            continue

        page_number = next((pn for start, pn in page_numbers.items() if start <= start_idx), "unknown")

        words = section_text.split()
        for j in range(0, len(words), chunk_size):
            chunk_words = words[j:j + chunk_size + overlap]
            chunk_text = " ".join(chunk_words)
            if len(chunk_text.strip()) < 50:
                continue

            doc = Document(page_content=chunk_text)
            doc.metadata["section"] = re.sub(r'\s+', ' ', heading)[:150]
            doc.metadata["heading_level"] = level
            doc.metadata["page_number"] = page_number
            doc.metadata["handbook_type"] = handbook_type
            if source_filename:
                doc.metadata["source_file"] = source_filename
            chunks.append(doc)

    for i, chunk in enumerate(chunks):
        print(f"Chunk {i+1}: {chunk.metadata.get('section', '')} | Level: {chunk.metadata.get('heading_level', 0)} | Page: {chunk.metadata.get('page_number', 'unknown')} | {chunk.page_content[:80]}...")

    return chunks



def generate_unique_filename(base_name, timestamp=None):
    """Tạo unique filename ngắn hơn để đảm bảo không vượt quá 36 ký tự"""
    if timestamp is None:
        timestamp = int(time.time())
    unique_id = str(uuid.uuid4())
    return unique_id

def create_vector_store(request_id, documents, original_filename, bedrock_embeddings):
    try:
        existing_vector_store = load_vector_store_if_exists(request_id, bedrock_embeddings)
        if existing_vector_store:
            print(f"Vector store for request_id {request_id} already exists, skipping creation.")
            return request_id 

        timestamp = int(time.time())
        unique_filename = request_id

        folder_path = DATA_DIR
        faiss_path = os.path.join(folder_path, f"{unique_filename}.faiss")
        pkl_path = os.path.join(folder_path, f"{unique_filename}.pkl")

        vectorstore_faiss = FAISS.from_documents(documents, bedrock_embeddings)
        vectorstore_faiss.save_local(index_name=unique_filename, folder_path=folder_path)
        print(f"FAISS saved locally to {faiss_path} & {pkl_path}")

        s3_faiss_key = f"faiss_indexes/{unique_filename}.faiss"
        s3_pkl_key = f"faiss_indexes/{unique_filename}.pkl"

        with s3_lock:
            s3_client.upload_file(Filename=faiss_path, Bucket=os.getenv("BUCKET_NAME"), Key=s3_faiss_key)
            s3_client.upload_file(Filename=pkl_path, Bucket=os.getenv("BUCKET_NAME"), Key=s3_pkl_key)
            print(f"Uploaded to S3: {s3_faiss_key}, {s3_pkl_key}")

        try:
            os.remove(faiss_path)
            os.remove(pkl_path)
            print(f"Deleted local files: {faiss_path}, {pkl_path}")
        except Exception as e:
            print(f"Failed to delete local files: {e}")

        update_file_registry(unique_filename, original_filename, timestamp, request_id)
        print(f"Registry updated with file: {original_filename}")

        return unique_filename

    except Exception as e:
        print(f"Error in create_vector_store: {e}")
        return None

def update_file_registry(unique_filename, original_filename, timestamp, request_id):
    registry_key = "faiss_indexes/file_registry.json"

    try:
        try:
            response = s3_client.get_object(Bucket=os.getenv("BUCKET_NAME"), Key=registry_key)
            registry = json.loads(response['Body'].read().decode('utf-8'))
        except s3_client.exceptions.NoSuchKey:
            registry = {"files": []}

        if isinstance(timestamp, str):
            timestamp = int(float(timestamp))

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

        registry_body = json.dumps(registry, indent=2)
        s3_client.put_object(Bucket=os.getenv("BUCKET_NAME"), Key=registry_key, Body=registry_body)

    except Exception as e:
        print(f"Failed to update file registry: {e}")

def load_vector_store_if_exists(request_id, bedrock_embeddings):
    for filename in os.listdir(DATA_DIR):
        if filename.startswith(request_id) and filename.endswith(".faiss"):
            base_name = filename[:-6] 
            pkl_path = os.path.join(DATA_DIR, base_name + ".pkl")
            if os.path.exists(pkl_path):
                try:
                    vector_store = FAISS.load_local(
                        index_name=base_name,
                        folder_path=DATA_DIR,
                        embeddings=bedrock_embeddings,
                        allow_dangerous_deserialization=True
                    )
                    print(f"Loaded existing vector store for request_id: {request_id}")
                    return vector_store
                except Exception as e:
                    print(f"Failed to load vector store {base_name}: {e}")
                    continue
    return None

def initialize_model():
    llm_id = os.getenv("LLM_ID")
    if not llm_id:
        raise ValueError("Chưa cấu hình LLM_ID trong file .env")


    vector_stores = {}
    s3_files = list_registry()
    for file in s3_files:
        unique_filename = file.get("unique_filename")
        vectorstore = load_vector_store_from_s3(unique_filename, bedrock_embeddings=bedrock_embeddings)
        if vectorstore:
            vector_stores[unique_filename] = vectorstore

    return None, vector_stores

def download_from_s3(unique_filename):
    faiss_key = f"faiss_indexes/{unique_filename}.faiss"
    pkl_key = f"faiss_indexes/{unique_filename}.pkl"

    local_faiss_path = os.path.join(DATA_DIR, f"{unique_filename}.faiss")
    local_pkl_path = os.path.join(DATA_DIR, f"{unique_filename}.pkl")

    try:
        s3_client.download_file(os.getenv("BUCKET_NAME"), faiss_key, local_faiss_path)
        s3_client.download_file(os.getenv("BUCKET_NAME"), pkl_key, local_pkl_path)
        return True
    except Exception as e:
        print(f"Download error: {e}")
        return False

def load_vector_store_from_s3(unique_filename, bedrock_embeddings):
    if download_from_s3(unique_filename):
        try:
            return FAISS.load_local(
                index_name=unique_filename,
                folder_path=DATA_DIR,
                embeddings=bedrock_embeddings,
                allow_dangerous_deserialization=True
            )
        except Exception as e:
            print(f"Load vector store failed: {e}")
            return None
    return None