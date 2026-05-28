from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from typing import Optional

from app.database import get_db
from app.models import Section, Project, Document
from app.schemas import SectionOut, SectionReorderRequest

router = APIRouter(prefix="/api/projects/{project_id}/sections", tags=["sections"])


@router.get("", response_model=list[SectionOut])
async def list_sections(project_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Section)
        .where(Section.project_id == project_id)
        .order_by(Section.sort_order.asc(), Section.created_at.desc())
    )
    return result.scalars().all()


@router.post("", response_model=SectionOut, status_code=201)
async def create_section(
    project_id: int,
    name: str = Form(...),
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

    section = Section(project_id=project_id, name=name, sort_order=max_val + 1)
    db.add(section)
    await db.commit()
    await db.refresh(section)
    return section


@router.patch("/{section_id}", response_model=SectionOut)
async def update_section(
    project_id: int,
    section_id: int,
    name: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Section).where(Section.id == section_id, Section.project_id == project_id))
    section = result.scalar_one_or_none()
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")
    if name is not None:
        section.name = name
    await db.commit()
    await db.refresh(section)
    return section


@router.delete("/{section_id}", status_code=204)
async def delete_section(
    project_id: int,
    section_id: int,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Section).where(Section.id == section_id, Section.project_id == project_id))
    section = result.scalar_one_or_none()
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")

    # Move documents out of this section before deleting
    await db.execute(
        update(Document)
        .where(Document.section_id == section_id, Document.project_id == project_id)
        .values(section_id=None)
    )

    await db.delete(section)
    await db.commit()
    return None


@router.patch("/reorder", status_code=204)
async def reorder_sections(
    project_id: int,
    data: SectionReorderRequest,
    db: AsyncSession = Depends(get_db),
):
    for idx, section_id in enumerate(data.section_ids):
        await db.execute(
            update(Section)
            .where(Section.id == section_id, Section.project_id == project_id)
            .values(sort_order=idx)
        )
    await db.commit()
    return None
