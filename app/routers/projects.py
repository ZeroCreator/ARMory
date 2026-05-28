from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import List

from app.database import get_db
from app.models import Project, Document, DocumentItem, DocType
from app.schemas import ProjectCreate, ProjectUpdate, ProjectOut, ProjectDetailOut, ProjectReorderRequest
from app.storage import get_storage, StorageBackend, slugify

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("", response_model=List[ProjectOut])
async def list_projects(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Project)
        .options(selectinload(Project.documents), selectinload(Project.sections))
        .order_by(Project.sort_order, Project.updated_at.desc())
    )
    return result.scalars().all()


@router.post("", response_model=ProjectOut, status_code=201)
async def create_project(data: ProjectCreate, db: AsyncSession = Depends(get_db)):
    project = Project(**data.model_dump())
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


@router.patch("/reorder", status_code=204)
async def reorder_projects(data: ProjectReorderRequest, db: AsyncSession = Depends(get_db)):
    for idx, project_id in enumerate(data.project_ids):
        result = await db.execute(select(Project).where(Project.id == project_id))
        project = result.scalar_one_or_none()
        if project:
            project.sort_order = idx
    await db.commit()
    return None


@router.get("/{project_id}", response_model=ProjectDetailOut)
async def get_project(project_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Project)
        .where(Project.id == project_id)
        .options(selectinload(Project.documents), selectinload(Project.sections))
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.patch("/{project_id}", response_model=ProjectOut)
async def update_project(
    project_id: int,
    data: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
    storage: StorageBackend = Depends(get_storage),
):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    old_name = project.name
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    await db.commit()
    await db.refresh(project)

    # Rename project folder if name changed
    if old_name != project.name:
        old_subfolder = f"{project.id}_{slugify(old_name)}"
        new_subfolder = f"{project.id}_{slugify(project.name)}"
        await storage.rename_subfolder(old_subfolder, new_subfolder)

        # Update stored file paths for all items in this project
        old_prefix = f"{old_subfolder}/"
        new_prefix = f"{new_subfolder}/"
        items_result = await db.execute(
            select(DocumentItem)
            .join(Document)
            .where(
                Document.project_id == project_id,
                DocumentItem.item_type == DocType.file,
                DocumentItem.file_path.isnot(None),
            )
        )
        for item in items_result.scalars().all():
            if item.file_path and item.file_path.startswith(old_prefix):
                item.file_path = item.file_path.replace(old_prefix, new_prefix, 1)
        await db.commit()

    return project


@router.delete("/{project_id}", status_code=204)
async def delete_project(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    storage: StorageBackend = Depends(get_storage),
):
    # Delete files from storage first
    result = await db.execute(
        select(DocumentItem)
        .join(Document)
        .where(Document.project_id == project_id, DocumentItem.item_type == DocType.file)
    )
    items = result.scalars().all()
    for item in items:
        if item.file_path:
            await storage.delete(item.file_path)

    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    await db.delete(project)
    await db.commit()
    return None
