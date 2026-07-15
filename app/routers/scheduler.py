import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from shlex import quote
from typing import List
from dotenv import load_dotenv, dotenv_values
from fastapi import APIRouter
from pydantic import BaseModel

# Загружаем .env из корня проекта
BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")

router = APIRouter(prefix="/api/scheduler", tags=["scheduler"])


# ── Загрузка тасков из .env проектов ──
def _load_tasks():
    paths_str = os.environ.get("SCRIPTS_PROJECT_PATHS", "")
    paths = [p.strip() for p in paths_str.split(",") if p.strip()]

    all_tasks = {}
    for path in paths:
        expanded = os.path.expanduser(path)
        path_obj = Path(expanded)
        if not path_obj.is_dir():
            continue
        project_name = path_obj.name
        env_file = path_obj / ".env"
        if env_file.exists():
            env_data = dotenv_values(env_file)
            raw = env_data.get("SCHEDULER_TASKS", "")
            if raw:
                try:
                    data = json.loads(raw)
                    for k, v in data.items():
                        full_key = f"{project_name.lower()}:{k}"
                        all_tasks[full_key] = {
                            "name": v.get("name", k),
                            "script": v["script"],
                            "project_dir": str(path_obj),
                        }
                except Exception:
                    continue

    return all_tasks


TASKS = _load_tasks()


class ScheduleRequest(BaseModel):
    project: str
    datetime: str
    args: List[str] = []


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
        return {"error": "SCHEDULER_TASKS не задан ни в одном из проектов"}
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
        script_path = Path(task["project_dir"]) / task["script"]
        if not script_path.exists():
            return {"error": f"Скрипт не найден: {script_path}"}
        args = " ".join(quote(a) for a in (data.args or []))
        cmd = f"cd {quote(str(task['project_dir']))} && {quote(str(script_path))}{' ' + args if args else ''} | at {at_time}"
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
