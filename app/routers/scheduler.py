import os
import subprocess
from datetime import datetime
from shlex import quote
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/scheduler", tags=["scheduler"])


dogma_cmd = os.getenv("DOGMA_SCRIPT_PATH")
trendagent_cmd = os.getenv("TRENDAGENT_SCRIPT_PATH")

PROJECT_COMMANDS = {
    "dogma": dogma_cmd,
    "trendagent": trendagent_cmd,
}


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


@router.post("/schedule")
def schedule_task(data: ScheduleRequest):
    project_key = data.project.lower()
    cmd_path = PROJECT_COMMANDS.get(project_key)
    if not cmd_path:
        return {"error": f"Команда для проекта '{data.project}' не настроена в .env"}
    if not data.datetime:
        return {"error": "Missing datetime"}
    try:
        dt = datetime.fromisoformat(data.datetime)
        at_time = dt.strftime("%H:%M %Y-%m-%d")
        safe_command = quote(cmd_path)
        cmd = f"echo {safe_command} | at {at_time}"
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
