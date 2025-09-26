"""
Database models for email configuration
"""
from config.database import db
from datetime import datetime
from sqlalchemy import Column, String, Text, JSON, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class EmailTemplate(Base):
    """Email template model"""
    __tablename__ = 'email_templates'
    
    id = Column(String(36), primary_key=True)
    template_type = Column(String(50), nullable=False)
    language = Column(String(10), nullable=False)
    subject = Column(Text, nullable=False)
    content = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class EmailKeyword(Base):
    """Email keyword model"""
    __tablename__ = 'email_keywords'
    
    id = Column(String(36), primary_key=True)
    email_type = Column(String(50), nullable=False)
    keyword = Column(String(200), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class ContactEmail(Base):
    """Contact email model"""
    __tablename__ = 'contact_emails'
    
    id = Column(String(36), primary_key=True)
    name = Column(String(100), nullable=False)
    email = Column(String(200), nullable=False)
    role = Column(String(100))
    office = Column(String(50))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class TeamStructure(Base):
    """Team structure model"""
    __tablename__ = 'team_structures'
    
    id = Column(String(36), primary_key=True)
    office = Column(String(50), nullable=False)
    team_type = Column(String(50), nullable=False)
    contact_names = Column(JSON, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class EmailConversation(Base):
    """Email conversation state model"""
    __tablename__ = 'email_conversations'
    
    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), nullable=False)
    email_type = Column(String(50), nullable=False)
    step = Column(String(50), nullable=False)
    data = Column(JSON, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow) 


class ELeaveConfig(Base):
    """E-leave system configuration model"""
    __tablename__ = 'eleave_configs'
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    config_key = Column(String(100), nullable=False, unique=True)
    config_value = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow) 