from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import List, Optional
from app.models import DocType


class ProjectBase(BaseModel):
    name: str
    description: Optional[str] = None


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(ProjectBase):
    name: Optional[str] = None
    description: Optional[str] = None


class DocumentItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    document_id: int
    title: Optional[str] = None
    item_type: DocType
    url: Optional[str] = None
    file_path: Optional[str] = None
    file_name: Optional[str] = None
    file_size: Optional[int] = None
    mime_type: Optional[str] = None
    category: Optional[str] = None
    content: Optional[str] = None
    sort_order: int = 0
    created_at: datetime


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    section_id: Optional[int] = None
    title: str
    description: Optional[str] = None
    category: Optional[str] = None
    sort_order: int = 0
    created_at: datetime
    updated_at: datetime
    items: List[DocumentItemOut] = []


class SectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    name: str
    description: Optional[str] = None
    sort_order: int = 0
    created_at: datetime
    documents: List[DocumentOut] = []


class SectionCreate(BaseModel):
    name: str
    description: Optional[str] = None


class SectionUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class DocumentCreate(BaseModel):
    title: str
    description: Optional[str] = None
    category: Optional[str] = None


class DocumentUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    section_id: Optional[int] = None


class DocumentItemCreate(BaseModel):
    item_type: DocType
    url: Optional[str] = None
    content: Optional[str] = None


class DocumentItemUpdate(BaseModel):
    item_type: Optional[DocType] = None
    url: Optional[str] = None
    content: Optional[str] = None


class ReorderRequest(BaseModel):
    document_ids: List[int]


class SectionReorderRequest(BaseModel):
    section_ids: List[int]


class ProjectReorderRequest(BaseModel):
    project_ids: List[int]


class ProjectOut(ProjectBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    sort_order: int = 0
    created_at: datetime
    updated_at: datetime
    documents: List[DocumentOut] = []
    sections: List[SectionOut] = []


class ProjectDetailOut(ProjectOut):
    pass


class SidebarLinkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    block_id: int
    title: str
    url: str
    note: Optional[str] = None
    sort_order: int = 0
    created_at: datetime


class SidebarLinkCreate(BaseModel):
    title: str
    url: str
    note: Optional[str] = None


class SidebarLinkUpdate(BaseModel):
    title: Optional[str] = None
    url: Optional[str] = None
    note: Optional[str] = None


class SidebarBlockOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    position: str
    title: str
    note: Optional[str] = None
    sort_order: int = 0
    created_at: datetime
    links: List[SidebarLinkOut] = []


class SidebarBlockCreate(BaseModel):
    position: str
    title: str
    note: Optional[str] = None


class SidebarBlockUpdate(BaseModel):
    title: Optional[str] = None
    position: Optional[str] = None
    note: Optional[str] = None
    sort_order: Optional[int] = None


class SidebarBlockReorderRequest(BaseModel):
    block_ids: List[int]


class SidebarLinkReorderRequest(BaseModel):
    link_ids: List[int]


# ═══════════════════════════════════════════════════
# Глоссарий
# ═══════════════════════════════════════════════════

class GlossarySubtopicOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    topic_id: int
    name: str
    sort_order: int = 0
    term_count: int = 0
    created_at: datetime


class GlossarySubtopicCreate(BaseModel):
    topic_id: int
    name: str


class GlossarySubtopicUpdate(BaseModel):
    topic_id: Optional[int] = None
    name: Optional[str] = None
    sort_order: Optional[int] = None


class GlossaryTopicShortOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    sort_order: int = 0
    term_count: int = 0
    created_at: datetime


class GlossaryTopicOut(GlossaryTopicShortOut):
    subtopics: List[GlossarySubtopicOut] = []


class GlossaryTopicCreate(BaseModel):
    name: str


class GlossaryTopicUpdate(BaseModel):
    name: Optional[str] = None
    sort_order: Optional[int] = None


class GlossaryTermOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    term: str
    short_definition: Optional[str] = None
    definition: Optional[str] = None
    letter: Optional[str] = None
    topic_id: Optional[int] = None
    topic: Optional[GlossaryTopicShortOut] = None
    subtopic_id: Optional[int] = None
    subtopic: Optional[GlossarySubtopicOut] = None
    sort_order: int = 0
    created_at: datetime
    updated_at: datetime


class GlossaryTermCreate(BaseModel):
    term: str
    short_definition: Optional[str] = None
    definition: Optional[str] = None
    topic_id: Optional[int] = None
    subtopic_id: Optional[int] = None


class GlossaryTermUpdate(BaseModel):
    term: Optional[str] = None
    short_definition: Optional[str] = None
    definition: Optional[str] = None
    topic_id: Optional[int] = None
    subtopic_id: Optional[int] = None
