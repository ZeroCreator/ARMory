import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from shlex import quote
from dotenv import load_dotenv
from fastapi import APIRouter
from pydantic import BaseModel

# Загружаем .env из корня проекта
BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")

router = APIRouter(prefix="/api/scheduler", tags=["scheduler"])

SCRIPTS_DIR = BASE_DIR / "scripts"

# ── Загрузка тасок из .env ──
def _load_tasks():
    raw = os.environ.get("SCHEDULER_TASKS", "")
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return {k: {"name": v.get("name", k), "script": v["script"]} for k, v in data.items()}
    except Exception:
        return {}

TASKS = _load_tasks()


class ScheduleRequest(BaseModel):
    project: str
    datetime: str


class RemoveTaskRequest(BaseModel):
    task_id: str


def run_command(command):
    try:
        result = subprocess.run(
            command,
            shell=True,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        return result.stdout, None
    except subprocess.CalledProcessError as e:
        return None, f"Error: {e.stderr}"


@router.get("/tasks")
def list_tasks():
    if not TASKS:
        return {"error": "SCHEDULER_TASKS не задан в .env"}
    return {
        "tasks": [
            {"key": k, "name": v["name"]}
            for k, v in TASKS.items()
        ]
    }


@router.post("/schedule")
def schedule_task(data: ScheduleRequest):
    task_key = data.project.lower()
    task = TASKS.get(task_key)
    if not task:
        return {"error": f"Таск '{data.project}' не найден"}
    if not data.datetime:
        return {"error": "Missing datetime"}
    try:
        dt = datetime.fromisoformat(data.datetime)
        at_time = dt.strftime("%H:%M %Y-%m-%d")
        script_path = SCRIPTS_DIR / task["script"]
        if not script_path.exists():
            return {"error": f"Скрипт не найден: {script_path}"}
        cmd = f"echo {quote(str(script_path))} | at {at_time}"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode != 0:
            raise Exception(result.stderr)
        return {"message": "Задача добавлена!", "output": result.stdout}
    except Exception as e:
        return {"error": str(e)}


@router.get("/atq")
def get_queue():
    try:
        output, error = run_command("atq")
        if error:
            return {"error": error}
        return {"output": output}
    except Exception as e:
        return {"error": str(e)}


@router.post("/remove-task")
def remove_task(data: RemoveTaskRequest):
    if not data.task_id:
        return {"error": "Task ID is required"}
    try:
        output, error = run_command(f"atrm {data.task_id}")
        if error:
            return {"error": error}
        return {"message": f"Задача {data.task_id} удалена!", "output": output}
    except Exception as e:
        return {"error": str(e)}
