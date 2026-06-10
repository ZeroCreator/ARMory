from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import List

from app.database import get_db
from app.models import SidebarBlock, SidebarLink
from app.schemas import (
    SidebarBlockOut, SidebarBlockCreate, SidebarBlockUpdate, SidebarBlockReorderRequest,
    SidebarLinkOut, SidebarLinkCreate, SidebarLinkUpdate, SidebarLinkReorderRequest,
)

router = APIRouter(prefix="/api/sidebar", tags=["sidebar"])


# ── Блоки ──

@router.get("/blocks", response_model=List[SidebarBlockOut])
async def list_blocks(position: str = None, db: AsyncSession = Depends(get_db)):
    stmt = select(SidebarBlock).options(selectinload(SidebarBlock.links))
    if position in ("left", "right"):
        stmt = stmt.where(SidebarBlock.position == position)
    stmt = stmt.order_by(SidebarBlock.sort_order, SidebarBlock.created_at)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("/blocks", response_model=SidebarBlockOut, status_code=201)
async def create_block(data: SidebarBlockCreate, db: AsyncSession = Depends(get_db)):
    if data.position not in ("left", "right"):
        raise HTTPException(status_code=400, detail="position must be 'left' or 'right'")
    block = SidebarBlock(**data.model_dump())
    db.add(block)
    await db.commit()
    await db.refresh(block)
    return block


@router.patch("/blocks/reorder", status_code=204)
async def reorder_blocks(data: SidebarBlockReorderRequest, db: AsyncSession = Depends(get_db)):
    for idx, block_id in enumerate(data.block_ids):
        result = await db.execute(select(SidebarBlock).where(SidebarBlock.id == block_id))
        block = result.scalar_one_or_none()
        if block:
            block.sort_order = idx
    await db.commit()
    return None


@router.patch("/blocks/{block_id}", response_model=SidebarBlockOut)
async def update_block(block_id: int, data: SidebarBlockUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SidebarBlock).where(SidebarBlock.id == block_id))
    block = result.scalar_one_or_none()
    if not block:
        raise HTTPException(status_code=404, detail="Block not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(block, field, value)
    await db.commit()
    await db.refresh(block)
    return block


@router.delete("/blocks/{block_id}", status_code=204)
async def delete_block(block_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SidebarBlock).where(SidebarBlock.id == block_id))
    block = result.scalar_one_or_none()
    if not block:
        raise HTTPException(status_code=404, detail="Block not found")
    await db.delete(block)
    await db.commit()
    return None


# ── Ссылки ──

@router.patch("/blocks/{block_id}/links/reorder", status_code=204)
async def reorder_links(block_id: int, data: SidebarLinkReorderRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SidebarBlock).where(SidebarBlock.id == block_id))
    block = result.scalar_one_or_none()
    if not block:
        raise HTTPException(status_code=404, detail="Block not found")
    for idx, link_id in enumerate(data.link_ids):
        result = await db.execute(select(SidebarLink).where(SidebarLink.id == link_id, SidebarLink.block_id == block_id))
        link = result.scalar_one_or_none()
        if link:
            link.sort_order = idx
    await db.commit()
    return None


@router.post("/blocks/{block_id}/links", response_model=SidebarLinkOut, status_code=201)
async def create_link(block_id: int, data: SidebarLinkCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SidebarBlock).where(SidebarBlock.id == block_id))
    block = result.scalar_one_or_none()
    if not block:
        raise HTTPException(status_code=404, detail="Block not found")
    link = SidebarLink(block_id=block_id, **data.model_dump())
    db.add(link)
    await db.commit()
    await db.refresh(link)
    return link


@router.patch("/links/{link_id}", response_model=SidebarLinkOut)
async def update_link(link_id: int, data: SidebarLinkUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SidebarLink).where(SidebarLink.id == link_id))
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(link, field, value)
    await db.commit()
    await db.refresh(link)
    return link


@router.delete("/links/{link_id}", status_code=204)
async def delete_link(link_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SidebarLink).where(SidebarLink.id == link_id))
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    await db.delete(link)
    await db.commit()
    return None
