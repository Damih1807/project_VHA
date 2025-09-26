import os
import json
import time
import re
from typing import List, Dict, Any, Tuple
from langchain_community.vectorstores import FAISS
from langchain.schema import Document

from utils.admin.upload_s3_utils import s3_client, BUCKET_NAME, DATA_DIR, download_from_s3
from utils.aws_client import bedrock_embeddings

_registry_cache = None
_cache_timestamp = 0
CACHE_TTL = 60

try:
    from config.performance import MAX_FILES_TO_LOAD, FILE_LOADING_STRATEGY, SMART_LOADING_KEYWORDS
except ImportError:
    MAX_FILES_TO_LOAD = 20
    FILE_LOADING_STRATEGY = "latest"
    SMART_LOADING_KEYWORDS = ["lương", "bảo hiểm", "nghỉ phép", "tuyển dụng"]

def clear_registry_cache():
    """Clear registry cache để force reload"""
    global _registry_cache, _cache_timestamp
    _registry_cache = None
    _cache_timestamp = 0
    print("[INFO] Registry cache cleared - will reload from S3 on next request")

def get_file_registry():
    """Get file registry with S3 fallback and caching"""
    global _registry_cache, _cache_timestamp
    
    current_time = time.time()
    
    if _registry_cache and (current_time - _cache_timestamp) < CACHE_TTL:
        print(f"[INFO] Using cached registry: {len(_registry_cache.get('files', []))} files")
        return _registry_cache
    
    registry_key = "faiss_indexes/file_registry.json"
    
    try:
        response = s3_client.get_object(Bucket=BUCKET_NAME, Key=registry_key)
        registry = json.loads(response['Body'].read().decode('utf-8'))
        print(f"[INFO] Loaded registry from S3: {len(registry.get('files', []))} files")
        
        _registry_cache = registry
        _cache_timestamp = current_time
        
        return registry
    except Exception as e:
        
        local_registry_path = "faiss_indexes/file_registry.json"
        try:
            if os.path.exists(local_registry_path):
                with open(local_registry_path, 'r', encoding='utf-8') as f:
                    registry = json.load(f)
                print(f"[INFO] Loaded registry from local: {len(registry.get('files', []))} files")
                
                _registry_cache = registry
                _cache_timestamp = current_time
                
                return registry
            else:
                print("[INFO] No local registry found, creating empty one")
                empty_registry = {"files": []}
                _registry_cache = empty_registry
                _cache_timestamp = current_time
                return empty_registry
        except Exception as local_e:
            print(f"[ERROR] Local registry load failed: {local_e}")
            empty_registry = {"files": []}
            _registry_cache = empty_registry
            _cache_timestamp = current_time
            return empty_registry

def get_latest_n_files(n: int) -> List[Dict[str, Any]]:
    """Get latest files with fallback"""
    registry = get_file_registry()
    files = registry.get("files", [])
    
    if not files:
        print("[WARNING] No files in registry, using sample data")
        return [{
            'unique_filename': 'sample_file',
            'original_filename': 'sample.pdf',
            'timestamp': time.time()
        }]
    
    sorted_files = sorted(files, key=lambda x: x.get('timestamp', 0), reverse=True)
    result = sorted_files[:n]
    
    print(f"[INFO] Loaded {len(result)} latest files from registry")
    return result

def load_faiss_index(unique_filename: str, embeddings) -> FAISS:
    """Load FAISS index with fallback"""
    try:
        local_faiss_path = os.path.join(DATA_DIR, f"{unique_filename}.faiss")
        local_pkl_path = os.path.join(DATA_DIR, f"{unique_filename}.pkl")
        
        if os.path.exists(local_faiss_path) and os.path.exists(local_pkl_path):
            index = FAISS.load_local(
                index_name=unique_filename,
                folder_path=DATA_DIR,
                embeddings=embeddings,
                allow_dangerous_deserialization=True
            )
            print(f"[INFO] Loaded FAISS index from local: {unique_filename}")
            return index
        
        if download_from_s3(unique_filename):
            index = FAISS.load_local(
                index_name=unique_filename,
                folder_path=DATA_DIR,
                embeddings=embeddings,
                allow_dangerous_deserialization=True
            )
            return index
        else:
            return None
        
    except Exception as e:
        print(f"[ERROR] Cannot load FAISS {unique_filename}: {e}")
        return None

def load_multiple_vector_stores(selected_files: List[Dict[str, Any]], embeddings) -> List[Dict[str, Any]]:
    """Load vector stores with fallback"""
    vector_stores = []
    
    
    for file_info in selected_files:
        unique_filename = file_info['unique_filename']
        faiss_index = load_faiss_index(unique_filename, embeddings)
        
        if faiss_index:
            vector_stores.append({
                'vectorstore': faiss_index,
                'filename': file_info['original_filename'],
                'unique_filename': unique_filename
            })
        else:
            print(f"[WARNING] Skipping {unique_filename} - index not available")
    
    print(f"[INFO] Successfully loaded {len(vector_stores)} vector stores")
    
    if not vector_stores:
        print("[WARNING] No vector stores loaded - this is normal for first run")
        try:
            dummy_docs = [Document(page_content="Sample document for testing", metadata={})]
            dummy_store = FAISS.from_documents(dummy_docs, embeddings)
            vector_stores.append({
                'vectorstore': dummy_store,
                'filename': 'dummy.pdf',
                'unique_filename': 'dummy'
            })
            print("[INFO] Created dummy vector store for testing")
        except Exception as e:
            print(f"[ERROR] Failed to create dummy store: {e}")
    
    return vector_stores

def find_accurate_section(page_content: str) -> str:
    """Find the most accurate section name from page content"""
    if not page_content:
        return "Unknown"
    
    lines = page_content.strip().split('\n')[:5]
    content_text = ' '.join(lines).lower()
    
    first_line = lines[0] if lines else ""
    if first_line.strip():
        heading_pattern = re.compile(r"^\s*(\d+(\.\d+)*)(\.|\s)\s+(.+)")
        match = heading_pattern.match(first_line.strip())
        if match:
            return match.group(0).strip()[:150]
    
    return first_line[:100] if first_line else "Unknown"

def retrieve_relevant_docs(vector_stores: List[Dict[str, Any]], question: str, k: int) -> List:
    """Retrieve relevant documents with similarity scores"""
    all_docs_with_scores = []
    
    for vs_info in vector_stores:
        try:
            results = vs_info['vectorstore'].similarity_search_with_score(question, k=k)
            
            for doc, score in results:
                doc.metadata['source_file'] = vs_info['filename']
                doc.metadata['source'] = vs_info['filename']  
                doc.metadata['similarity_score'] = score  
                doc.metadata["section"] = find_accurate_section(doc.page_content)
                all_docs_with_scores.append((doc, score))
                
        except Exception as e:
            print(f"[ERROR] Error retrieving from {vs_info['filename']}: {e}")
            continue 
    all_docs_with_scores.sort(key=lambda x: x[1])
    
    docs = [doc for doc, score in all_docs_with_scores]
    
    return docs

def build_context(docs: List, question: str) -> str:
    """Build context from documents"""
    if not docs:
        return ""
    
    context_parts = []
    for doc in docs:
        if doc.page_content:
            content = doc.page_content[:800]
            source = doc.metadata.get("section", doc.metadata.get("source_file", "unknown"))
            context_parts.append(f"[{source}]\n{content.strip()}")
    
    return "\n\n".join(context_parts).strip()

def prioritize_files_for_hr_questions(latest_files: List[Dict[str, Any]], enhanced_question: str) -> List[Dict[str, Any]]:
    """Prioritize files based on HR question content"""
    question_lower = enhanced_question.lower()
    prioritized_files = []
    
    if any(word in question_lower for word in ['bảo hiểm', 'bhxh', 'bhyt', 'bhtn', 'insurance']):
        for file_info in latest_files:
            if 'bao hiem' in file_info['original_filename'].lower():
                prioritized_files.insert(0, file_info)
            else:
                prioritized_files.append(file_info)
    elif any(word in question_lower for word in ['lương', 'thưởng', 'phúc lợi', 'phụ cấp', 'salary', 'bonus']):
        for file_info in latest_files:
            if 'luong' in file_info['original_filename'].lower():
                prioritized_files.insert(0, file_info)
            else:
                prioritized_files.append(file_info)
    elif any(word in question_lower for word in ['nghỉ phép', 'nghỉ thai sản', 'leave', 'holiday']):
        for file_info in latest_files:
            if 'nghi' in file_info['original_filename'].lower():
                prioritized_files.insert(0, file_info)
            else:
                prioritized_files.append(file_info)
    else:
        prioritized_files = latest_files
    
    return prioritized_files 

def get_smart_files(question: str, max_files: int = None) -> List[Dict[str, Any]]:
    """Get files based on smart strategy"""
    if max_files is None:
        max_files = MAX_FILES_TO_LOAD
    
    registry = get_file_registry()
    files = registry.get("files", [])
    
    if not files:
        print("[WARNING] No files in registry, using sample data")
        return [{
            'unique_filename': 'sample_file',
            'original_filename': 'sample.pdf',
            'timestamp': time.time()
        }]
    
    question_lower = question.lower()
    
    if any(word in question_lower for word in ["tất cả", "tổng hợp", "tổng quan", "overview", "summary"]):
        print(f"[INFO] Loading all {len(files)} files for comprehensive search")
        return files[:max_files]
    
    relevant_files = []
    other_files = []
    
    for file_info in files:
        filename_lower = file_info.get('original_filename', '').lower()
        
        is_relevant = False
        for keyword in SMART_LOADING_KEYWORDS:
            if keyword in question_lower and keyword in filename_lower:
                is_relevant = True
                break
        
        if is_relevant:
            relevant_files.append(file_info)
        else:
            other_files.append(file_info)
    
    result = relevant_files[:max_files//2]
    
    sorted_other = sorted(other_files, key=lambda x: x.get('timestamp', 0), reverse=True)
    remaining_slots = max_files - len(result)
    result.extend(sorted_other[:remaining_slots])
    
    print(f"[INFO] Smart loading: {len(relevant_files)} relevant + {len(result) - len(relevant_files)} latest files")
    return result 