import json
import time
import hashlib
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import redis
import pickle
from collections import deque
import logging

@dataclass
class Message:
    """Đại diện cho một tin nhắn trong cuộc hội thoại"""
    role: str
    content: str
    timestamp: float
    message_id: str
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

@dataclass
class Conversation:
    """Đại diện cho một cuộc hội thoại"""
    conversation_id: str
    user_id: str
    created_at: float
    last_updated: float
    messages: List[Message]
    context_summary: str = ""
    key_topics: List[str] = None
    sentiment: str = "neutral"
    complexity_level: str = "medium"
    
    def __post_init__(self):
        if self.key_topics is None:
            self.key_topics = []

class ConversationMemory:
    """Quản lý bộ nhớ hội thoại với Redis và local cache"""
    
    def __init__(self, redis_host='localhost', redis_port=6379, redis_db=0):
        self.redis_enabled = True
        self.redis_client = None
        
        try:
            self.redis_client = redis.Redis(
                host=redis_host, 
                port=redis_port, 
                db=redis_db,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5
            )
            self.redis_client.ping()
            print(f"[INFO] Redis connection established: {redis_host}:{redis_port}")
        except Exception as e:
            print(f"[WARNING] Redis connection failed: {e}. Falling back to local-only mode.")
            self.redis_enabled = False
            self.redis_client = None
        
        self._local_cache = {}
        self._cache_ttl = 300
        
        self.max_messages_per_conversation = 50
        self.max_conversations_per_user = 10
        self.context_window_size = 10
        
        self.logger = logging.getLogger(__name__)
    
    def _generate_conversation_id(self, user_id: str) -> str:
        """Tạo conversation ID duy nhất"""
        timestamp = str(time.time())
        return hashlib.md5(f"{user_id}_{timestamp}".encode()).hexdigest()
    
    def _generate_message_id(self, content: str, timestamp: float) -> str:
        """Tạo message ID duy nhất"""
        return hashlib.md5(f"{content}_{timestamp}".encode()).hexdigest()
    
    def create_conversation(self, user_id: str) -> str:
        """Tạo cuộc hội thoại mới"""
        conversation_id = self._generate_conversation_id(user_id)
        now = time.time()
        
        conversation = Conversation(
            conversation_id=conversation_id,
            user_id=user_id,
            created_at=now,
            last_updated=now,
            messages=[],
            context_summary="",
            key_topics=[],
            sentiment="neutral",
            complexity_level="medium"
        )
        
        self._save_conversation_to_redis(conversation)
        
        self._local_cache[conversation_id] = {
            'conversation': conversation,
            'timestamp': now
        }
        
        self.logger.info(f"Created new conversation {conversation_id} for user {user_id}")
        return conversation_id
    
    def add_message(self, conversation_id: str, role: str, content: str, metadata: Dict[str, Any] = None) -> str:
        """Thêm tin nhắn vào cuộc hội thoại"""
        conversation = self.get_conversation(conversation_id)
        if not conversation:
            raise ValueError(f"Conversation {conversation_id} not found")
        
        timestamp = time.time()
        message_id = self._generate_message_id(content, timestamp)
        
        message = Message(
            role=role,
            content=content,
            timestamp=timestamp,
            message_id=message_id,
            metadata=metadata or {}
        )
        
        conversation.messages.append(message)
        conversation.last_updated = timestamp
        
        if len(conversation.messages) > self.max_messages_per_conversation:
            conversation.messages = conversation.messages[-self.max_messages_per_conversation:]
        
        self._update_context_summary(conversation)
        
        self._update_key_topics(conversation)
        
        self._update_sentiment(conversation)
        
        self._save_conversation_to_redis(conversation)
        
        self._local_cache[conversation_id] = {
            'conversation': conversation,
            'timestamp': timestamp
        }
        
        self.logger.info(f"Added message {message_id} to conversation {conversation_id}")
        return message_id
    
    def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        """Lấy cuộc hội thoại từ cache hoặc Redis"""
        if conversation_id in self._local_cache:
            cache_entry = self._local_cache[conversation_id]
            if time.time() - cache_entry['timestamp'] < self._cache_ttl:
                return cache_entry['conversation']
            else:
                del self._local_cache[conversation_id]
        
        conversation = self._load_conversation_from_redis(conversation_id)
        if conversation:
            self._local_cache[conversation_id] = {
                'conversation': conversation,
                'timestamp': time.time()
            }
        
        return conversation
    
    def get_user_conversations(self, user_id: str, limit: int = None) -> List[Conversation]:
        """Lấy tất cả cuộc hội thoại của user"""
        if limit is None:
            limit = self.max_conversations_per_user
        
        pattern = f"user_conversations:{user_id}:*"
        conversation_keys = self.redis_client.keys(pattern)
        
        conversations = []
        for key in conversation_keys[-limit:]:
            conversation_id = key.split(':')[-1]
            conversation = self.get_conversation(conversation_id)
            if conversation:
                conversations.append(conversation)
        
        conversations.sort(key=lambda x: x.last_updated, reverse=True)
        return conversations
    
    def get_conversation_context(self, conversation_id: str, window_size: int = None) -> str:
        """Lấy context của cuộc hội thoại (các tin nhắn gần nhất)"""
        conversation = self.get_conversation(conversation_id)
        if not conversation:
            return ""
        
        if window_size is None:
            window_size = self.context_window_size
        
        recent_messages = conversation.messages[-window_size:]
        
        context_parts = []
        for msg in recent_messages:
            role_prefix = "U" if msg.role == "user" else "A"
            context_parts.append(f"{role_prefix}: {msg.content}")
        
        return "\n".join(context_parts)
    
    def get_conversation_summary(self, conversation_id: str) -> Dict[str, Any]:
        """Lấy tóm tắt cuộc hội thoại"""
        conversation = self.get_conversation(conversation_id)
        if not conversation:
            return {}
        
        return {
            'conversation_id': conversation.conversation_id,
            'user_id': conversation.user_id,
            'created_at': conversation.created_at,
            'last_updated': conversation.last_updated,
            'message_count': len(conversation.messages),
            'context_summary': conversation.context_summary,
            'key_topics': conversation.key_topics,
            'sentiment': conversation.sentiment,
            'complexity_level': conversation.complexity_level,
            'duration_minutes': (conversation.last_updated - conversation.created_at) / 60
        }
    
    def search_conversations(self, user_id: str, query: str) -> List[Conversation]:
        """Tìm kiếm cuộc hội thoại dựa trên nội dung"""
        conversations = self.get_user_conversations(user_id)
        matching_conversations = []
        
        query_lower = query.lower()
        
        for conversation in conversations:
            if query_lower in conversation.context_summary.lower():
                matching_conversations.append(conversation)
                continue
            
            if any(query_lower in topic.lower() for topic in conversation.key_topics):
                matching_conversations.append(conversation)
                continue
            
            for message in conversation.messages:
                if query_lower in message.content.lower():
                    matching_conversations.append(conversation)
                    break
        
        return matching_conversations
    
    def delete_conversation(self, conversation_id: str) -> bool:
        """Xóa cuộc hội thoại"""
        try:
            self.redis_client.delete(f"conversation:{conversation_id}")
            
            if conversation_id in self._local_cache:
                del self._local_cache[conversation_id]
            
            self.logger.info(f"Deleted conversation {conversation_id}")
            return True
        except Exception as e:
            self.logger.error(f"Error deleting conversation {conversation_id}: {e}")
            return False
    
    def cleanup_old_conversations(self, days_old: int = 30) -> int:
        """Dọn dẹp các cuộc hội thoại cũ"""
        cutoff_time = time.time() - (days_old * 24 * 60 * 60)
        deleted_count = 0
        
        pattern = "conversation:*"
        conversation_keys = self.redis_client.keys(pattern)
        
        for key in conversation_keys:
            try:
                conversation_data = self.redis_client.get(key)
                if conversation_data:
                    conversation = pickle.loads(conversation_data)
                    if conversation.last_updated < cutoff_time:
                        self.delete_conversation(conversation.conversation_id)
                        deleted_count += 1
            except Exception as e:
                self.logger.error(f"Error processing conversation key {key}: {e}")
        
        self.logger.info(f"Cleaned up {deleted_count} old conversations")
        return deleted_count
    
    def _save_conversation_to_redis(self, conversation: Conversation):
        """Lưu conversation vào Redis"""
        if not self.redis_enabled or not self.redis_client:
            self._local_cache[conversation.conversation_id] = {
                'conversation': conversation,
                'timestamp': time.time()
            }
            return
            
        try:
            conversation_data = pickle.dumps(conversation)
            
            self.redis_client.setex(
                f"conversation:{conversation.conversation_id}",
                86400,
                conversation_data
            )
            
            self.redis_client.zadd(
                f"user_conversations:{conversation.user_id}",
                {conversation.conversation_id: conversation.last_updated}
            )
            
        except Exception as e:
            self.logger.error(f"Error saving conversation to Redis: {e}")
            self._local_cache[conversation.conversation_id] = {
                'conversation': conversation,
                'timestamp': time.time()
            }
    
    def _load_conversation_from_redis(self, conversation_id: str) -> Optional[Conversation]:
        """Load conversation từ Redis"""
        if not self.redis_enabled or not self.redis_client:
            cache_entry = self._local_cache.get(conversation_id)
            if cache_entry and time.time() - cache_entry['timestamp'] < self._cache_ttl:
                return cache_entry['conversation']
            return None
            
        try:
            conversation_data = self.redis_client.get(f"conversation:{conversation_id}")
            if conversation_data:
                return pickle.loads(conversation_data)
        except Exception as e:
            self.logger.error(f"Error loading conversation from Redis: {e}")
            cache_entry = self._local_cache.get(conversation_id)
            if cache_entry and time.time() - cache_entry['timestamp'] < self._cache_ttl:
                return cache_entry['conversation']
        
        return None
    
    def _update_context_summary(self, conversation: Conversation):
        """Cập nhật tóm tắt context"""
        if not conversation.messages:
            conversation.context_summary = ""
            return
        
        recent_messages = conversation.messages[-self.context_window_size:]
        
        user_messages = [msg.content for msg in recent_messages if msg.role == "user"]
        assistant_messages = [msg.content for msg in recent_messages if msg.role == "assistant"]
        
        summary_parts = []
        if user_messages:
            summary_parts.append(f"User topics: {', '.join(user_messages[-3:])}")
        if assistant_messages:
            summary_parts.append(f"Assistant responses: {len(assistant_messages)} messages")
        
        conversation.context_summary = " | ".join(summary_parts)
    
    def _update_key_topics(self, conversation: Conversation):
        """Cập nhật các chủ đề chính"""
        if not conversation.messages:
            conversation.key_topics = []
            return
        
        recent_content = " ".join([msg.content for msg in conversation.messages[-10:]])
        
        keywords = []
        content_lower = recent_content.lower()
        
        hr_keywords = ['lương', 'thưởng', 'nghỉ phép', 'bảo hiểm', 'hợp đồng', 'kpi', 'đánh giá']
        for keyword in hr_keywords:
            if keyword in content_lower:
                keywords.append(keyword)
        
        tech_keywords = ['hệ thống', 'công nghệ', 'phần mềm', 'database', 'api', 'deploy']
        for keyword in tech_keywords:
            if keyword in content_lower:
                keywords.append(keyword)
        
        conversation.key_topics = list(set(keywords))[:5]
    
    def _update_sentiment(self, conversation: Conversation):
        """Cập nhật sentiment của cuộc hội thoại"""
        if not conversation.messages:
            conversation.sentiment = "neutral"
            return
        
        positive_words = ['tốt', 'hay', 'thích', 'hài lòng', 'tuyệt vời', 'cảm ơn']
        negative_words = ['xấu', 'tệ', 'không thích', 'không hài lòng', 'lỗi', 'vấn đề']
        
        recent_content = " ".join([msg.content.lower() for msg in conversation.messages[-5:]])
        
        positive_count = sum(1 for word in positive_words if word in recent_content)
        negative_count = sum(1 for word in negative_words if word in recent_content)
        
        if positive_count > negative_count:
            conversation.sentiment = "positive"
        elif negative_count > positive_count:
            conversation.sentiment = "negative"
        else:
            conversation.sentiment = "neutral"
    
    def get_memory_stats(self) -> Dict[str, Any]:
        """Lấy thống kê về memory usage"""
        try:
            redis_info = self.redis_client.info()
            
            conversation_keys = self.redis_client.keys("conversation:*")
            user_keys = self.redis_client.keys("user_conversations:*")
            
            return {
                'total_conversations': len(conversation_keys),
                'total_users': len(user_keys),
                'redis_memory_usage': redis_info.get('used_memory_human', 'N/A'),
                'local_cache_size': len(self._local_cache),
                'cache_hit_rate': 'N/A'
            }
        except Exception as e:
            self.logger.error(f"Error getting memory stats: {e}")
            return {}

conversation_memory = ConversationMemory()

def get_conversation_memory() -> ConversationMemory:
    """Get global conversation memory instance"""
    return conversation_memory

def create_user_conversation(user_id: str) -> str:
    """Tạo cuộc hội thoại mới cho user"""
    return conversation_memory.create_conversation(user_id)

def add_message_to_conversation(conversation_id: str, role: str, content: str, metadata: Dict[str, Any] = None) -> str:
    """Thêm tin nhắn vào cuộc hội thoại"""
    return conversation_memory.add_message(conversation_id, role, content, metadata)

def get_conversation_context(conversation_id: str, window_size: int = None) -> str:
    """Lấy context của cuộc hội thoại"""
    return conversation_memory.get_conversation_context(conversation_id, window_size)

def get_user_conversations(user_id: str, limit: int = None) -> List[Conversation]:
    """Lấy tất cả cuộc hội thoại của user"""
    return conversation_memory.get_user_conversations(user_id, limit) 