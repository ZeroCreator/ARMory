import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Enum, Boolean, text
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
    comments = relationship("ProjectComment", back_populates="project", cascade="all, delete-orphan", lazy="selectin", order_by="ProjectComment.created_at")
    task_statuses = relationship("TaskStatus", back_populates="project", cascade="all, delete-orphan", lazy="selectin", order_by="TaskStatus.sort_order")
    tasks = relationship("Task", back_populates="project", cascade="all, delete-orphan", lazy="selectin", order_by="Task.sort_order")


class Section(Base):
    __tablename__ = "sections"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    collapsed = Column(Boolean, nullable=False, default=True, server_default=text("1"))
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
    collapsed = Column(Boolean, nullable=False, default=True, server_default=text("1"))
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
    collapsed = Column(Boolean, nullable=False, default=True)
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


class ProjectComment(Base):
    __tablename__ = "project_comments"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    author_email = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    project = relationship("Project", back_populates="comments")


class ProjectCommentRead(Base):
    __tablename__ = "project_comment_reads"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    user_email = Column(String(255), nullable=False)
    last_read_at = Column(DateTime, default=datetime.datetime.utcnow)


class CalendarEvent(Base):
    __tablename__ = "calendar_events"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    note = Column(Text, nullable=True)
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=True)
    all_day = Column(Boolean, default=False)
    color = Column(String(7), default="#a78bfa")
    reminder_minutes = Column(Integer, nullable=True)
    notified_at = Column(DateTime, nullable=True)
    dismissed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class Affair(Base):
    __tablename__ = "affairs"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    owner_email = Column(String(255), nullable=False, index=True)
    is_shared = Column(Boolean, nullable=False, default=False, server_default=text("0"), index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    due_date = Column(DateTime, nullable=True)
    is_completed = Column(Boolean, nullable=False, default=False, server_default=text("0"))
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    project = relationship("Project", lazy="selectin")


class Assignee(Base):
    __tablename__ = "assignees"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False, unique=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class TaskAssignee(Base):
    __tablename__ = "task_assignees"

    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True)
    assignee_email = Column(String(255), nullable=False, primary_key=True)

    task = relationship("Task", back_populates="assignees")


class TaskStatus(Base):
    __tablename__ = "task_statuses"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    color = Column(String(7), nullable=False, default="#a78bfa")
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, server_default=text("CURRENT_TIMESTAMP"))

    project = relationship("Project", back_populates="task_statuses")
    tasks = relationship("Task", back_populates="status", cascade="all, delete-orphan", lazy="selectin", order_by="Task.sort_order")


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    status_id = Column(Integer, ForeignKey("task_statuses.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    priority = Column(String(20), nullable=False, default="medium")
    is_closed = Column(Boolean, nullable=False, default=False, server_default=text("0"))
    start_date = Column(DateTime, nullable=True)
    due_date = Column(DateTime, nullable=True)
    assignee_email = Column(String(255), nullable=True)
    tags = Column(String(500), nullable=True)
    list_name = Column(String(255), nullable=True, index=True)
    result = Column(Text, nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    project = relationship("Project", back_populates="tasks", lazy="selectin")
    status = relationship("TaskStatus", back_populates="tasks", lazy="selectin")
    assignees = relationship("TaskAssignee", back_populates="task", cascade="all, delete-orphan", lazy="selectin", order_by="TaskAssignee.assignee_email")
    attachments = relationship("TaskAttachment", back_populates="task", cascade="all, delete-orphan", lazy="selectin", order_by="TaskAttachment.created_at.asc()")
    status_history = relationship("TaskStatusHistory", back_populates="task", cascade="all, delete-orphan", lazy="selectin", order_by="TaskStatusHistory.entered_at.asc()")

    @property
    def assignee_emails(self):
        emails = [a.assignee_email for a in self.assignees]
        if not emails and self.assignee_email:
            emails = [self.assignee_email]
        return emails

    @property
    def first_assignee_email(self):
        return self.assignee_emails[0] if self.assignee_emails else None


class TaskStatusHistory(Base):
    __tablename__ = "task_status_history"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    status_id = Column(Integer, ForeignKey("task_statuses.id", ondelete="CASCADE"), nullable=False)
    entered_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    task = relationship("Task", back_populates="status_history")
    status = relationship("TaskStatus", lazy="selectin")


class TaskAttachment(Base):
    __tablename__ = "task_attachments"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    attachment_type = Column(String(20), nullable=False)  # file, link, git
    title = Column(String(255), nullable=True)
    url = Column(String(1000), nullable=True)
    file_path = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    task = relationship("Task", back_populates="attachments")
