from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.events import broadcast
from app.models import Assignee, Project, ProjectComment, ProjectCommentRead
from app.schemas import ProjectCommentCreate, ProjectCommentOut, ProjectCommentUpdate

router = APIRouter(prefix="/api/projects/{project_id}/comments", tags=["comments"])


_AUTH_HEADERS = [
    "X-Forwarded-Email",
    "X-Forwarded-User",
    "X-Forwarded-Preferred-Username",
    "X-Forwarded-Access-Token",
    "Remote-User",
    "Remote-Email",
]


def _get_current_email(request: Request) -> Optional[str]:
    for h in _AUTH_HEADERS:
        value = request.headers.get(h)
        if value:
            return value.strip()
    # Если OAuth-заголовков нет, использовать локального пользователя
    return "local.user"


async def _resolve_author_name(email: str, db: AsyncSession) -> str:
    result = await db.execute(select(Assignee).where(Assignee.email == email))
    assignee = result.scalar_one_or_none()
    return assignee.name if assignee else email


def _comment_out(comment: ProjectComment, author_name: str) -> ProjectCommentOut:
    return ProjectCommentOut(
        id=comment.id,
        project_id=comment.project_id,
        author_email=comment.author_email,
        author_name=author_name,
        content=comment.content,
        created_at=comment.created_at,
        updated_at=comment.updated_at,
        is_edited=(comment.updated_at - comment.created_at).total_seconds() > 1 if comment.updated_at and comment.created_at else False,
    )


@router.get("", response_model=List[ProjectCommentOut])
async def list_comments(project_id: int, db: AsyncSession = Depends(get_db)):
    project_result = await db.execute(select(Project).where(Project.id == project_id))
    if not project_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Project not found")

    result = await db.execute(
        select(ProjectComment)
        .where(ProjectComment.project_id == project_id)
        .order_by(ProjectComment.created_at.asc())
    )
    comments = result.scalars().all()

    # Подгрузить имена исполнителей одним запросом
    emails = {c.author_email for c in comments}
    names = {}
    if emails:
        assignees_result = await db.execute(select(Assignee).where(Assignee.email.in_(emails)))
        names = {a.email: a.name for a in assignees_result.scalars().all()}

    return [_comment_out(c, names.get(c.author_email, c.author_email)) for c in comments]


@router.post("", response_model=ProjectCommentOut, status_code=201)
async def create_comment(
    project_id: int,
    data: ProjectCommentCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    project_result = await db.execute(select(Project).where(Project.id == project_id))
    if not project_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Project not found")

    author_email = _get_current_email(request)
    if not author_email:
        raise HTTPException(status_code=401, detail="User not authenticated")

    content = data.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Comment content is required")

    comment = ProjectComment(
        project_id=project_id,
        author_email=author_email,
        content=content,
    )
    db.add(comment)
    await db.commit()
    await db.refresh(comment)
    broadcast({"event": "unread", "type": "comments_changed", "project_id": project_id})

    author_name = await _resolve_author_name(author_email, db)
    return _comment_out(comment, author_name)


@router.delete("/{comment_id}", status_code=204)
async def delete_comment(
    project_id: int,
    comment_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ProjectComment).where(
            ProjectComment.id == comment_id,
            ProjectComment.project_id == project_id,
        )
    )
    comment = result.scalar_one_or_none()
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")

    user_email = _get_current_email(request)
    if comment.author_email != user_email:
        raise HTTPException(status_code=403, detail="Not authorized to delete this comment")

    await db.delete(comment)
    await db.commit()
    broadcast({"event": "unread", "type": "comments_changed", "project_id": project_id})
    return None


@router.put("/{comment_id}", response_model=ProjectCommentOut)
async def update_comment(
    project_id: int,
    comment_id: int,
    data: ProjectCommentUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ProjectComment).where(
            ProjectComment.id == comment_id,
            ProjectComment.project_id == project_id,
        )
    )
    comment = result.scalar_one_or_none()
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")

    user_email = _get_current_email(request)
    if comment.author_email != user_email:
        raise HTTPException(status_code=403, detail="Not authorized to edit this comment")

    content = data.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Comment content is required")

    comment.content = content
    comment.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(comment)
    broadcast({"event": "unread", "type": "comments_changed", "project_id": project_id})

    author_name = await _resolve_author_name(comment.author_email, db)
    return _comment_out(comment, author_name)


@router.post("/read", status_code=204)
async def mark_comments_read(
    project_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    project_result = await db.execute(select(Project).where(Project.id == project_id))
    if not project_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Project not found")

    user_email = _get_current_email(request)
    if not user_email:
        raise HTTPException(status_code=401, detail="User not authenticated")

    result = await db.execute(
        select(ProjectCommentRead).where(
            ProjectCommentRead.project_id == project_id,
            ProjectCommentRead.user_email == user_email,
        )
    )
    read_state = result.scalar_one_or_none()
    now = datetime.utcnow()
    if read_state:
        read_state.last_read_at = now
    else:
        read_state = ProjectCommentRead(
            project_id=project_id,
            user_email=user_email,
            last_read_at=now,
        )
        db.add(read_state)
    await db.commit()
    broadcast({"event": "unread", "project_id": project_id})
    return None
