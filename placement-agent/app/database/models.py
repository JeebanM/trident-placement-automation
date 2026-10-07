"""
app/database/models.py
──────────────────────
SQLAlchemy ORM models.
"""
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class EligibilityStatus(str, PyEnum):
    ELIGIBLE = "eligible"
    REVIEW = "review"
    INELIGIBLE = "ineligible"
    PENDING = "pending"


class NotificationStatus(str, PyEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"


class PlacementPost(Base):
    __tablename__ = "placement_posts"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(1000), nullable=False)
    post_url = Column(String(2000), nullable=False, unique=True)
    notice_hash = Column(String(64), nullable=False, unique=True, index=True)

    raw_content = Column(Text)

    published_at = Column(DateTime(timezone=True))
    discovered_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    processing_status = Column(String(50), default="pending")

    documents = relationship("PlacementDocument", back_populates="post", cascade="all, delete-orphan")
    extracted_data = relationship("ExtractedData", back_populates="post", uselist=False, cascade="all, delete-orphan")
    eligibility_result = relationship("EligibilityResult", back_populates="post", uselist=False, cascade="all, delete-orphan")
    notification_logs = relationship("NotificationLog", back_populates="post", cascade="all, delete-orphan")
    processing_logs = relationship("ProcessingLog", back_populates="post", cascade="all, delete-orphan")


class PlacementDocument(Base):
    __tablename__ = "placement_documents"

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("placement_posts.id"), nullable=False, index=True)

    file_url = Column(String(2000), nullable=False)
    file_hash = Column(String(64))
    filename = Column(String(500))
    mime_type = Column(String(100))

    extracted_text = Column(Text)
    extraction_method = Column(String(20))
    page_count = Column(Integer)

    download_status = Column(String(20), default="pending")
    processing_status = Column(String(20), default="pending")

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    post = relationship("PlacementPost", back_populates="documents")


class ExtractedData(Base):
    __tablename__ = "extracted_data"

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("placement_posts.id"), nullable=False, unique=True)

    company_name = Column(String(500))
    program_name = Column(String(500))
    job_role = Column(String(500))
    job_type = Column(String(100))
    location = Column(JSON)
    eligible_degrees = Column(JSON)
    minimum_10th_percentage = Column(Float)
    minimum_12th_percentage = Column(Float)
    minimum_cgpa = Column(Float)
    graduation_years = Column(JSON)
    backlog_allowed = Column(Boolean)
    salary = Column(String(200))
    notice_date = Column(String(100))
    application_deadline = Column(String(100))
    application_link = Column(String(2000))
    notice_link = Column(String(2000))
    eligibility_text = Column(Text)

    structured_json = Column(JSON)

    llm_confidence = Column(Float)
    extraction_model = Column(String(100))
    extraction_attempts = Column(Integer, default=1)

    extracted_at = Column(DateTime(timezone=True), server_default=func.now())

    post = relationship("PlacementPost", back_populates="extracted_data")


class EligibilityResult(Base):
    __tablename__ = "eligibility_results"

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("placement_posts.id"), nullable=False, unique=True)

    status = Column(String(20), nullable=False)
    is_eligible = Column(Boolean)
    confidence = Column(Float)
    reason = Column(Text)
    rules_triggered = Column(JSON)

    evaluated_at = Column(DateTime(timezone=True), server_default=func.now())

    post = relationship("PlacementPost", back_populates="eligibility_result")


class NotificationLog(Base):
    __tablename__ = "notification_logs"
    __table_args__ = (UniqueConstraint('post_id', 'recipient', name='uq_post_recipient'),)

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("placement_posts.id"), nullable=False)

    status = Column(String(20), default="pending")
    recipient = Column(String(500))
    subject = Column(String(1000))
    sent_at = Column(DateTime(timezone=True))
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)

    post = relationship("PlacementPost", back_populates="notification_logs")


class ProcessingLog(Base):
    __tablename__ = "processing_logs"

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("placement_posts.id"), nullable=True)

    step = Column(String(100))
    status = Column(String(20))
    message = Column(Text)
    duration_ms = Column(Integer)
    retry_count = Column(Integer, default=0)
    error = Column(Text)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    post = relationship("PlacementPost", back_populates="processing_logs")
