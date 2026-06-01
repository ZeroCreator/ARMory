import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Enum, Boolean
from sqlalchemy.orm import relationship
import enum
from app.database import Base


class DocType(str, enum.Enum):
    link = "link"
    file = "file"
    note = "note"


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    sections = relationship("Section", back_populates="project", cascade="all, delete-orphan", lazy="selectin", order_by="Section.sort_order")
    documents = relationship("Document", back_populates="project", cascade="all, delete-orphan", lazy="selectin", order_by="Document.sort_order")


class Section(Base):
    __tablename__ = "sections"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    project = relationship("Project", back_populates="sections")
    documents = relationship("Document", back_populates="section", lazy="selectin", order_by="Document.sort_order")


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    section_id = Column(Integer, ForeignKey("sections.id", ondelete="SET NULL"), nullable=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(50), nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    project = relationship("Project", back_populates="documents")
    section = relationship("Section", back_populates="documents")
    items = relationship("DocumentItem", back_populates="document", cascade="all, delete-orphan", lazy="selectin", order_by="DocumentItem.sort_order")


class DocumentItem(Base):
    __tablename__ = "document_items"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    document = relationship("Document", back_populates="items")
    title = Column(String(255), nullable=True)
    item_type = Column(Enum(DocType), nullable=False)
    url = Column(Text, nullable=True)
    file_path = Column(String(500), nullable=True)
    file_name = Column(String(255), nullable=True)
    file_size = Column(Integer, nullable=True)
    mime_type = Column(String(100), nullable=True)
    category = Column(String(50), nullable=True)
    content = Column(Text, nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class SidebarBlock(Base):
    __tablename__ = "sidebar_blocks"

    id = Column(Integer, primary_key=True, index=True)
    position = Column(String(10), nullable=False, default="left")  # left | right
    title = Column(String(255), nullable=False)
    note = Column(Text, nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    links = relationship("SidebarLink", back_populates="block", cascade="all, delete-orphan", lazy="selectin", order_by="SidebarLink.sort_order")


class SidebarLink(Base):
    __tablename__ = "sidebar_links"

    id = Column(Integer, primary_key=True, index=True)
    block_id = Column(Integer, ForeignKey("sidebar_blocks.id", ondelete="CASCADE"), nullable=False)
    block = relationship("SidebarBlock", back_populates="links")
    title = Column(String(255), nullable=False)
    url = Column(Text, nullable=False)
    note = Column(Text, nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class CalendarEvent(Base):
    __tablename__ = "calendar_events"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    note = Column(Text, nullable=True)
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=True)
    all_day = Column(Boolean, default=False)
    color = Column(String(7), default="#a78bfa")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
