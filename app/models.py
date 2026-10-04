import datetime
from sqlalchemy import Column, Integer, String, Date, DateTime, Text, ForeignKey, Enum, Boolean, Index, JSON, text
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


class DailyNewsRead(Base):
    __tablename__ = "daily_news_reads"

    id = Column(Integer, primary_key=True)
    user_email = Column(String(255), nullable=False, unique=True, index=True)
    dismissed_date = Column(Date, nullable=True)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


class Affair(Base):
    __tablename__ = "affairs"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    owner_email = Column(String(255), nullable=False, index=True)
    is_shared = Column(Boolean, nullable=False, default=False, server_default=text("0"), index=True)
    show_in_news = Column(Boolean, nullable=False, default=False, server_default=text("0"), index=True)
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
    estimated_minutes = Column(Integer, nullable=True)
    manual_work_seconds = Column(Integer, nullable=True)
    manual_work_session_baseline = Column(Integer, nullable=False, default=0, server_default=text("0"))
    manual_testing_seconds = Column(Integer, nullable=True)
    manual_testing_session_baseline = Column(Integer, nullable=False, default=0, server_default=text("0"))
    manual_actual_seconds = Column(Integer, nullable=True)
    manual_actual_session_baseline = Column(Integer, nullable=False, default=0, server_default=text("0"))
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    project = relationship("Project", back_populates="tasks", lazy="selectin")
    status = relationship("TaskStatus", back_populates="tasks", lazy="selectin")
    assignees = relationship("TaskAssignee", back_populates="task", cascade="all, delete-orphan", lazy="selectin", order_by="TaskAssignee.assignee_email")
    attachments = relationship("TaskAttachment", back_populates="task", cascade="all, delete-orphan", lazy="selectin", order_by="TaskAttachment.created_at.asc()")
    status_history = relationship("TaskStatusHistory", back_populates="task", cascade="all, delete-orphan", lazy="selectin", order_by="TaskStatusHistory.entered_at.asc()")
    time_sessions = relationship("TaskTimeSession", back_populates="task", cascade="all, delete-orphan", lazy="selectin", order_by="TaskTimeSession.started_at.asc()")

    @property
    def assignee_emails(self):
        emails = [a.assignee_email for a in self.assignees]
        if not emails and self.assignee_email:
            emails = [self.assignee_email]
        return emails

    @property
    def first_assignee_email(self):
        return self.assignee_emails[0] if self.assignee_emails else None

    def _tracked_time_for_phase(self, phase: str) -> int:
        total = 0
        now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        for session in self.time_sessions:
            if session.phase != phase:
                continue
            started_at = session.started_at
            ended_at = session.ended_at or now
            if started_at.tzinfo is not None:
                started_at = started_at.astimezone(datetime.timezone.utc).replace(tzinfo=None)
            if ended_at.tzinfo is not None:
                ended_at = ended_at.astimezone(datetime.timezone.utc).replace(tzinfo=None)
            total += max(0, int((ended_at - started_at).total_seconds()))
        return total

    def _time_for_phase(self, phase: str) -> int:
        tracked = self._tracked_time_for_phase(phase)
        if phase == "work" and self.manual_work_seconds is not None:
            return self.manual_work_seconds + max(0, tracked - self.manual_work_session_baseline)
        if phase == "testing" and self.manual_testing_seconds is not None:
            return self.manual_testing_seconds + max(0, tracked - self.manual_testing_session_baseline)
        return tracked

    @property
    def work_seconds(self) -> int:
        return self._time_for_phase("work")

    @property
    def testing_seconds(self) -> int:
        return self._time_for_phase("testing")

    @property
    def actual_seconds(self) -> int:
        if self.manual_actual_seconds is not None:
            tracked = self._tracked_time_for_phase("work") + self._tracked_time_for_phase("testing")
            return self.manual_actual_seconds + max(0, tracked - self.manual_actual_session_baseline)
        return self.work_seconds + self.testing_seconds

    @property
    def manual_time_phase(self) -> str | None:
        """Возвращает этап активного ручного таймера."""
        return next((session.phase for session in self.time_sessions
                     if session.ended_at is None and session.worker_id == f"manual:task:{self.id}"), None)

    @property
    def time_tracking_status(self) -> str | None:
        """Возвращает состояние учёта времени независимо от колонки Kanban."""
        if any(session.ended_at is None for session in self.time_sessions):
            return "running"
        if not self.time_sessions:
            return None
        latest = max(self.time_sessions, key=lambda session: (session.ended_at, session.started_at, session.id or 0))
        return "completed" if latest.completed else "paused"


class TaskStatusHistory(Base):
    __tablename__ = "task_status_history"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    status_id = Column(Integer, ForeignKey("task_statuses.id", ondelete="CASCADE"), nullable=False)
    entered_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    task = relationship("Task", back_populates="status_history")
    status = relationship("TaskStatus", lazy="selectin")


class TaskTimeSession(Base):
    __tablename__ = "task_time_sessions"
    __table_args__ = (
        Index(
            "uq_task_time_sessions_worker_active",
            "worker_id",
            unique=True,
            sqlite_where=text("ended_at IS NULL"),
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    worker_id = Column(String(128), nullable=False, index=True)
    phase = Column(String(20), nullable=False)
    started_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)
    completed = Column(Boolean, nullable=False, default=False, server_default=text("0"))

    task = relationship("Task", back_populates="time_sessions")


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


class AuthLoginToken(Base):
    __tablename__ = "auth_login_tokens"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), nullable=False, index=True)
    token_hash = Column(String(64), nullable=False, unique=True, index=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)


class AuthUser(Base):
    __tablename__ = "auth_users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
        nullable=False,
    )


class MCPOAuthClient(Base):
    __tablename__ = "mcp_oauth_clients"

    client_id = Column(String(64), primary_key=True)
    client_info = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)


class MCPOAuthGrant(Base):
    __tablename__ = "mcp_oauth_grants"

    id = Column(String(64), primary_key=True)
    client_id = Column(String(64), ForeignKey("mcp_oauth_clients.client_id", ondelete="CASCADE"), nullable=False, index=True)
    redirect_uri = Column(Text, nullable=False)
    redirect_uri_provided_explicitly = Column(Boolean, nullable=False, default=True)
    state = Column(Text, nullable=False)
    code_challenge = Column(String(128), nullable=False)
    code_challenge_method = Column(String(8), nullable=False)
    scopes = Column(JSON, nullable=False)
    resource = Column(Text, nullable=False)
    user_email = Column(String(255), nullable=True)
    code_hash = Column(String(64), nullable=True, unique=True, index=True)
    status = Column(String(16), nullable=False, default="pending", index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)
    used_at = Column(DateTime, nullable=True)


class MCPOAuthToken(Base):
    __tablename__ = "mcp_oauth_tokens"

    token_hash = Column(String(64), primary_key=True)
    token_type = Column(String(16), nullable=False, index=True)
    family_id = Column(String(64), nullable=False, index=True)
    client_id = Column(String(64), ForeignKey("mcp_oauth_clients.client_id", ondelete="CASCADE"), nullable=False, index=True)
    user_email = Column(String(255), nullable=False, index=True)
    scopes = Column(JSON, nullable=False)
    resource = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)
    revoked_at = Column(DateTime, nullable=True)
