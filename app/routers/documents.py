import os
import platform
import subprocess
from urllib.parse import urlparse
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from typing import Optional

from app.database import get_db
from app.models import Document, DocumentItem, Project, Section, DocType
from app.schemas import DocumentOut, DocumentItemOut, ReorderRequest, SectionOut, SectionReorderRequest
from app.storage import get_storage, StorageBackend, slugify

router = APIRouter(prefix="/api/projects/{project_id}/documents", tags=["documents"])


# ═══════════════════════════════════════════════════
# Category detection
# ═══════════════════════════════════════════════════

FILE_CATEGORIES = {
    "image":        [".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".bmp", ".ico"],
    "video":        [".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv", ".wmv"],
    "audio":        [".mp3", ".wav", ".ogg", ".flac", ".aac", ".wma"],
    "pdf":          [".pdf"],
    "word":         [".doc", ".docx", ".rtf"],
    "spreadsheet":  [".xls", ".xlsx", ".ods", ".csv"],
    "presentation": [".ppt", ".pptx", ".odp"],
    "archive":      [".zip", ".rar", ".7z", ".tar", ".gz", ".bz2"],
    "code":         [".py", ".js", ".ts", ".html", ".css", ".json", ".yaml", ".yml", ".sql", ".java", ".go", ".rs", ".cpp", ".c", ".h"],
    "text":         [".txt", ".md", ".log", ".ini", ".cfg"],
}

LINK_CATEGORIES = {
    "drive": ["drive.google.com"],
    "docs": ["docs.google.com/document"],
    "sheets": ["docs.google.com/spreadsheets", "sheets.google.com"],
    "slides": ["docs.google.com/presentation"],
    "youtube": ["youtube.com", "youtu.be"],
    "figma": ["figma.com"],
    "notion": ["notion.so"],
    "github": ["github.com"],
    "gitlab": ["gitlab.com"],
}


def detect_category(item_type: DocType, url: Optional[str], file_name: Optional[str], mime_type: Optional[str]) -> str:
    if item_type == DocType.note:
        return "note"
    if item_type == DocType.link:
        if not url:
            return "link"
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        path = parsed.path or ""
        full = f"{hostname}{path}".lower()
        for cat, patterns in LINK_CATEGORIES.items():
            for pat in patterns:
                if pat in full:
                    return cat
        return "link"

    # File
    if mime_type:
        main = mime_type.split("/")[0]
        mapping = {"image": "image", "video": "video", "audio": "audio"}
        if main in mapping:
            return mapping[main]
        if mime_type == "application/pdf":
            return "pdf"

    if file_name:
        ext = Path(file_name).suffix.lower()
        for cat, exts in FILE_CATEGORIES.items():
            if ext in exts:
                return cat

    return "file"


# ═══════════════════════════════════════════════════
# Documents (groups)
# ═══════════════════════════════════════════════════

@router.get("", response_model=list[DocumentOut])
async def list_documents(project_id: int, section_id: Optional[int] = None, db: AsyncSession = Depends(get_db)):
    query = select(Document).where(Document.project_id == project_id)
    if section_id is not None:
        query = query.where(Document.section_id == section_id)
    else:
        query = query.where(Document.section_id.is_(None))
    result = await db.execute(query.order_by(Document.sort_order.asc(), Document.created_at.desc()))
    return result.scalars().all()


@router.post("", response_model=DocumentOut, status_code=201)
async def create_document(
    project_id: int,
    title: str = Form(...),
    description: Optional[str] = Form(None),
    section_id: Optional[int] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    proj_result = await db.execute(select(Project).where(Project.id == project_id))
    if not proj_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Project not found")

    if section_id is not None:
        sec_result = await db.execute(select(Section).where(Section.id == section_id, Section.project_id == project_id))
        if not sec_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Section not found")

    max_order = await db.execute(
        select(Document.sort_order)
        .where(Document.project_id == project_id, Document.section_id == section_id)
        .order_by(Document.sort_order.desc())
        .limit(1)
    )
    max_val = max_order.scalar_one_or_none() or 0

    doc = Document(project_id=project_id, section_id=section_id, title=title, description=description, sort_order=max_val + 1)
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return doc


@router.patch("/{doc_id}", response_model=DocumentOut)
async def update_document(
    project_id: int,
    doc_id: int,
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    section_id: Optional[int] = Form(None),
    db: AsyncSession = Depends(get_db),
    storage: StorageBackend = Depends(get_storage),
):
    result = await db.execute(select(Document).where(Document.id == doc_id, Document.project_id == project_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    old_title = doc.title
    if title is not None:
        doc.title = title
    if description is not None:
        doc.description = description
    if section_id is not None:
        if section_id == -1:
            doc.section_id = None
        else:
            sec_result = await db.execute(select(Section).where(Section.id == section_id, Section.project_id == project_id))
            if not sec_result.scalar_one_or_none():
                raise HTTPException(status_code=404, detail="Section not found")
            doc.section_id = section_id
    await db.commit()
    await db.refresh(doc)

    # Rename folder if document title changed
    if title is not None and old_title != doc.title:
        proj_result = await db.execute(select(Project).where(Project.id == project_id))
        project = proj_result.scalar_one_or_none()
        if project:
            old_subfolder = f"{project.id}_{slugify(project.name)}/{doc.id}_{slugify(old_title)}"
            new_subfolder = f"{project.id}_{slugify(project.name)}/{doc.id}_{slugify(doc.title)}"
            await storage.rename_subfolder(old_subfolder, new_subfolder)

            # Update stored file paths
            old_prefix = f"{old_subfolder}/"
            new_prefix = f"{new_subfolder}/"
            items_result = await db.execute(
                select(DocumentItem).where(
                    DocumentItem.document_id == doc_id,
                    DocumentItem.item_type == DocType.file,
                    DocumentItem.file_path.isnot(None),
                )
            )
            for item in items_result.scalars().all():
                if item.file_path and item.file_path.startswith(old_prefix):
                    item.file_path = item.file_path.replace(old_prefix, new_prefix, 1)
            await db.commit()

    return doc


@router.delete("/{doc_id}", status_code=204)
async def delete_document(
    project_id: int,
    doc_id: int,
    db: AsyncSession = Depends(get_db),
    storage: StorageBackend = Depends(get_storage),
):
    result = await db.execute(select(Document).where(Document.id == doc_id, Document.project_id == project_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Delete associated files from storage
    for item in doc.items:
        if item.item_type == DocType.file and item.file_path:
            await storage.delete(item.file_path)

    await db.delete(doc)
    await db.commit()
    return None


@router.patch("/reorder", status_code=204)
async def reorder_documents(
    project_id: int,
    data: ReorderRequest,
    db: AsyncSession = Depends(get_db),
):
    for idx, doc_id in enumerate(data.document_ids):
        await db.execute(
            update(Document)
            .where(Document.id == doc_id, Document.project_id == project_id)
            .values(sort_order=idx)
        )
    await db.commit()
    return None


# ═══════════════════════════════════════════════════
# Document Items (links / files inside a group)
# ═══════════════════════════════════════════════════

@router.post("/{doc_id}/items", response_model=DocumentItemOut, status_code=201)
async def create_item(
    project_id: int,
    doc_id: int,
    title: Optional[str] = Form(None),
    item_type: str = Form(...),
    url: Optional[str] = Form(None),
    content: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    db: AsyncSession = Depends(get_db),
    storage: StorageBackend = Depends(get_storage),
):
    result = await db.execute(select(Document).where(Document.id == doc_id, Document.project_id == project_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    proj_result = await db.execute(select(Project).where(Project.id == project_id))
    project = proj_result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    item_type_enum = DocType(item_type)
    file_path = None
    file_name = None
    file_size = None
    mime_type = None
    final_url = url

    if item_type_enum == DocType.file:
        if not file:
            raise HTTPException(status_code=400, detail="File is required for item_type=file")
        file_name = file.filename
        mime_type = file.content_type
        file_content = await file.read()
        file_size = len(file_content)
        from io import BytesIO
        subfolder = f"{project.id}_{slugify(project.name)}/{doc.id}_{slugify(doc.title)}"
        meta = await storage.save(BytesIO(file_content), file.filename, file.content_type, subfolder=subfolder)
        file_path = meta["file_path"]
        if meta.get("url"):
            final_url = meta["url"]
    elif item_type_enum == DocType.note:
        if not content:
            raise HTTPException(status_code=400, detail="Content is required for item_type=note")
    else:
        if not url:
            raise HTTPException(status_code=400, detail="URL is required for item_type=link")

    category = detect_category(item_type_enum, final_url, file_name, mime_type)

    max_order = await db.execute(
        select(DocumentItem.sort_order)
        .where(DocumentItem.document_id == doc_id)
        .order_by(DocumentItem.sort_order.desc())
        .limit(1)
    )
    max_val = max_order.scalar_one_or_none() or 0

    item = DocumentItem(
        document_id=doc_id,
        title=title,
        item_type=item_type_enum,
        url=final_url,
        file_path=file_path,
        file_name=file_name,
        file_size=file_size,
        mime_type=mime_type,
        category=category,
        content=content,
        sort_order=max_val + 1,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)

    # Update document category if empty or auto
    if not doc.category:
        doc.category = category
        await db.commit()

    return item


@router.patch("/{doc_id}/items/{item_id}", response_model=DocumentItemOut)
async def update_item(
    project_id: int,
    doc_id: int,
    item_id: int,
    title: Optional[str] = Form(None),
    url: Optional[str] = Form(None),
    content: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    db: AsyncSession = Depends(get_db),
    storage: StorageBackend = Depends(get_storage),
):
    result = await db.execute(
        select(DocumentItem)
        .join(Document)
        .where(DocumentItem.id == item_id, DocumentItem.document_id == doc_id, Document.project_id == project_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    if title is not None:
        item.title = title

    if item.item_type == DocType.link:
        if url is not None:
            item.url = url
            item.category = detect_category(DocType.link, url, None, None)
    elif item.item_type == DocType.note:
        if content is not None:
            item.content = content
    else:
        if file:
            # Replace file: delete old, save new
            if item.file_path:
                await storage.delete(item.file_path)
            file_name = file.filename
            mime_type = file.content_type
            file_content = await file.read()
            file_size = len(file_content)
            from io import BytesIO
            proj_result = await db.execute(select(Project).where(Project.id == project_id))
            project = proj_result.scalar_one_or_none()
            doc_result = await db.execute(select(Document).where(Document.id == doc_id, Document.project_id == project_id))
            doc_obj = doc_result.scalar_one_or_none()
            subfolder = f"{project.id}_{slugify(project.name)}/{doc_obj.id}_{slugify(doc_obj.title)}" if project and doc_obj else f"{project_id}/{doc_id}"
            meta = await storage.save(BytesIO(file_content), file.filename, file.content_type, subfolder=subfolder)
            item.file_path = meta["file_path"]
            item.file_name = file_name
            item.file_size = file_size
            item.mime_type = mime_type
            item.category = detect_category(DocType.file, None, file_name, mime_type)
            if meta.get("url"):
                item.url = meta["url"]

    await db.commit()
    await db.refresh(item)
    return item


@router.delete("/{doc_id}/items/{item_id}", status_code=204)
async def delete_item(
    project_id: int,
    doc_id: int,
    item_id: int,
    db: AsyncSession = Depends(get_db),
    storage: StorageBackend = Depends(get_storage),
):
    result = await db.execute(
        select(DocumentItem)
        .join(Document)
        .where(DocumentItem.id == item_id, DocumentItem.document_id == doc_id, Document.project_id == project_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    if item.item_type == DocType.file and item.file_path:
        await storage.delete(item.file_path)

    await db.delete(item)
    await db.commit()
    return None


@router.get("/{doc_id}/items/{item_id}/download")
async def download_item(
    project_id: int,
    doc_id: int,
    item_id: int,
    db: AsyncSession = Depends(get_db),
    storage: StorageBackend = Depends(get_storage),
):
    result = await db.execute(
        select(DocumentItem)
        .join(Document)
        .where(DocumentItem.id == item_id, DocumentItem.document_id == doc_id, Document.project_id == project_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    if item.item_type == DocType.link:
        raise HTTPException(status_code=400, detail="Cannot download a link item")

    if not item.file_path:
        raise HTTPException(status_code=404, detail="File not found")

    local_path = await storage.get_local_path(item.file_path)
    if local_path and os.path.exists(local_path):
        return FileResponse(
            local_path,
            filename=item.file_name or os.path.basename(local_path),
            media_type=item.mime_type or "application/octet-stream",
        )

    download_url = storage.get_download_url(item.file_path, filename=item.file_name)
    if download_url:
        return RedirectResponse(url=download_url)

    public_url = storage.get_public_url(item.file_path)
    if public_url:
        return RedirectResponse(url=public_url)

    raise HTTPException(status_code=404, detail="File not available")


@router.post("/{doc_id}/items/{item_id}/open")
async def open_item(
    request: Request,
    project_id: int,
    doc_id: int,
    item_id: int,
    db: AsyncSession = Depends(get_db),
    storage: StorageBackend = Depends(get_storage),
):
    result = await db.execute(
        select(DocumentItem)
        .join(Document)
        .where(DocumentItem.id == item_id, DocumentItem.document_id == doc_id, Document.project_id == project_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    if item.item_type == DocType.link:
        raise HTTPException(status_code=400, detail="Cannot open a link item")

    if not item.file_path:
        raise HTTPException(status_code=404, detail="File not found")

    client_host = request.client.host if request.client else None
    if client_host not in ("127.0.0.1", "::1", "localhost"):
        raise HTTPException(status_code=403, detail="Remote open not allowed")

    local_path = await storage.get_local_path(item.file_path)
    if not local_path or not os.path.exists(local_path):
        raise HTTPException(status_code=404, detail="File not found")

    system = platform.system()
    try:
        if system == "Windows":
            os.startfile(local_path)
        elif system == "Darwin":
            subprocess.Popen(["open", local_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.Popen(["xdg-open", local_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to open file: {str(e)}")

    return {"status": "opened", "path": local_path}


# ═══════════════════════════════════════════════════
# Sections
# ═══════════════════════════════════════════════════

# Separate router for sections
section_router = APIRouter(prefix="/api/projects/{project_id}/sections", tags=["sections"])

@section_router.get("", response_model=list[SectionOut])
async def list_sections(project_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Section).where(Section.project_id == project_id).order_by(Section.sort_order.asc(), Section.created_at.desc())
    )
    return result.scalars().all()


@section_router.post("", response_model=SectionOut, status_code=201)
async def create_section(
    project_id: int,
    name: str = Form(...),
    description: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    proj_result = await db.execute(select(Project).where(Project.id == project_id))
    if not proj_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Project not found")

    max_order = await db.execute(
        select(Section.sort_order)
        .where(Section.project_id == project_id)
        .order_by(Section.sort_order.desc())
        .limit(1)
    )
    max_val = max_order.scalar_one_or_none() or 0

    section = Section(project_id=project_id, name=name, description=description, sort_order=max_val + 1)
    db.add(section)
    await db.commit()
    await db.refresh(section)
    return section


@section_router.patch("/reorder", status_code=204)
async def reorder_sections(
    project_id: int,
    data: SectionReorderRequest,
    db: AsyncSession = Depends(get_db),
):
    for idx, sec_id in enumerate(data.section_ids):
        await db.execute(
            update(Section)
            .where(Section.id == sec_id, Section.project_id == project_id)
            .values(sort_order=idx)
        )
    await db.commit()
    return None


@section_router.patch("/{sec_id}", response_model=SectionOut)
async def update_section(
    project_id: int,
    sec_id: int,
    name: str = Form(None),
    description: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Section).where(Section.id == sec_id, Section.project_id == project_id))
    section = result.scalar_one_or_none()
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")
    if name is not None:
        section.name = name
    if description is not None:
        section.description = description
    await db.commit()
    await db.refresh(section)
    return section


@section_router.delete("/{sec_id}", status_code=204)
async def delete_section(
    project_id: int,
    sec_id: int,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Section).where(Section.id == sec_id, Section.project_id == project_id))
    section = result.scalar_one_or_none()
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")

    # Clear section_id from documents in this section
    for doc in section.documents:
        doc.section_id = None
    await db.commit()

    await db.delete(section)
    await db.commit()
    return None


@router.get("/{doc_id}/items/{item_id}/preview")
async def preview_item(
    project_id: int,
    doc_id: int,
    item_id: int,
    db: AsyncSession = Depends(get_db),
    storage: StorageBackend = Depends(get_storage),
):
    result = await db.execute(
        select(DocumentItem)
        .join(Document)
        .where(DocumentItem.id == item_id, DocumentItem.document_id == doc_id, Document.project_id == project_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    if item.item_type == DocType.link:
        return {"type": "link", "url": item.url}

    if not item.file_path:
        raise HTTPException(status_code=404, detail="File not found")

    local_path = await storage.get_local_path(item.file_path)
    if local_path and os.path.exists(local_path):
        return FileResponse(
            local_path,
            media_type=item.mime_type or "application/octet-stream",
        )

    preview_url = storage.get_preview_url(item.file_path)
    if preview_url:
        return RedirectResponse(url=preview_url)

    public_url = storage.get_public_url(item.file_path)
    if public_url:
        return RedirectResponse(url=public_url)

    raise HTTPException(status_code=404, detail="File not available")
