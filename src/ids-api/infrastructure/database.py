"""
Database models for Smart City IDS - Capstone 2 Phase 1
Implements: SQLAlchemy ORM with encryption support
"""

from datetime import datetime
from typing import Optional, List
from enum import Enum

from sqlalchemy import Column, Integer, String, DateTime, JSON, LargeBinary, Boolean, ForeignKey, Enum as SQLEnum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from cryptography.fernet import Fernet
import json
import logging

logger = logging.getLogger(__name__)

Base = declarative_base()

# Encryption key (from environment)
import os
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")

if not ENCRYPTION_KEY:
    logger.warning("ENCRYPTION_KEY not set. Using development key (DO NOT USE IN PRODUCTION)")
    ENCRYPTION_KEY = Fernet.generate_key()

cipher_suite = Fernet(ENCRYPTION_KEY)


class UserRole(str, Enum):
    """User roles"""
    ADMIN = "admin"
    ANALYST = "analyst"
    MONITOR = "monitor"
    SERVICE = "service"


class User(Base):
    """User model with authentication"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(255), unique=True, index=True, nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(SQLEnum(UserRole), default=UserRole.MONITOR, nullable=False)
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)
    
    # Relationships
    api_keys = relationship("APIKey", back_populates="user", cascade="all, delete-orphan")
    activities = relationship("AuditLog", back_populates="user", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User {self.username}>"


class APIKey(Base):
    """API keys for service-to-service authentication"""
    __tablename__ = "api_keys"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    key = Column(String(255), unique=True, index=True, nullable=False)  # Hash of actual key
    name = Column(String(255), nullable=False)
    description = Column(String(1024))
    is_active = Column(Boolean, default=True)
    last_used = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)
    
    # Relationship
    user = relationship("User", back_populates="api_keys")
    
    def __repr__(self):
        return f"<APIKey {self.name}>"


class AlertRecord(Base):
    """Alert records with encrypted sensitive data"""
    __tablename__ = "alerts"
    
    id = Column(Integer, primary_key=True, index=True)
    alert_id = Column(String(36), unique=True, index=True, nullable=False)  # UUID
    source = Column(String(50), index=True)  # falco, suricata, etc.
    rule = Column(String(512))
    severity = Column(Integer, index=True)  # 1-10
    
    # Encrypted fields
    encrypted_alert_data = Column(LargeBinary, nullable=False)  # Full alert JSON
    encrypted_analysis = Column(LargeBinary, nullable=True)  # LLM analysis result
    
    # Unencrypted metadata for querying
    alert_source_ip = Column(String(45))  # IPv4/IPv6
    alert_dest_ip = Column(String(45))
    container_name = Column(String(255), index=True)
    threat_type = Column(String(255), index=True)
    
    # Processing status
    is_analyzed = Column(Boolean, default=False)
    analysis_error = Column(String(1024), nullable=True)
    
    # Actions taken (JSON for flexibility)
    actions_taken = Column(JSON, default=list)  # List of executed automation actions
    
    # Audit fields
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    processed_at = Column(DateTime, nullable=True)
    created_by = Column(String(255), default="system")  # User/service that created this
    
    def encrypt_alert_data(self, data: dict) -> None:
        """Encrypt alert data"""
        try:
            json_str = json.dumps(data)
            self.encrypted_alert_data = cipher_suite.encrypt(json_str.encode())
            logger.debug(f"Alert {self.alert_id} data encrypted")
        except Exception as e:
            logger.error(f"Failed to encrypt alert data: {e}")
            raise
    
    def decrypt_alert_data(self) -> dict:
        """Decrypt alert data"""
        try:
            json_str = cipher_suite.decrypt(self.encrypted_alert_data).decode()
            return json.loads(json_str)
        except Exception as e:
            logger.error(f"Failed to decrypt alert data: {e}")
            raise
    
    def encrypt_analysis(self, data: dict) -> None:
        """Encrypt analysis result"""
        try:
            json_str = json.dumps(data)
            self.encrypted_analysis = cipher_suite.encrypt(json_str.encode())
            logger.debug(f"Alert {self.alert_id} analysis encrypted")
        except Exception as e:
            logger.error(f"Failed to encrypt analysis: {e}")
            raise
    
    def decrypt_analysis(self) -> Optional[dict]:
        """Decrypt analysis result"""
        if not self.encrypted_analysis:
            return None
        try:
            json_str = cipher_suite.decrypt(self.encrypted_analysis).decode()
            return json.loads(json_str)
        except Exception as e:
            logger.error(f"Failed to decrypt analysis: {e}")
            raise
    
    def __repr__(self):
        return f"<Alert {self.alert_id} severity={self.severity}>"


class AuditLog(Base):
    """Audit trail for all important actions"""
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # NULL for system actions
    action = Column(String(255), index=True, nullable=False)  # e.g., "alert:view", "pod:isolated"
    resource_type = Column(String(255), index=True)  # alert, pod, user, etc.
    resource_id = Column(String(255), index=True)  # ID of the resource acted upon
    details = Column(JSON)  # Additional context
    status = Column(String(50))  # success, failure
    error_message = Column(String(1024), nullable=True)
    ip_address = Column(String(45))
    user_agent = Column(String(512))
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Relationship
    user = relationship("User", back_populates="activities")
    
    def __repr__(self):
        return f"<AuditLog {self.action} on {self.resource_type}:{self.resource_id}>"


class AnalysisResult(Base):
    """LLM analysis results (encrypted)"""
    __tablename__ = "analysis_results"
    
    id = Column(Integer, primary_key=True, index=True)
    alert_id = Column(String(36), ForeignKey("alerts.alert_id"), nullable=False, index=True)
    
    # LLM model used
    model = Column(String(255))
    
    # Analysis result (encrypted)
    encrypted_result = Column(LargeBinary, nullable=False)
    
    # Metadata
    analysis_time_ms = Column(Integer)  # How long analysis took
    confidence_score = Column(Integer)  # 0-100
    
    # Audit
    analyzed_at = Column(DateTime, default=datetime.utcnow)
    
    def encrypt_result(self, data: dict) -> None:
        """Encrypt analysis result"""
        try:
            json_str = json.dumps(data)
            self.encrypted_result = cipher_suite.encrypt(json_str.encode())
        except Exception as e:
            logger.error(f"Failed to encrypt analysis result: {e}")
            raise
    
    def decrypt_result(self) -> dict:
        """Decrypt analysis result"""
        try:
            json_str = cipher_suite.decrypt(self.encrypted_result).decode()
            return json.loads(json_str)
        except Exception as e:
            logger.error(f"Failed to decrypt analysis result: {e}")
            raise
    
    def __repr__(self):
        return f"<AnalysisResult alert_id={self.alert_id}>"


class AutomationAction(Base):
    """Record of automated K8s actions"""
    __tablename__ = "automation_actions"
    
    id = Column(Integer, primary_key=True, index=True)
    alert_id = Column(String(36), ForeignKey("alerts.alert_id"), nullable=False, index=True)
    
    # Action details
    action_type = Column(String(255))  # isolate_pod, scale_service, etc.
    target_resource = Column(String(255))  # Pod name, service name, etc.
    target_namespace = Column(String(255))
    
    # Status
    status = Column(String(50))  # pending, executing, completed, failed
    
    # Result
    error_message = Column(String(1024), nullable=True)
    execution_time_ms = Column(Integer)
    
    # Audit
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    triggered_by = Column(String(255))  # System/user that triggered action
    
    def __repr__(self):
        return f"<AutomationAction {self.action_type} on {self.target_resource}>"
