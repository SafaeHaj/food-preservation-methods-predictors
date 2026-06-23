import json
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey,
    Integer, String, Text, JSON
)
from sqlalchemy.orm import relationship

from app.db.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    projects = relationship("Project", back_populates="owner")


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, default="")
    schema_json = Column(Text, default="[]")  # JSON list of field definitions
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    owner = relationship("User", back_populates="projects")
    papers = relationship("Paper", back_populates="project", cascade="all, delete-orphan")

    @property
    def schema(self):
        return json.loads(self.schema_json) if self.schema_json else []


class Paper(Base):
    __tablename__ = "papers"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    filename = Column(String, nullable=False)
    original_name = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    page_count = Column(Integer, default=0)
    status = Column(String, default="uploaded")  # uploaded | extracting | extracted | reviewed | error
    error_message = Column(Text, default="")
    uploaded_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project", back_populates="papers")
    rows = relationship("ExtractedRow", back_populates="paper", cascade="all, delete-orphan")


class ExtractedRow(Base):
    __tablename__ = "extracted_rows"

    id = Column(Integer, primary_key=True, index=True)
    paper_id = Column(Integer, ForeignKey("papers.id"), nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    data_json = Column(Text, default="{}")       # field_name -> value
    provenance_json = Column(Text, default="{}")  # field_name -> {page, table, confidence}
    status = Column(String, default="pending")   # pending | approved | rejected | edited
    reviewer_note = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    paper = relationship("Paper", back_populates="rows")

    @property
    def data(self):
        return json.loads(self.data_json) if self.data_json else {}

    @property
    def provenance(self):
        return json.loads(self.provenance_json) if self.provenance_json else {}
