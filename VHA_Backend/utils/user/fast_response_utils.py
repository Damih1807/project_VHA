"""
Fast Response Utils for Chitchat and HR Partner Questions
Provides immediate responses without heavy LLM processing
"""

import json
import os
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Tuple
import re

class FastResponseHandler:
    def __init__(self):
        self.chitchat_data = None
        self.hr_data = None
        self.hr_quick_data = None
        self.data_loaded = False
        
    def load_data(self):
        """Load chitchat and HR data from JSON files"""
        if self.data_loaded:
            return
            
        try:
            # Load chitchat data
            chitchat_path = os.path.join(os.path.dirname(__file__), '..', '..', 'data_chatting', 'enhanced_chitchat_data.json')
            with open(chitchat_path, 'r', encoding='utf-8') as f:
                self.chitchat_data = json.load(f)
                
            # Load HR data  
            hr_path = os.path.join(os.path.dirname(__file__), '..', '..', 'data_chatting', 'hr_training_data.json')
            with open(hr_path, 'r', encoding='utf-8') as f:
                self.hr_data = json.load(f)
                
            # Load HR quick responses
            hr_quick_path = os.path.join(os.path.dirname(__file__), '..', '..', 'data_chatting', 'hr_quick_responses.json')
            with open(hr_quick_path, 'r', encoding='utf-8') as f:
                self.hr_quick_data = json.load(f)
                
            self.data_loaded = True
            print(f"[FAST_RESPONSE] Loaded {len(self.chitchat_data)} chitchat responses, {len(self.hr_data)} HR categories, and {len(self.hr_quick_data)} HR quick responses")
            
        except Exception as e:
            print(f"[WARNING] Failed to load fast response data: {e}")
            self.chitchat_data = []
            self.hr_data = []
            self.hr_quick_data = []
            self.data_loaded = True

    def normalize_text(self, text: str) -> str:
        """Normalize text for better matching"""
        text = text.lower().strip()
        # Remove extra spaces
        text = re.sub(r'\s+', ' ', text)
        # Remove punctuation
        text = re.sub(r'[^\w\s]', '', text)
        return text

    def contains_hr_keywords(self, question: str) -> bool:
        """Check if question contains HR-related keywords"""
        hr_keywords = [
            # Company info - Enhanced with VINOVA specific terms
            'vinova', 'công ty', 'company', 'doanh nghiệp', 'tập đoàn',
            'giới thiệu', 'introduce', 'about', 'mô tả', 'describe',
            
            # HR policies
            'nghỉ phép', 'leave', 'lương', 'salary', 'remote', 'ot', 'overtime',
            'thiết bị', 'equipment', 'bảo hiểm', 'insurance', 'hợp đồng', 'contract',
            
            # Company culture & values
            'văn hóa', 'culture', 'giá trị', 'values', 'môi trường', 'environment',
            'sứ mệnh', 'mission', 'tầm nhìn', 'vision', 'tinh thần', 'spirit',
            
            # Training & career
            'thực tập', 'internship', 'đào tạo', 'training', 'phát triển', 'development',
            'kỹ năng', 'skills', 'nghề nghiệp', 'career', 'tuyển dụng', 'recruitment',
            
            # Company operations
            'văn phòng', 'office', 'khách hàng', 'customer', 'client', 'dự án', 'project',
            'dịch vụ', 'service', 'giải thưởng', 'award', 'chứng nhận', 'certification',
            'thị trường', 'market', 'hợp tác', 'cooperation', 'partnership',
            
            # Work processes
            'làm việc', 'work', 'quy trình', 'process', 'quy định', 'regulation',
            'hỗ trợ', 'support', 'liên hệ', 'contact', 'ứng tuyển', 'apply'
        ]
        
        question_lower = question.lower()
        
        # Special handling for VINOVA detection
        if 'vinova' in question_lower:
            return True
            
        # Check for company introduction patterns
        company_patterns = [
            'giới thiệu về công ty',
            'công ty làm gì',
            'company làm gì',
            'về công ty',
            'about company'
        ]
        
        for pattern in company_patterns:
            if pattern in question_lower:
                return True
        
        # Check regular keywords
        for keyword in hr_keywords:
            if keyword in question_lower:
                return True
                
        return False

    def classify_question_type(self, question: str) -> str:
        """Classify question type to determine appropriate link to add"""
        question_lower = question.lower()
        
        # Keywords for recruitment/application
        recruitment_keywords = [
            'tuyển dụng', 'recruitment', 'ứng tuyển', 'apply', 'thực tập', 'internship',
            'tuyển', 'hiring', 'job', 'việc làm', 'career', 'nghề nghiệp',
            'cv', 'resume', 'hồ sơ', 'ứng viên', 'candidate',
            'văn hóa', 'culture', 'văn hoá', 'môi trường làm việc', 'work environment'
        ]
        
        # Keywords for company introduction
        introduction_keywords = [
            'giới thiệu', 'introduce', 'vinova là gì', 'công ty làm gì', 'về vinova',
            'about vinova', 'mô tả', 'describe', 'tổng quan', 'overview',
            'dịch vụ', 'service', 'sản phẩm', 'product', 'khách hàng', 'client',
            'giá trị', 'values', 'slogan', 'sứ mệnh', 'mission', 'tầm nhìn', 'vision'
        ]
        
        # Keywords for contact/inquiry
        contact_keywords = [
            'liên hệ', 'contact', 'hỏi thêm', 'ask more', 'thắc mắc', 'inquiry',
            'tư vấn', 'consult', 'hỗ trợ', 'support', 'email', 'phone', 'address'
        ]
        
        # Check for recruitment-related questions
        for keyword in recruitment_keywords:
            if keyword in question_lower:
                return 'recruitment'
        
        # Check for introduction-related questions
        for keyword in introduction_keywords:
            if keyword in question_lower:
                return 'introduction'
        
        # Check for contact-related questions
        for keyword in contact_keywords:
            if keyword in question_lower:
                return 'contact'
        
        return 'general'

    def add_appropriate_link(self, response: str, question: str) -> str:
        """Add appropriate link based on question type"""
        question_type = self.classify_question_type(question)
        
        # Don't add links if response already contains a URL
        if 'http' in response:
            return response
        
        if question_type == 'recruitment':
            return f"{response}\n\n💼 **Tìm hiểu thêm về cơ hội nghề nghiệp tại Vinova:** https://vinova.sg/jobs/"
        
        elif question_type == 'introduction':
            return f"{response}\n\n🌐 **Tìm hiểu thêm về Vinova:** https://vinova.sg/"
        
        elif question_type == 'contact':
            return f"{response}\n\n📞 **Liên hệ với chúng tôi để được hỗ trợ:** https://vinova.sg/contact/"
        
        else:
            # For general HR questions, add contact link if response seems incomplete
            if len(response) < 200 or 'liên hệ' in response.lower() or 'hr' in response.lower():
                return f"{response}\n\n📞 **Cần hỗ trợ thêm? Liên hệ với chúng tôi:** https://vinova.sg/contact/"
        
        return response

    def calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity between two texts with improved algorithm"""
        norm1 = self.normalize_text(text1)
        norm2 = self.normalize_text(text2)
        
        # Basic similarity
        basic_score = SequenceMatcher(None, norm1, norm2).ratio()
        
        # Keyword matching bonus
        words1 = set(norm1.split())
        words2 = set(norm2.split())
        common_words = words1.intersection(words2)
        keyword_bonus = len(common_words) / max(len(words1), len(words2)) if words1 or words2 else 0
        
        final_score = (basic_score * 0.6) + (keyword_bonus * 0.3)
        
        return min(final_score, 1.0)

    def find_chitchat_response(self, question: str, threshold: float = 0.8) -> Optional[str]:
        """Find immediate chitchat response if available"""
        self.load_data()
        
        if not self.chitchat_data:
            return None
            
        best_match = None
        best_score = 0
        
        for item in self.chitchat_data:
            if 'question' in item and 'response' in item:
                score = self.calculate_similarity(question, item['question'])
                if score > best_score and score >= threshold:
                    best_score = score
                    best_match = item['response']
                    
        if best_match:
            print(f"[FAST_RESPONSE] Chitchat match found with score {best_score:.2f}")
            return best_match
            
        return None

    def find_hr_response(self, question: str, threshold: float = 0.5) -> Optional[str]:
        """Find immediate HR response if available with improved matching"""
        self.load_data()
        
        # First check if question contains HR keywords
        if not self.contains_hr_keywords(question):
            print(f"[FAST_RESPONSE] No HR keywords detected in: {question}")
            return None
        
        print(f"[FAST_RESPONSE] HR keywords detected, searching responses...")
                
        if self.hr_quick_data:
            best_match = None
            best_score = 0
            best_item = None
            
            for item in self.hr_quick_data:
                if 'question' in item and 'response' in item:
                    score = self.calculate_similarity(question, item['question'])
                    if score > best_score and score >= threshold:
                        best_score = score
                        best_match = item['response']
                        best_item = item
                        
            if best_match:
                category = best_item.get('category', 'General')
                print(f"[FAST_RESPONSE] HR quick response match found - Category: {category}, Score: {best_score:.3f}")
                print(f"[FAST_RESPONSE] Matched question: {best_item['question']}")
                                
                # Add appropriate link based on question type
                enhanced_response = self.add_appropriate_link(best_match, question)
                return enhanced_response
            else:
                print(f"[FAST_RESPONSE] No HR quick response found above threshold {threshold}")
        
        # If no quick response found, try general HR categories
        if not self.hr_data:
            return None
            
        # Search through HR categories and questions
        for category_data in self.hr_data:
            if 'category' in category_data and 'questions' in category_data:
                category = category_data['category']
                questions = category_data['questions']
                
                for hr_question in questions:
                    score = self.calculate_similarity(question, hr_question)
                    if score >= threshold:
                        # Generate a helpful response pointing to the category
                        response = f"""Câu hỏi của bạn thuộc về **{category}**. 

Để có thông tin chi tiết và chính xác nhất, tôi khuyên bạn nên:

1. **Liên hệ trực tiếp với bộ phận HR** để được tư vấn cụ thể
2. **Tham khảo tài liệu chính sách** có sẵn trong hệ thống
3. **Đặt câu hỏi cụ thể hơn** về chính sách mà bạn quan tâm

Bạn có muốn tôi tìm kiếm thông tin chi tiết trong tài liệu chính sách không?"""
                        
                        print(f"[FAST_RESPONSE] HR category match found in '{category}' with score {score:.2f}")
                        
                        enhanced_response = self.add_appropriate_link(response, question)
                        return enhanced_response
                        
        return None

    def get_fast_response(self, question: str, intent: str) -> Optional[str]:
        """Get immediate response for chitchat or HR questions"""
        if intent == 'chitchat':
            return self.find_chitchat_response(question)
        elif intent in ['hr_inquiry', 'hr_partner', 'policy_inquiry']:
            return self.find_hr_response(question)
        else:
            return None

# Global instance
fast_response_handler = FastResponseHandler()

def get_immediate_response(question: str, intent: str) -> Optional[str]:
    """Get immediate response if available for chitchat or HR questions"""
    return fast_response_handler.get_fast_response(question, intent)

def is_fast_response_available(intent: str) -> bool:
    """Check if fast response is available for this intent"""
    return intent in ['chitchat', 'hr_inquiry', 'hr_partner', 'policy_inquiry']
