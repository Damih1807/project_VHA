from error.error_codes import ErrorCode
import re
from typing import List, Dict, Any
from models.models_db import FileDocument
from section_map import SECTION_PAGE_MAP
from urllib.parse import unquote_plus
from flask import Response, stream_with_context
import os
import json
def api_response(error_code, message: str = None, data: any = None) -> dict:
    return {
        "status": error_code,
        "message": message or ErrorCode.get_message(error_code),
        "data": data
    }

def message_response(error_codes, message: str) -> dict:
    return {
        "status": error_codes,
        "message": message
    }
def url_response(error_codes, message: str = None, data: any = None, references: list = None):
    if references:
        ref_content = "\n\n**Tài liệu tham khảo:**\n"
        for i, ref in enumerate(references, 1):
            file_name = ref.get('file_name', 'Unknown').replace('.pdf', '').replace('.docx', '').replace('.txt', '')
            file_url = ref.get('file_url', '')
            
            if file_url:
                ref_content += f"{i}. [{file_name}]({file_url})\n"
            else:
                ref_content += f"{i}. {file_name}\n"
        
        yield sse_event("delta", {"content": ref_content})
    return {
        "data": data,
        "status": error_codes,
        "message": message
    }

    

    
    
    
    
    
    



def extract_references_from_docs(docs: List[Any], response: str = "", question: str = "") -> List[Dict[str, Any]]:
    """
    Trích xuất thông tin tài liệu tham khảo từ docs dựa trên RESPONSE EVIDENCE làm chính (80%) và question support làm phụ (20%)
    """
    from urllib.parse import quote, urlsplit, urlunsplit
    import re
    from difflib import SequenceMatcher

    references = []
    seen_files = set()


    db_files = FileDocument.query.all()
    for db_file in db_files:
        print(f"[DEBUG] - {db_file.file_name}")

    def calculate_response_evidence(doc_content: str, response: str) -> float:
        """Tính bằng chứng document được sử dụng trong response - ĐÂY LÀ CHÍNH"""
        if not doc_content or not response:
            return 0.0
        
        doc_content = re.sub(r'\s+', ' ', doc_content.lower().strip())
        response = re.sub(r'\s+', ' ', response.lower().strip())
        
        total_score = 0.0
        
        exact_matches = []
        doc_sentences = [s.strip() for s in doc_content.split('.') if len(s.strip()) > 15]
        
        for doc_sent in doc_sentences:
            doc_sent_clean = doc_sent.strip()
            if len(doc_sent_clean) > 20:
                if doc_sent_clean in response:
                    match_length = len(doc_sent_clean)
                    exact_matches.append(match_length)
                    print(f"[DEBUG] EXACT MATCH found: '{doc_sent_clean[:50]}...'")
                
                elif len(doc_sent_clean) > 30:
                    words = doc_sent_clean.split()
                    for i in range(len(words) - 5):
                        phrase = ' '.join(words[i:i+6])
                        if phrase in response:
                            exact_matches.append(len(phrase))
                            print(f"[DEBUG] PHRASE MATCH found: '{phrase}'")
        
        exact_score = sum(exact_matches) / max(len(doc_content), 1)
        exact_score = min(exact_score * 2, 1.0)
        
        response_concepts = extract_key_concepts_from_response(response)
        doc_concepts = extract_key_concepts_from_text(doc_content)
        
        concept_score = 0.0
        matched_concepts = []
        
        for resp_concept in response_concepts:
            for doc_concept in doc_concepts:
                similarity = calculate_concept_similarity(resp_concept, doc_concept)
                if similarity > 0.7:
                    concept_score += similarity
                    matched_concepts.append((resp_concept, doc_concept, similarity))
        
        concept_score = min(concept_score / max(len(response_concepts), 1), 1.0)
        
        if matched_concepts:
            print(f"[DEBUG] CONCEPT MATCHES: {matched_concepts[:3]}")
        
        numeric_score = calculate_numeric_consistency(doc_content, response)
        
        terminology_score = calculate_terminology_overlap(doc_content, response)
        
        total_score = (
            exact_score * 0.50 +
            concept_score * 0.30 +
            numeric_score * 0.15 +
            terminology_score * 0.05
        )
        
        print(f"[DEBUG] Response Evidence Breakdown:")
        print(f"  - Exact matches: {exact_score:.3f} (weight: 0.50)")
        print(f"  - Concept match: {concept_score:.3f} (weight: 0.30)")
        print(f"  - Numeric match: {numeric_score:.3f} (weight: 0.15)")
        print(f"  - Terminology: {terminology_score:.3f} (weight: 0.05)")
        print(f"  - TOTAL RESPONSE EVIDENCE: {total_score:.3f}")
        
        return min(total_score, 1.0)

    def extract_key_concepts_from_response(response: str) -> List[str]:
        """Trích xuất concepts chính từ response"""
        concepts = []
        
        values = re.findall(r'\d+(?:[.,]\d+)*\s*(?:ngày|tháng|năm|triệu|nghìn|đồng|%|phần trăm)', response, re.IGNORECASE)
        concepts.extend(values)
        
        policies = re.findall(r'(?:quy định|chính sách|điều khoản|theo|được|phải|có thể|không được)\s+[^.!?]{10,50}', response, re.IGNORECASE)
        concepts.extend([p.strip() for p in policies])
        
        actions = re.findall(r'(?:cần|phải|nên|có thể|được)\s+[^.!?]{5,30}', response, re.IGNORECASE)
        concepts.extend([a.strip() for a in actions])
        
        hr_terms = re.findall(r'(?:lương|thưởng|phép|nghỉ|bảo hiểm|hợp đồng|tuyển dụng|đào tạo)\s*[^.!?]{0,20}', response, re.IGNORECASE)
        concepts.extend([term.strip() for term in hr_terms])
        
        return [c for c in concepts if len(c) > 5]

    def extract_key_concepts_from_text(text: str) -> List[str]:
        """Trích xuất concepts từ document text"""
        concepts = []
        
        sentences = [s.strip() for s in text.split('.') if len(s.strip()) > 20]
        for sentence in sentences[:10]:
            phrases = re.findall(r'[^,;]{15,60}', sentence)
            concepts.extend([p.strip() for p in phrases])
        
        return concepts

    def calculate_concept_similarity(concept1: str, concept2: str) -> float:
        """Tính similarity giữa 2 concepts"""
        if not concept1 or not concept2:
            return 0.0
        
        c1 = re.sub(r'\s+', ' ', concept1.lower().strip())
        c2 = re.sub(r'\s+', ' ', concept2.lower().strip())
        
        if c1 == c2:
            return 1.0
        
        if c1 in c2 or c2 in c1:
            return 0.8
        
        words1 = set(c1.split())
        words2 = set(c2.split())
        if words1 and words2:
            overlap = len(words1.intersection(words2)) / len(words1.union(words2))
            if overlap > 0.5:
                return overlap * 0.7
        
        return 0.0

    def calculate_numeric_consistency(doc_content: str, response: str) -> float:
        """Kiểm tra consistency của số liệu giữa doc và response"""
        doc_numbers = set(re.findall(r'\d+(?:[.,]\d+)*', doc_content))
        response_numbers = set(re.findall(r'\d+(?:[.,]\d+)*', response))
        
        if not response_numbers:
            return 0.0
        
        matched_numbers = doc_numbers.intersection(response_numbers)
        consistency = len(matched_numbers) / len(response_numbers)
        
        if matched_numbers:
            print(f"[DEBUG] NUMERIC MATCHES: {list(matched_numbers)[:5]}")
        
        return consistency

    def calculate_terminology_overlap(doc_content: str, response: str) -> float:
        """Tính overlap của terminology chuyên ngành"""
        hr_terms = [
            'lương', 'thưởng', 'phép', 'nghỉ', 'bảo hiểm', 'hợp đồng', 
            'tuyển dụng', 'đào tạo', 'kỷ luật', 'chấm công', 'overtime',
            'probation', 'appraisal', 'benefit', 'allowance'
        ]
        
        doc_terms = [term for term in hr_terms if term in doc_content.lower()]
        response_terms = [term for term in hr_terms if term in response.lower()]
        
        if not response_terms:
            return 0.0
        
        matched_terms = set(doc_terms).intersection(set(response_terms))
        return len(matched_terms) / len(response_terms)

    def calculate_question_support(doc_content: str, question: str) -> float:
        """Tính mức độ document support question - ĐÂY LÀ PHỤ"""
        if not doc_content or not question:
            return 0.0
        
        doc_content = re.sub(r'\s+', ' ', doc_content.lower().strip())
        question = re.sub(r'\s+', ' ', question.lower().strip())
        
        # Kiểm tra nếu document quá ngắn hoặc không có nội dung có ý nghĩa
        if len(doc_content.strip()) < 10:
            print(f"[DEBUG] Document too short: {len(doc_content)} chars")
            return 0.0
        
        # Stop words tiếng Việt mở rộng
        stop_words = {'là', 'của', 'và', 'có', 'được', 'trong', 'với', 'theo', 'để', 'từ', 'về', 
                     'như', 'thế', 'nào', 'gì', 'khi', 'mà', 'này', 'đó', 'những', 'các', 'một', 
                     'bao', 'nhiêu', 'tôi', 'tui', 'mình', 'chúng', 'chúng ta', 'họ', 'nó', 
                     'em', 'anh', 'chị', 'ạ', 'ơi', 'à', 'ư', 'hả', 'ha', 'hì', 'hở'}
        
        # Làm sạch dấu câu và ký tự đặc biệt
        question_clean = re.sub(r'[^\w\s]', ' ', question)
        doc_clean = re.sub(r'[^\w\s]', ' ', doc_content)
        
        question_words = set(question_clean.split()) - stop_words
        doc_words = set(doc_clean.split()) - stop_words
        
        # Lọc bỏ từ quá ngắn (< 2 ký tự)
        question_words = {w for w in question_words if len(w) >= 2}
        doc_words = {w for w in doc_words if len(w) >= 2}
        
        # Kiểm tra nếu không có từ khóa có ý nghĩa trong câu hỏi
        if not question_words:
            print(f"[DEBUG] No meaningful keywords in question after filtering")
            return 0.0
        
        # Tính keyword overlap
        common_words = question_words.intersection(doc_words)
        keyword_overlap = len(common_words) / len(question_words)
        
        # Debug info cho keyword overlap
        if keyword_overlap == 0.0:
            print(f"[DEBUG] No keyword overlap found")
            print(f"  Question words: {sorted(list(question_words))[:5]}")
            print(f"  Doc words sample: {sorted(list(doc_words))[:10]}")
        else:
            print(f"[DEBUG] Keyword overlap: {keyword_overlap:.3f}")
            print(f"  Common words: {sorted(list(common_words))[:5]}")
        
        # Topic categories với từ khóa mở rộng
        topic_categories = {
            'lương_thưởng': ['lương', 'thưởng', 'salary', 'bonus', 'tiền lương', 'thu nhập', 'phụ cấp', 'mức lương', 'lương cơ bản', 'tăng lương'],
            'nghỉ_phép': ['nghỉ', 'phép', 'leave', 'vacation', 'ngày nghỉ', 'đơn nghỉ', 'nghỉ ốm', 'nghỉ thai sản', 'annual leave'],
            'bảo_hiểm': ['bảo hiểm', 'bhxh', 'bhyt', 'insurance', 'phúc lợi', 'social insurance', 'health insurance'],
            'quy_trình': ['quy trình', 'thủ tục', 'hướng dẫn', 'cách thức', 'process', 'procedure', 'workflow'],
            'chính_sách': ['chính sách', 'quy định', 'điều khoản', 'policy', 'rule', 'regulation'],
            'tuyển_dụng': ['tuyển dụng', 'tuyển', 'recruitment', 'hiring', 'ứng tuyển', 'phỏng vấn', 'interview']
        }
        
        topic_score = 0.0
        matched_category = None
        
        for category, keywords in topic_categories.items():
            question_has = any(kw in question for kw in keywords)
            doc_has = any(kw in doc_content for kw in keywords)
            if question_has and doc_has:
                topic_score = 0.8
                matched_category = category
                print(f"[DEBUG] Strong topic match: {category}")
                break
            elif question_has:
                topic_score = max(topic_score, 0.1)
        
        # Nếu không có topic nào khớp và keyword overlap cũng rất thấp
        if topic_score == 0.0 and keyword_overlap < 0.1:
            print(f"[DEBUG] No meaningful match - document not relevant to question")
            return 0.0
        
        support_score = (keyword_overlap * 0.7) + (topic_score * 0.3)
        
        if matched_category:
            print(f"[DEBUG] Topic category matched: {matched_category}")
        
        return min(support_score, 1.0)

    doc_scores = []
    
    for i, doc in enumerate(docs):

        if hasattr(doc, 'metadata') and doc.metadata and hasattr(doc, 'page_content'):
            source = doc.metadata.get('source')
            section = doc.metadata.get("section", "N/A").strip()
            doc_content = doc.page_content if hasattr(doc, 'page_content') else ""


            if source and doc_content:
                response_evidence = calculate_response_evidence(doc_content, response)
                
                question_support = calculate_question_support(doc_content, question)
                
                retrieval_score = doc.metadata.get("similarity_score", 0.0)
                if hasattr(retrieval_score, 'item'):
                    retrieval_score = float(retrieval_score.item())
                else:
                    retrieval_score = float(retrieval_score)
                
                final_score = (
                    response_evidence * 0.80 +
                    question_support * 0.20
                )
                
                
                doc_scores.append({
                    'doc': doc,
                    'source': source,
                    'section': section,
                    'final_score': final_score,
                    'response_evidence': response_evidence,
                    'question_support': question_support,
                    'retrieval_score': retrieval_score
                })

    if doc_scores:
        doc_scores.sort(key=lambda x: x['final_score'], reverse=True)
        
        print(f"\n[DEBUG] === FINAL DOCUMENT RANKING ===")
        for i, doc_info in enumerate(doc_scores[:5], 1):
            print(f"{i}. {doc_info['source']}")
            print(f"   Final: {doc_info['final_score']:.3f} | Response: {doc_info['response_evidence']:.3f} | Question: {doc_info['question_support']:.3f}")
        
        top_doc = doc_scores[0]
        
        if len(doc_scores) > 1:
            second_score = doc_scores[1]['final_score']
            score_gap = top_doc['final_score'] - second_score
            
            if top_doc['response_evidence'] > 0.3:
                threshold = 0.1
            elif score_gap > 0.15:
                threshold = 0.05
            else:
                threshold = 0.2
        else:
            threshold = 0.15
        
        if top_doc['final_score'] >= threshold:
            used_docs = [top_doc]
            print(f"\n[DEBUG] ✅ SELECTED: {top_doc['source']}")
            print(f"    🎯 Response Evidence: {top_doc['response_evidence']:.3f}")
            print(f"    ❓ Question Support: {top_doc['question_support']:.3f}")
            print(f"    🏆 Final Score: {top_doc['final_score']:.3f}")
        else:
            top_by_response = sorted(doc_scores, key=lambda x: x['response_evidence'], reverse=True)[0]
            
            if top_by_response['response_evidence'] > 0.1:
                used_docs = [top_by_response]
                print(f"\n[DEBUG] 📋 RESPONSE-BASED FALLBACK: {top_by_response['source']}")
                print(f"    🎯 Response Evidence: {top_by_response['response_evidence']:.3f}")
            else:
                used_docs = []
                print(f"\n[DEBUG] ❌ No documents have sufficient evidence")
    else:
        used_docs = []
        print(f"\n[DEBUG] ❌ No documents available for analysis")

    for doc_info in used_docs:
        source = doc_info['source']
        section = doc_info['section']
        
        file_doc = None

        file_doc = FileDocument.query.filter_by(file_name=source).first()

        if not file_doc:
            clean_source = source.replace('.pdf', '').replace('.txt', '').replace('.docx', '')
            file_doc = FileDocument.query.filter_by(file_name=clean_source).first()

        if not file_doc:
            clean_source = re.sub(r'_\d+_[a-f0-9]+', '', source)
            clean_source = clean_source.replace('.pdf', '').replace('.txt', '').replace('.docx', '')
            for db_file in db_files:
                if clean_source.lower() in db_file.file_name.lower() or db_file.file_name.lower() in clean_source.lower():
                    file_doc = db_file
                    break

        if file_doc and file_doc.file_name not in seen_files:
            seen_files.add(file_doc.file_name)

            object_url = file_doc.file_url

            page_number = SECTION_PAGE_MAP.get(section, 1)
            parts = urlsplit(object_url)
            url_with_page = urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, f"page={page_number}"))

            citation_html = f'<a href="{url_with_page}" class="citation-link" target="_blank">[Nguồn: {file_doc.file_name}{f" - {section}" if section and section != "N/A" else ""}]</a>'

            reference = {
                "file_name": file_doc.file_name,
                "file_url": object_url,
                "section": section,
                "similarity_score": doc_info['retrieval_score'],
                "response_evidence": doc_info['response_evidence'],
                "final_score": doc_info['final_score'],
                "citation_html": citation_html
            }
            references.append(reference)
            break

    if not references and docs:
        print(f"\n[DEBUG] ❌ NO REFERENCES: No documents have sufficient evidence for this query")
        print(f"[DEBUG] � FALLBACK DISABLED: Will not provide any references for irrelevant documents")

    return references

def format_references_in_response(response: str, references: List[Dict[str, Any]]) -> str:
    if len(response.split()) < 30:
        # Không nối references nếu response ngắn
        return response
    """
    Format câu trả lời với tài liệu tham khảo
    """
    if not references:
        return response
    
    reference_text = "\n\n**Tài liệu tham khảo:**\n"
    for i, ref in enumerate(references, 1):
        file_name = ref.get('file_name', 'Unknown').replace('.pdf', '').replace('.docx', '').replace('.txt', '')
        file_url = ref.get('file_url', '')
        
        if file_url:
            reference_text += f"{i}. [{file_name}]({file_url})\n"
        else:
            reference_text += f"{i}. {file_name}\n"
    
    return response + reference_text

def get_file_info_by_id(file_id: str) -> Dict[str, Any]:
    """
    Lấy thông tin file theo ID
    """
    file_doc = FileDocument.query.filter_by(id=file_id).first()
    if file_doc:
        return {
            'id': file_doc.id,
            'file_name': file_doc.file_name,
            'file_url': file_doc.file_url,
            'content_type': file_doc.content_type
        }
    return None

def create_streaming_response(generator_func, content_type="text/plain"):
    """
    Tạo streaming response từ generator function
    """
    from flask import Response, stream_with_context
    
    def generate():
        try:
            for chunk in generator_func():
                if chunk:
                    yield f"data: {chunk}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            error_chunk = f"data: [ERROR] {str(e)}\n\n"
            yield error_chunk
    
    return Response(
        stream_with_context(generate()),
        content_type="text/event-stream",
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Cache-Control'
        }
    )

def stream_response_chunks(response_text: str, chunk_size: int = 50):
    """
    Chia response thành các chunks nhỏ để stream
    """
    import re
    
    if not response_text or not response_text.strip():
        return
    
    sentences = re.split(r'([.!?]+)', response_text)
    current_chunk = ""
    
    for i in range(0, len(sentences), 2):
        sentence = sentences[i]
        punctuation = sentences[i + 1] if i + 1 < len(sentences) else ""
        full_sentence = sentence + punctuation
        
        if len(current_chunk + full_sentence) <= chunk_size:
            current_chunk += full_sentence
        else:
            if current_chunk and current_chunk.strip():
                yield current_chunk.strip()
            current_chunk = full_sentence
    
    if current_chunk and current_chunk.strip():
        yield current_chunk.strip()

FENCE_RE = re.compile(r"(^|\n)```")
SAFE_BORDER = re.compile(r"(?:\n{2,}|^#{1,6}\s|^\d+\.\s|^-\s|[.!?]\s)$", re.MULTILINE)

class MarkdownChunker:
    def __init__(self):
        self.buf = ""
        self.fence_open = False

    def _update_fence_state(self, text: str):
        count = len(FENCE_RE.findall(text))
        if count % 2 == 1:
            self.fence_open = not self.fence_open

    def push(self, delta: str):
        if not delta:
            return None
        self.buf += delta
        self._update_fence_state(delta)
        if (not self.fence_open) and SAFE_BORDER.search(self.buf):
            out = self.buf
            self.buf = ""
            return out
        return None

    def flush(self):
        out = self.buf
        self.buf = ""
        self.fence_open = False
        return out


LINK_HTML = re.compile(r'<a\s+href="([^"]+)">(.*?)</a>', re.IGNORECASE)

def convert_html_links_to_markdown(htmlish: str) -> str:
    text = LINK_HTML.sub(r'[\2](\1)', htmlish)

    url_pattern = re.compile(r'(https?://[^\s\)\]]+|www\.[^\s\)\]]+|[a-zA-Z0-9.-]+\.amazonaws\.com/[^\s\)\]]+|[a-zA-Z0-9.-]+\.[a-z]{2,}(?:/[^\s\)\]]*)?)', re.IGNORECASE)
    markdown_link_pattern = re.compile(r'\[([^\]]*)\]\(([^\)]+)\)')
    
    file_path_pattern = re.compile(r'[a-zA-Z0-9]+(?:[-][a-zA-Z0-9]+){3,}(?:\.[a-z]+)?', re.IGNORECASE)
    
    protected_items = []
    
    def protect_markdown_link(match):
        placeholder = f"__PROTECTED_LINK_{len(protected_items)}__"
        protected_items.append(match.group(0))
        return placeholder
    
    text = markdown_link_pattern.sub(protect_markdown_link, text)
    
    def protect_url(match):
        placeholder = f"__PROTECTED_URL_{len(protected_items)}__"
        protected_items.append(match.group(0))
        return placeholder
    
    text = url_pattern.sub(protect_url, text)
    
    def protect_file_path(match):
        placeholder = f"__PROTECTED_PATH_{len(protected_items)}__"
        protected_items.append(match.group(0))
        return placeholder
    
    text = file_path_pattern.sub(protect_file_path, text)

    text = re.sub(r'\r\n', '\n', text)
    text = re.sub(r'\s+\n', '\n', text)
    text = re.sub(r'\n\s+', '\n', text)
    text = re.sub(r' {2,}', ' ', text)

    def add_space_letter_digit(match):
        before_context = text[max(0, match.start()-10):match.start()]
        after_context = text[match.end():match.end()+10]
        full_context = before_context + match.group(0) + after_context
        
        if any(pattern in full_context.lower() for pattern in ['.com', '.amazonaws', '.pdf', 'http', 'www', 'cdbe', 'bf6', 'fae5']):
            return match.group(0)
        return match.group(1) + ' ' + match.group(2)
    
    text = re.sub(r'([A-Za-zÀ-ỹ])(\d)', add_space_letter_digit, text)
    
    def add_space_digit_letter(match):
        before_context = text[max(0, match.start()-10):match.start()]
        after_context = text[match.end():match.end()+10]
        full_context = before_context + match.group(0) + after_context
        
        if any(pattern in full_context.lower() for pattern in ['.com', '.amazonaws', '.pdf', 'http', 'www', 'cdbe', 'bf6', 'fae5']):
            return match.group(0)
        return match.group(1) + ' ' + match.group(2)
    
        text = re.sub(r'(\d)([A-Za-zÀ-ỹ])', add_space_digit_letter, text)
    
    text = re.sub(r'(\d+)(giờ|ngày|tháng|năm|tuần|phút|giây)', r'\1 \2', text)

    text = re.sub(r'([.!?])([A-ZÀ-Ỹ])', r'\1 \2', text)

    text = re.sub(r'\s*:\s*([A-ZÀ-Ỹ])', r': \1', text)

    text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
    
    for i, item in enumerate(protected_items):
        if item.startswith('[') and '](' in item:
            text = text.replace(f"__PROTECTED_LINK_{i}__", item)
        elif any(placeholder in text for placeholder in [f"__PROTECTED_PATH_{i}__"]):
            text = text.replace(f"__PROTECTED_PATH_{i}__", item)
        else:
            text = text.replace(f"__PROTECTED_URL_{i}__", item)

    return text.strip()


    
    
    
    
    
    
    

def close_unfinished_fences(md: str) -> str:
    if md.count("```") % 2 == 1:
        md += "\n```"
    return md

def soft_markdown_finalize(raw: str) -> str:
    md = convert_html_links_to_markdown(raw)
    md = close_unfinished_fences(md)
    return md

def stream_llm_response(
    prompt: str,
    model: str = "gpt-4o-mini",
    cancellation_check=None
):
    """
    Stream response từ LLM theo từng khối Markdown hợp lý.
    - Ưu tiên chia ở ranh giới Markdown: \n\n, tiêu đề (
    - Không trim để giữ nguyên khoảng trắng & xuống dòng.
    """
    from utils.user.llm_services import chatgpt_generate_stream

    BORDER_PATTERN = re.compile(
        r"(?:\n\n|^#{1,6}\s|^\d+\.\s|^-{1}\s|[.!?]\s)$", re.MULTILINE
    )

    try:
        buffer = ""
        for delta in chatgpt_generate_stream(
            prompt, model=model, cancellation_check=cancellation_check
        ):
            if cancellation_check and cancellation_check():
                print("[INFO] LLM response stream cancelled")
                return

            if not delta:
                continue

            if delta.strip() and delta not in ['{}', '{"content": ""}', '{"response": ""}', 'null', 'undefined']:
                buffer += delta

                if BORDER_PATTERN.search(buffer):
                    if buffer.strip():
                        yield buffer
                    buffer = ""

        if buffer.strip():
            yield buffer

    except Exception as e:
        yield f"Lỗi hệ thống: {str(e)}"

def sse_event(event: str, data: dict):
    payload = f"event: {event}\n" + f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
    return payload

def sse_text_event(event: str, text: str):
    payload = f"event: {event}\n" + f"data: {text}\n\n"
    return payload

def sse_response(generator):
    return Response(stream_with_context(generator), mimetype="text/event-stream")

def llm_delta_stream(prompt: str, model: str, cancellation_check=None):
    from utils.user.llm_services import chatgpt_generate_stream
    for delta in chatgpt_generate_stream(prompt, model=model, cancellation_check=cancellation_check):
        if cancellation_check and cancellation_check():
            break
        if delta:
            yield delta

def stream_with_references(response_generator, references: List[Dict[str, Any]] = None):
    """
    Stream response kèm theo references với SSE format
    """
    for chunk in response_generator:
        if chunk:
            clean_chunk = chunk
            if chunk.startswith('{"model":'):
                import re
                clean_chunk = re.sub(r'^\{"model":\s*"[^"]*"\}', '', chunk)
            
            clean_chunk = clean_chunk.replace('****', '').strip()
            clean_chunk = clean_chunk.replace('{}', '').strip()
            if clean_chunk != '{}' and clean_chunk:
                yield sse_text_event("delta", clean_chunk)
    
    if references:
        ref_content = "\n\n**Tài liệu tham khảo:**\n"
        for i, ref in enumerate(references, 1):
            file_name = ref.get('file_name', 'Unknown').replace('.pdf', '').replace('.docx', '').replace('.txt', '')
            file_url = ref.get('file_url', '')
            
            if file_url:
                ref_content += f"{i}. [{file_name}]({file_url})\n"
            else:
                ref_content += f"{i}. {file_name}\n"
        
        yield sse_event("delta", {"content": ref_content})

def create_streaming_api_response(status: int, message: str, data: any = None):
    """
    Tạo streaming API response format
    """
    import json
    response_data = {
        "status": status,
        "message": message,
        "data": data
    }
    return f"data: {json.dumps(response_data, ensure_ascii=False)}\n\n"

