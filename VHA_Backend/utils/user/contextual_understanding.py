import re
import json
import time
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from collections import defaultdict
import numpy as np
from langchain_community.embeddings import BedrockEmbeddings
import boto3
import os
from dotenv import load_dotenv

load_dotenv()

@dataclass
class ContextEntity:
    """Đại diện cho một entity trong context"""
    entity_type: str
    value: str
    confidence: float
    position: Tuple[int, int]
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

@dataclass
class ContextRelation:
    """Đại diện cho mối quan hệ giữa các entities"""
    source_entity: str
    target_entity: str
    relation_type: str
    confidence: float
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

@dataclass
class ContextAnalysis:
    """Kết quả phân tích context"""
    entities: List[ContextEntity]
    relations: List[ContextRelation]
    topics: List[str]
    sentiment: str
    intent: str
    confidence: float
    summary: str

class ContextualUnderstanding:
    """Phân tích và hiểu context của cuộc hội thoại"""
    
    def __init__(self):
        session = boto3.Session(
            aws_access_key_id=os.getenv("ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("SECRET_ACCESS_KEY"),
            region_name=os.getenv("REGION")
        )
        
        bedrock_client = session.client(service_name="bedrock-runtime")
        self.embeddings = BedrockEmbeddings(
            model_id=os.getenv("MODEL_ID"),
            client=bedrock_client
        )
        
        self.entity_patterns = {
            'person': [
                r'\b[A-Z][a-z]+ [A-Z][a-z]+\b',
                r'\b(ông|bà|anh|chị|em)\s+[A-Za-zÀ-ỹ]+\b',
            ],
            'company': [
                r'\b[A-Z][A-Za-z\s&]+(?:Corp|Inc|Ltd|Company|Công ty|TNHH|JSC)\b',
                r'\bVINOVA\b',
                r'\b[A-Z][A-Za-z\s]+(?:Technology|Tech|Solutions)\b',
            ],
            'policy': [
                r'\bchính sách\s+[A-Za-zÀ-ỹ\s]+\b',
                r'\bquy định\s+[A-Za-zÀ-ỹ\s]+\b',
                r'\bthủ tục\s+[A-Za-zÀ-ỹ\s]+\b',
            ],
            'number': [
                r'\b\d+(?:,\d{3})*(?:\.\d+)?\b',
                r'\b\d+(?:,\d{3})*(?:\.\d+)?\s*(?:VND|USD|đồng|dollar)\b',
                r'\b\d+(?:\.\d+)?\s*%\b',
            ],
            'date': [
                r'\b\d{1,2}[/-]\d{1,2}[/-]\d{4}\b',
                r'\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b',
                r'\b(?:tháng|ngày|năm)\s+\d+\b',
            ],
            'duration': [
                r'\b\d+\s*(?:ngày|tháng|năm|tuần|giờ|phút)\b',
            ],
            'position': [
                r'\b(?:giám đốc|phó giám đốc|trưởng phòng|nhân viên|thực tập sinh)\b',
                r'\b(?:manager|director|employee|intern|staff)\b',
            ],
            'department': [
                r'\b(?:phòng|ban|bộ phận)\s+[A-Za-zÀ-ỹ\s]+\b',
                r'\b(?:HR|IT|Finance|Marketing|Sales|Operations)\b',
            ]
        }
        
        self.relation_patterns = {
            'works_for': [
                r'(\w+)\s+(?:làm việc tại|làm ở|thuộc)\s+(\w+)',
                r'(\w+)\s+(?:employee|staff|member)\s+(?:of|at)\s+(\w+)',
            ],
            'has_salary': [
                r'(\w+)\s+(?:có|lương|thu nhập)\s+(\d+(?:,\d{3})*(?:\.\d+)?\s*(?:VND|USD))',
                r'(\w+)\s+(?:salary|income)\s+(\d+(?:,\d{3})*(?:\.\d+)?\s*(?:VND|USD))',
            ],
            'applies_to': [
                r'(\w+)\s+(?:áp dụng cho|dành cho|cho)\s+(\w+)',
                r'(\w+)\s+(?:applies to|for)\s+(\w+)',
            ],
            'reports_to': [
                r'(\w+)\s+(?:báo cáo cho|thuộc quyền)\s+(\w+)',
                r'(\w+)\s+(?:reports to|under)\s+(\w+)',
            ],
            'has_position': [
                r'(\w+)\s+(?:là|chức vụ|vị trí)\s+(\w+)',
                r'(\w+)\s+(?:is|position|role)\s+(\w+)',
            ]
        }
        
        self.intent_patterns = {
            'question': [
                r'\b(?:bao nhiêu|như thế nào|khi nào|ở đâu|tại sao|ai|cái gì)\b',
                r'\b(?:how much|how|when|where|why|who|what)\b',
                r'\?$',
            ],
            'request': [
                r'\b(?:xin|yêu cầu|đề nghị|mong muốn|muốn)\b',
                r'\b(?:please|request|ask|want|need)\b',
            ],
            'complaint': [
                r'\b(?:phàn nàn|không hài lòng|bất mãn|vấn đề|lỗi)\b',
                r'\b(?:complaint|dissatisfied|problem|issue|error)\b',
            ],
            'appreciation': [
                r'\b(?:cảm ơn|tuyệt vời|tốt|hài lòng|thích)\b',
                r'\b(?:thank|great|good|satisfied|like)\b',
            ],
            'information': [
                r'\b(?:thông tin|chi tiết|tìm hiểu|biết)\b',
                r'\b(?:information|details|learn|know)\b',
            ]
        }
        
        self.topic_keywords = {
            'salary': ['lương', 'thưởng', 'salary', 'bonus', 'compensation'],
            'leave': ['nghỉ phép', 'nghỉ lễ', 'leave', 'holiday', 'vacation'],
            'insurance': ['bảo hiểm', 'insurance', 'health', 'medical'],
            'contract': ['hợp đồng', 'contract', 'agreement', 'terms'],
            'performance': ['kpi', 'đánh giá', 'performance', 'evaluation'],
            'training': ['đào tạo', 'training', 'course', 'learning'],
            'benefits': ['phúc lợi', 'benefits', 'perks', 'advantages'],
            'policy': ['chính sách', 'policy', 'rules', 'regulations'],
            'technical': ['hệ thống', 'công nghệ', 'technical', 'system', 'api'],
            'general': ['chung', 'general', 'overview', 'summary']
        }
        
        self.sentiment_keywords = {
            'positive': [
                'tốt', 'hay', 'thích', 'hài lòng', 'tuyệt vời', 'cảm ơn',
                'good', 'great', 'like', 'satisfied', 'excellent', 'thank'
            ],
            'negative': [
                'xấu', 'tệ', 'không thích', 'không hài lòng', 'lỗi', 'vấn đề',
                'bad', 'terrible', 'dislike', 'dissatisfied', 'error', 'problem'
            ],
            'neutral': [
                'bình thường', 'ok', 'được', 'normal', 'okay', 'fine'
            ]
        }
    
    def analyze_context(self, text: str, conversation_history: List[str] = None) -> ContextAnalysis:
        """Phân tích context của text và conversation history"""
        entities = self._extract_entities(text)
        
        relations = self._extract_relations(text, entities)
        
        topics = self._extract_topics(text)
        
        sentiment = self._analyze_sentiment(text)
        
        intent = self._analyze_intent(text)
        
        summary = self._generate_summary(text, entities, topics, intent)
        
        confidence = self._calculate_confidence(entities, relations, topics)
        
        return ContextAnalysis(
            entities=entities,
            relations=relations,
            topics=topics,
            sentiment=sentiment,
            intent=intent,
            confidence=confidence,
            summary=summary
        )
    
    def _extract_entities(self, text: str) -> List[ContextEntity]:
        """Trích xuất entities từ text"""
        entities = []
        
        for entity_type, patterns in self.entity_patterns.items():
            for pattern in patterns:
                matches = re.finditer(pattern, text, re.IGNORECASE)
                for match in matches:
                    value = match.group(0)
                    confidence = self._calculate_entity_confidence(value, entity_type)
                    
                    entity = ContextEntity(
                        entity_type=entity_type,
                        value=value,
                        confidence=confidence,
                        position=(match.start(), match.end())
                    )
                    entities.append(entity)
        
        unique_entities = []
        seen_values = set()
        for entity in entities:
            if entity.value.lower() not in seen_values:
                unique_entities.append(entity)
                seen_values.add(entity.value.lower())
        
        return unique_entities
    
    def _extract_relations(self, text: str, entities: List[ContextEntity]) -> List[ContextRelation]:
        """Trích xuất relations giữa các entities"""
        relations = []
        
        for relation_type, patterns in self.relation_patterns.items():
            for pattern in patterns:
                matches = re.finditer(pattern, text, re.IGNORECASE)
                for match in matches:
                    source = match.group(1)
                    target = match.group(2)
                    
                    source_entity = self._find_matching_entity(source, entities)
                    target_entity = self._find_matching_entity(target, entities)
                    
                    if source_entity and target_entity:
                        confidence = min(source_entity.confidence, target_entity.confidence) * 0.8
                        
                        relation = ContextRelation(
                            source_entity=source_entity.value,
                            target_entity=target_entity.value,
                            relation_type=relation_type,
                            confidence=confidence
                        )
                        relations.append(relation)
        
        return relations
    
    def _extract_topics(self, text: str) -> List[str]:
        """Trích xuất topics từ text"""
        text_lower = text.lower()
        found_topics = []
        
        for topic, keywords in self.topic_keywords.items():
            for keyword in keywords:
                if keyword in text_lower:
                    found_topics.append(topic)
                    break
        
        if not found_topics:
            found_topics.append('general')
        
        return list(set(found_topics))
    
    def _analyze_sentiment(self, text: str) -> str:
        """Phân tích sentiment của text"""
        text_lower = text.lower()
        
        positive_count = 0
        negative_count = 0
        neutral_count = 0
        
        for sentiment, keywords in self.sentiment_keywords.items():
            for keyword in keywords:
                if keyword in text_lower:
                    if sentiment == 'positive':
                        positive_count += 1
                    elif sentiment == 'negative':
                        negative_count += 1
                    else:
                        neutral_count += 1
        
        if positive_count > negative_count and positive_count > neutral_count:
            return 'positive'
        elif negative_count > positive_count and negative_count > neutral_count:
            return 'negative'
        else:
            return 'neutral'
    
    def _analyze_intent(self, text: str) -> str:
        """Phân tích intent của text"""
        text_lower = text.lower()
        
        intent_scores = defaultdict(int)
        
        for intent, patterns in self.intent_patterns.items():
            for pattern in patterns:
                if re.search(pattern, text_lower):
                    intent_scores[intent] += 1
        
        if intent_scores:
            return max(intent_scores, key=intent_scores.get)
        else:
            return 'general'
    
    def _generate_summary(self, text: str, entities: List[ContextEntity], topics: List[str], intent: str) -> str:
        """Tạo summary của context"""
        summary_parts = []
        
        summary_parts.append(f"Intent: {intent}")
        
        if topics:
            summary_parts.append(f"Topics: {', '.join(topics)}")
        
        important_entities = [e for e in entities if e.confidence > 0.7]
        if important_entities:
            entity_summary = ', '.join([f"{e.entity_type}: {e.value}" for e in important_entities[:3]])
            summary_parts.append(f"Key entities: {entity_summary}")
        
        return ' | '.join(summary_parts)
    
    def _calculate_confidence(self, entities: List[ContextEntity], relations: List[ContextRelation], topics: List[str]) -> float:
        """Tính confidence của phân tích"""
        if not entities and not relations and not topics:
            return 0.0
        
        entity_confidence = np.mean([e.confidence for e in entities]) if entities else 0.0
        relation_confidence = np.mean([r.confidence for r in relations]) if relations else 0.0
        topic_confidence = 0.8 if topics else 0.0
        
        weights = [0.4, 0.3, 0.3]
        
        total_confidence = (
            entity_confidence * weights[0] +
            relation_confidence * weights[1] +
            topic_confidence * weights[2]
        )
        
        return min(total_confidence, 1.0)
    
    def _calculate_entity_confidence(self, value: str, entity_type: str) -> float:
        """Tính confidence của entity"""
        base_confidence = 0.7
        
        if entity_type == 'person':
            if re.match(r'^[A-Z][a-z]+ [A-Z][a-z]+$', value):
                base_confidence = 0.9
        elif entity_type == 'number':
            if re.match(r'^\d+(?:,\d{3})*(?:\.\d+)?$', value):
                base_confidence = 0.95
        elif entity_type == 'date':
            if re.match(r'^\d{1,2}[/-]\d{1,2}[/-]\d{4}$', value):
                base_confidence = 0.9
        
        return base_confidence
    
    def _find_matching_entity(self, text: str, entities: List[ContextEntity]) -> Optional[ContextEntity]:
        """Tìm entity phù hợp với text"""
        text_lower = text.lower()
        
        for entity in entities:
            if text_lower in entity.value.lower() or entity.value.lower() in text_lower:
                return entity
        
        return None
    
    def get_context_embedding(self, text: str) -> List[float]:
        """Lấy embedding của context"""
        try:
            return self.embeddings.embed_query(text)
        except Exception as e:
            print(f"Error getting context embedding: {e}")
            return []
    
    def calculate_context_similarity(self, text1: str, text2: str) -> float:
        """Tính độ tương đồng giữa hai context"""
        try:
            embedding1 = self.get_context_embedding(text1)
            embedding2 = self.get_context_embedding(text2)
            
            if not embedding1 or not embedding2:
                return 0.0
            
            dot_product = np.dot(embedding1, embedding2)
            norm1 = np.linalg.norm(embedding1)
            norm2 = np.linalg.norm(embedding2)
            
            if norm1 == 0 or norm2 == 0:
                return 0.0
            
            return dot_product / (norm1 * norm2)
        except Exception as e:
            print(f"Error calculating context similarity: {e}")
            return 0.0
    
    def enhance_context_with_history(self, current_text: str, conversation_history: List[str]) -> str:
        """Tăng cường context với lịch sử hội thoại"""
        if not conversation_history:
            return current_text
        
        recent_history = conversation_history[-5:]
        
        enhanced_parts = []
        
        if recent_history:
            history_text = " | ".join(recent_history)
            enhanced_parts.append(f"Recent context: {history_text}")
        
        enhanced_parts.append(f"Current: {current_text}")
        
        return " | ".join(enhanced_parts)
    
    def get_context_suggestions(self, context_analysis: ContextAnalysis) -> List[str]:
        """Đưa ra gợi ý dựa trên context analysis"""
        suggestions = []
        
        if context_analysis.intent == 'question':
            if 'salary' in context_analysis.topics:
                suggestions.append("Bạn có muốn biết thêm về chính sách lương thưởng không?")
            elif 'leave' in context_analysis.topics:
                suggestions.append("Bạn có cần thông tin về nghỉ phép không?")
        
        if context_analysis.sentiment == 'negative':
            suggestions.append("Tôi hiểu bạn đang gặp vấn đề. Hãy cho tôi biết chi tiết hơn.")
        elif context_analysis.sentiment == 'positive':
            suggestions.append("Rất vui khi bạn hài lòng! Bạn có cần hỗ trợ gì thêm không?")
        
        if any(e.entity_type == 'person' for e in context_analysis.entities):
            suggestions.append("Bạn có muốn tôi tìm thông tin về nhân viên cụ thể không?")
        
        return suggestions

contextual_understanding = ContextualUnderstanding()

def get_contextual_understanding() -> ContextualUnderstanding:
    """Get global contextual understanding instance"""
    return contextual_understanding

def analyze_text_context(text: str, conversation_history: List[str] = None) -> ContextAnalysis:
    """Phân tích context của text"""
    return contextual_understanding.analyze_context(text, conversation_history)

def get_context_similarity(text1: str, text2: str) -> float:
    """Tính độ tương đồng giữa hai context"""
    return contextual_understanding.calculate_context_similarity(text1, text2)

def enhance_context_with_history(current_text: str, conversation_history: List[str]) -> str:
    """Tăng cường context với lịch sử"""
    return contextual_understanding.enhance_context_with_history(current_text, conversation_history) 