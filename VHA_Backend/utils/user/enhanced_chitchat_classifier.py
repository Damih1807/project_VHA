import json
import os
from typing import List, Dict, Tuple
from langchain_community.vectorstores import FAISS
from langchain.schema import Document
from langchain.embeddings.base import Embeddings

ENHANCED_CHITCHAT_DATA = "data_chatting/enhanced_chitchat_data.json"
HR_TRAINING_DATA = "data_chatting/hr_training_data.json"
CHITCHAT_FAISS = "faiss_indexes/chitchat_index"
HR_FAISS = "faiss_indexes/hr_index"

class EnhancedChitchatClassifier:
    def __init__(self, embeddings: Embeddings):
        self.embeddings = embeddings
        self.chitchat_threshold = 1.0
        self.hr_threshold = 1.0
        
    def build_chitchat_index(self):
        """Xây dựng index cho chitchat data"""
        if not os.path.exists(ENHANCED_CHITCHAT_DATA):
            raise FileNotFoundError(f"Không tìm thấy file: {ENHANCED_CHITCHAT_DATA}")

        with open(ENHANCED_CHITCHAT_DATA, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        docs = []
        for entry in raw_data:
            content = f"Question: {entry['question']}\nResponse: {entry['response']}"
            metadata = {
                "type": "chitchat",
                "question": entry["question"],
                "response": entry["response"]
            }
            docs.append(Document(page_content=content, metadata=metadata))
            
        vectorstore = FAISS.from_documents(docs, self.embeddings)
        vectorstore.save_local(CHITCHAT_FAISS)

    def build_hr_index(self):
        """Xây dựng index cho HR training data"""
        if not os.path.exists(HR_TRAINING_DATA):
            raise FileNotFoundError(f"Không tìm thấy file: {HR_TRAINING_DATA}")

        with open(HR_TRAINING_DATA, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        docs = []
        for category in raw_data:
            category_name = category["category"]
            questions = category["questions"]
            responses = category["responses"]
            
            for i, (question, response) in enumerate(zip(questions, responses)):
                content = f"Category: {category_name}\nQuestion: {question}\nResponse: {response}"
                metadata = {
                    "type": "hr",
                    "category": category_name,
                    "question": question,
                    "response": response
                }
                docs.append(Document(page_content=content, metadata=metadata))
                
        vectorstore = FAISS.from_documents(docs, self.embeddings)
        vectorstore.save_local(HR_FAISS)

    def is_chitchat(self, question: str) -> Tuple[bool, str, float]:
        """
        Kiểm tra xem câu hỏi có phải là chitchat không
        Returns: (is_chitchat, response, confidence_score)
        """
        if not os.path.exists(os.path.join(CHITCHAT_FAISS, "index.faiss")):
            self.build_chitchat_index()

        vectorstore = FAISS.load_local(
            CHITCHAT_FAISS,
            self.embeddings,
            allow_dangerous_deserialization=True
        )

        results = vectorstore.similarity_search_with_score(question, k=1)
        
        if not results:
            return False, "", 0.0

        best_match = results[0]
        doc, score = best_match
        
        if score < self.chitchat_threshold:
            response = doc.metadata.get("response", "")
            confidence = max(0.0, (self.chitchat_threshold - score) / self.chitchat_threshold)
            return True, response, confidence
            
        return False, "", 0.0

    def get_hr_response(self, question: str) -> Tuple[str, str, float]:
        """
        Tìm câu trả lời HR phù hợp
        Returns: (response, category, confidence_score)
        """
        if not os.path.exists(os.path.join(HR_FAISS, "index.faiss")):
            self.build_hr_index()

        vectorstore = FAISS.load_local(
            HR_FAISS,
            self.embeddings,
            allow_dangerous_deserialization=True
        )

        results = vectorstore.similarity_search_with_score(question, k=1)
        
        if not results:
            return "", "", 0.0

        best_match = results[0]
        doc, score = best_match
        
        if score < self.hr_threshold:
            response = doc.metadata.get("response", "")
            category = doc.metadata.get("category", "")
            confidence = max(0.0, (self.hr_threshold - score) / self.hr_threshold)
            return response, category, confidence
            
        return "", "", 0.0

    def classify_and_respond(self, question: str) -> Tuple[str, str, float]:
        """
        Phân loại câu hỏi và trả về câu trả lời phù hợp
        Thứ tự ưu tiên: HR Training -> Chitchat -> Generate
        Returns: (response, response_type, confidence)
        """
        hr_response, hr_category, hr_confidence = self.get_hr_response(question)
        
        is_chitchat, chitchat_response, chitchat_confidence = self.is_chitchat(question)
        
        if hr_response and hr_confidence > 0.4 and hr_confidence > chitchat_confidence:
            return hr_response, f"hr_{hr_category}", hr_confidence
            
        if is_chitchat and chitchat_response and chitchat_confidence > 0.4:
            return chitchat_response, "chitchat", chitchat_confidence
            
        return "", "unknown", 0.0

    def get_suggested_questions(self, category: str = None) -> List[str]:
        """Lấy danh sách câu hỏi gợi ý"""
        suggestions = []
        
        if os.path.exists(ENHANCED_CHITCHAT_DATA):
            with open(ENHANCED_CHITCHAT_DATA, "r", encoding="utf-8") as f:
                chitchat_data = json.load(f)
                suggestions.extend([entry["question"] for entry in chitchat_data[:5]])
        
        if os.path.exists(HR_TRAINING_DATA):
            with open(HR_TRAINING_DATA, "r", encoding="utf-8") as f:
                hr_data = json.load(f)
                for cat in hr_data:
                    if category is None or cat["category"] == category:
                        suggestions.extend(cat["questions"][:3])
                        
        return suggestions[:10]

    def update_thresholds(self, chitchat_threshold: float = None, hr_threshold: float = None):
        """Cập nhật ngưỡng phân loại"""
        if chitchat_threshold is not None:
            self.chitchat_threshold = chitchat_threshold
        if hr_threshold is not None:
            self.hr_threshold = hr_threshold

def is_chitchat(question: str, embeddings: Embeddings, threshold: float = 0.3) -> bool:
    """Hàm tương thích ngược với code cũ"""
    classifier = EnhancedChitchatClassifier(embeddings)
    classifier.chitchat_threshold = threshold
    is_chitchat, _, _ = classifier.is_chitchat(question)
    return is_chitchat

def get_enhanced_response(question: str, embeddings: Embeddings) -> Tuple[str, str, float]:
    """Lấy câu trả lời cải thiện"""
    classifier = EnhancedChitchatClassifier(embeddings)
    return classifier.classify_and_respond(question) 


CHITCHAT_KEYWORDS = [
    "chào", "xin chào", "hello", "hi", "chào bạn", "hế nhô", "cảm ơn", "tạm biệt",
    "bạn là ai", "bạn làm gì", "khỏe không", "vui", "buồn", "robot", "trò chuyện",
    "kể chuyện", "tâm sự", "thích", "goodbye"
]

def is_chitchat_fast(question: str) -> bool:
    q_lower = question.lower().strip()
    return any(q_lower.startswith(kw) or f" {kw} " in f" {q_lower} " for kw in CHITCHAT_KEYWORDS)

def load_chitchat_pairs():
    pairs = {}
    try:
        with open("data_chatting/enhanced_chitchat_data.json", encoding="utf-8") as f2:
            data2 = json.load(f2)
            for item in data2:
                q = item.get("question") if isinstance(item, dict) else item
                ans = item.get("response") if isinstance(item, dict) else ""
                if q and ans:
                    pairs[q.lower()] = ans
    except Exception as e:
        print(f"[WARNING] Could not load chitchat pairs: {e}")
    return pairs

CHITCHAT_PAIRS = load_chitchat_pairs()

def get_chitchat_answer(question: str) -> str:
    q_lower = question.lower().strip()
    for k in CHITCHAT_PAIRS:
        if k in q_lower or q_lower in k:
            return CHITCHAT_PAIRS[k]
    return ""
