from config.database import db
from datetime import datetime
import uuid

from models.email_models import EmailTemplate, EmailKeyword, ContactEmail, TeamStructure, EmailConversation

class ConversationSession(db.Model):
    __tablename__ = "conversation_sessions"

    id = db.Column(db.String(100), primary_key=True)
    email = db.Column(db.String(100), nullable=False)
    user_id = db.Column(db.String, index=True, nullable=True)
    started_at = db.Column(db.DateTime, default=datetime.now)
    last_asked_at = db.Column(db.DateTime, default=datetime.now)
    is_active = db.Column(db.Boolean, default=True)

    logs = db.relationship("ConversationLog", backref="session", cascade="all, delete-orphan", lazy=True)

class ConversationLog(db.Model):
    __tablename__ = "conversation_logs"

    id = db.Column(db.Integer, primary_key=True)
    con_id = db.Column(db.String(100), db.ForeignKey("conversation_sessions.id"), nullable=False)
    user_id = db.Column(db.String, index=True, nullable=True)
    email = db.Column(db.String(100), nullable=False)
    question = db.Column(db.Text, nullable=False)
    answer = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.now)
    topic = db.Column(db.String(100), nullable=True)

class Users(db.Model):
    __tablename__ = "users"

    user_id = db.Column(db.String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    sso_id = db.Column(db.String, unique=True, nullable=True)
    username = db.Column(db.String, unique=True, index=True, nullable=False)
    email = db.Column(db.String, unique=True, index=True, nullable=False)
    full_name = db.Column(db.String)
    role = db.Column(db.String(20), default="MEMBER", nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    last_login = db.Column(db.DateTime)
    permissions = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    logs = db.relationship("UserLogs", back_populates="user", cascade="all, delete-orphan")

class UserLogs(db.Model):
    __tablename__ = "user_logs"
    
    id = db.Column(db.String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.String, db.ForeignKey("users.user_id"), nullable=False)
    refresh_token = db.Column(db.Text, nullable=False, unique=True)
    username = db.Column(db.String, nullable=False)
    email = db.Column(db.String, nullable=False)
    full_name = db.Column(db.String) 
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.now)
    user = db.relationship("Users", back_populates="logs")

class FileDocument(db.Model):
    __tablename__ = 'file_documents'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    file_name = db.Column(db.String(255), nullable=False)
    content_type = db.Column(db.String(100), nullable=False)
    file_url = db.Column(db.Text, nullable=False)
    uploaded_by = db.Column(db.String, db.ForeignKey("users.user_id"), nullable=True)
    uploaded_at = db.Column(db.DateTime, default=datetime.now)
    is_public = db.Column(db.Boolean, default=True)
    file_size = db.Column(db.Integer)
    description = db.Column(db.Text)

class TokenUsage(db.Model):
    __tablename__ = "token_usage"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.String(100), nullable=False)
    date = db.Column(db.Date, nullable=False)
    tokens_used = db.Column(db.Integer, default=0)

class UserFormConfig(db.Model):
    __tablename__ = 'user_form_config'

    user_id = db.Column(db.String, primary_key=True)
    retrieve_k = db.Column(db.Integer, nullable=False, default=20)
    rerank_k = db.Column(db.Integer, nullable=False, default=3)
    enable_rerank = db.Column(db.Boolean, nullable=False, default=True)
    model = db.Column(db.String, nullable=False, default="gpt-4.0")
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)


class GlobalConfig(db.Model):
    """Cấu hình toàn cục cho hệ thống"""
    __tablename__ = 'global_config'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    config_key = db.Column(db.String(100), nullable=False, unique=True)
    config_value = db.Column(db.Text, nullable=False)
    description = db.Column(db.String(500), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    updated_by = db.Column(db.String(36), nullable=True)

class SystemLog(db.Model):
    __tablename__ = "system_logs"
    
    id = db.Column(db.String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.String, db.ForeignKey("users.user_id"), nullable=True)
    action = db.Column(db.String(100), nullable=False)
    resource_type = db.Column(db.String(50), nullable=False)
    resource_id = db.Column(db.String, nullable=True)
    details = db.Column(db.JSON)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.now)