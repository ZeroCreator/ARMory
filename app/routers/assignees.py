from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models import Assignee
from app.schemas import AssigneeCreate, AssigneeOut

router = APIRouter(prefix="/api/assignees", tags=["assignees"])


@router.get("", response_model=List[AssigneeOut])
async def list_assignees(db: AsyncSession = Depends(get_db)):
    """Список всех ответственных."""
    result = await db.execute(select(Assignee).order_by(Assignee.name.asc()))
    return result.scalars().all()


@router.post("", response_model=AssigneeOut, status_code=201)
async def create_assignee(data: AssigneeCreate, db: AsyncSession = Depends(get_db)):
    """Добавить нового ответственного."""
    existing = await db.execute(select(Assignee).where(Assignee.email == data.email))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail="Ответственный с таким email уже существует",
        )

    assignee = Assignee(**data.model_dump())
    db.add(assignee)
    await db.commit()
    await db.refresh(assignee)
    return assignee


@router.post("/mcp-agent", response_model=AssigneeOut)
async def get_or_create_mcp_agent_assignee(db: AsyncSession = Depends(get_db)):
    """Ensure the configured MCP agent is available in task assignee pickers."""
    settings = get_settings()
    result = await db.execute(
        select(Assignee).where(Assignee.email == settings.ai_assignee_email)
    )
    assignee = result.scalar_one_or_none()
    if assignee:
        return assignee

    assignee = Assignee(
        name=settings.ai_assignee_name,
        email=settings.ai_assignee_email,
    )
    db.add(assignee)
    await db.commit()
    await db.refresh(assignee)
    return assignee
