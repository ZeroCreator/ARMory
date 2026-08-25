import asyncio
import json
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse

from app.extensions import install_manifest, list_extensions, set_enabled
from app.extension_deployer import get_job, start_deployment


router = APIRouter(tags=["extensions"])


@router.post("/api/extensions/connect", status_code=201)
async def connect_extension(payload: dict):
    manifest = {
        "id": payload.get("id"),
        "name": payload.get("name"),
        "url": payload.get("url"),
        "health_url": payload.get("health_url"),
        "icon": payload.get("icon", "bi-box"),
        "description": payload.get("description", ""),
        "enabled": True,
    }
    logs = ["Проверка параметров подключения…"]
    try:
        health_url = str(manifest.get("health_url") or "").strip()
        if health_url:
            parsed = urlparse(health_url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError("Health URL должен быть абсолютным HTTP(S)-адресом")
            logs.append(f"$ GET {health_url}")
            async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
                response = await client.get(health_url)
            logs.append(f"HTTP {response.status_code}")
            if response.status_code >= 500:
                raise ValueError(f"Health-check вернул HTTP {response.status_code}")
        extension = install_manifest(manifest)
        logs.append("Приложение подключено и добавлено в меню.")
        return {"extension": extension, "logs": logs}
    except (ValueError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/api/extensions/deploy", status_code=202)
async def deploy_extension(payload: dict):
    try:
        return {"job_id": start_deployment(payload)}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/api/extensions/jobs/{job_id}/events")
async def deployment_events(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Операция не найдена")

    async def stream():
        position = 0
        while True:
            while position < len(job["logs"]):
                yield f"data: {json.dumps({'message': job['logs'][position]}, ensure_ascii=False)}\n\n"
                position += 1
            if job["status"] in {"complete", "failed"}:
                yield f"event: done\ndata: {json.dumps({'status': job['status']})}\n\n"
                return
            job["event"].clear()
            try:
                await asyncio.wait_for(job["event"].wait(), timeout=15)
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.get("/applications", response_class=HTMLResponse)
async def applications_page(request: Request):
    return request.app.state.templates.TemplateResponse(
        "applications.html",
        {"request": request, "title": request.app.title, "extensions": list_extensions()},
    )


@router.get("/api/extensions")
async def get_extensions():
    return list_extensions()


@router.patch("/api/extensions/{extension_id}")
async def update_extension(extension_id: str, payload: dict):
    if "enabled" not in payload or not isinstance(payload["enabled"], bool):
        raise HTTPException(status_code=422, detail="Поле enabled должно быть логическим")
    try:
        return set_enabled(extension_id, payload["enabled"])
    except KeyError:
        raise HTTPException(status_code=404, detail="Приложение не найдено") from None


@router.post("/api/extensions/install", status_code=201)
async def upload_extension_manifest(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".json"):
        raise HTTPException(status_code=400, detail="Загрузите JSON-манифест")
    content = await file.read(64 * 1024 + 1)
    if len(content) > 64 * 1024:
        raise HTTPException(status_code=413, detail="Манифест не должен превышать 64 КБ")
    try:
        manifest = json.loads(content)
        if not isinstance(manifest, dict):
            raise ValueError("Корень манифеста должен быть объектом")
        return install_manifest(manifest)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
