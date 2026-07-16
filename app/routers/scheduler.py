import io
import json
import os
import shutil
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

SSH_TIMEOUT = 10  # секунд на одну ssh-операцию
LOCAL_LABEL = "local"  # метка локальной очереди в выводе atq


# ── SSH ──
def _ssh_map() -> dict:
    """Проект → ssh-target (user@host) из SCRIPTS_PROJECT_SSH.

    Проекты без записи выполняются локально (режим разработки).
    """
    mapping = {}
    for pair in os.environ.get("SCRIPTS_PROJECT_SSH", "").split(","):
        pair = pair.strip()
        if "=" in pair:
            project, target = pair.split("=", 1)
            if project.strip() and target.strip():
                mapping[project.strip().lower()] = target.strip()
    return mapping


def _prepare_ssh_key() -> str | None:
    """Вернуть путь к приватному ключу с корректными правами.

    Ключ монтируется в контейнер read-only, а ssh требует права 0600,
    поэтому копируем его во временный файл внутри контейнера.
    """
    src = os.environ.get("SCHEDULER_SSH_KEY", "")
    if not src or not os.path.isfile(src):
        return None
    dst = "/tmp/.scheduler_ssh_key"
    try:
        if not os.path.exists(dst) or os.path.getmtime(dst) < os.path.getmtime(src):
            shutil.copyfile(src, dst)
            os.chmod(dst, 0o600)
    except OSError:
        return None
    return dst


def _run_ssh(target: str, remote_cmd: list, stdin: str | None = None) -> subprocess.CompletedProcess:
    argv = [
        "ssh",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=10",
        "-o", "StrictHostKeyChecking=accept-new",
    ]
    key = _prepare_ssh_key()
    if key:
        argv += ["-i", key, "-o", "IdentitiesOnly=yes"]
    argv.append(target)
    argv += remote_cmd
    return subprocess.run(
        argv, input=stdin, capture_output=True, text=True, timeout=SSH_TIMEOUT
    )


def _remote_path(path: str) -> str:
    """Путь на удалённом сервере.

    Если путь начинается с ~, не экранируем его — пусть remote shell
    сама развернёт домашний каталог пользователя. Остальные пути
    экранируем через shlex.quote.
    """
    if path.startswith("~"):
        return path
    return quote(path)


# ── Загрузка тасков из .env проектов ──
def _read_project_env(project_dir_raw: str, target: str | None) -> dict:
    """Прочитать .env проекта — локально или по ssh."""
    if target is None:
        env_file = Path(os.path.expanduser(project_dir_raw)) / ".env"
        if not env_file.exists():
            return {}
        return dotenv_values(env_file)
    try:
        result = _run_ssh(target, ["cat", _remote_path(f"{project_dir_raw}/.env")])
    except (subprocess.TimeoutExpired, OSError):
        return {}
    if result.returncode != 0:
        return {}
    return dotenv_values(stream=io.StringIO(result.stdout))


def _load_tasks():
    paths_str = os.environ.get("SCRIPTS_PROJECT_PATHS", "")
    paths = [p.strip() for p in paths_str.split(",") if p.strip()]
    ssh_map = _ssh_map()

    all_tasks = {}
    for project_dir_raw in paths:
        project_name = Path(project_dir_raw).name
        target = ssh_map.get(project_name.lower())
        # Локальный проект без каталога пропускаем; у удалённого каталог не проверяем
        if target is None:
            expanded = Path(os.path.expanduser(project_dir_raw))
            if not expanded.is_dir():
                continue
        env_data = _read_project_env(project_dir_raw, target)
        raw = env_data.get("SCHEDULER_TASKS", "")
        if raw:
            try:
                data = json.loads(raw)
                for k, v in data.items():
                    full_key = f"{project_name.lower()}:{k}"
                    all_tasks[full_key] = {
                        "name": v.get("name", k),
                        "script": v["script"],
                        "project_dir": project_dir_raw,
                        "target": target,
                    }
            except Exception:
                continue

    return all_tasks


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
    tasks = _load_tasks()
    if not tasks:
        return {"error": "SCHEDULER_TASKS не задан ни в одном из проектов"}
    return {
        "tasks": [
            {"key": k, "name": v["name"]}
            for k, v in tasks.items()
        ]
    }


@router.post("/schedule")
def schedule_task(data: ScheduleRequest):
    task_key = data.project.lower()
    task = _load_tasks().get(task_key)
    if not task:
        return {"error": f"Таск '{data.project}' не найден"}
    if not data.datetime:
        return {"error": "Missing datetime"}
    try:
        dt = datetime.fromisoformat(data.datetime)
        project_dir_raw = task["project_dir"]
        script_rel = task["script"]
        args = " ".join(quote(a) for a in (data.args or []))
        target = task["target"]
        if target is None:
            project_dir = Path(os.path.expanduser(project_dir_raw))
            script_path = project_dir / script_rel
            if not script_path.exists():
                return {"error": f"Скрипт не найден: {script_path}"}
            job_cmd = f"cd {quote(str(project_dir))} && {quote(str(script_path))}{' ' + args if args else ''}"
            at_time = dt.strftime("%H:%M %Y-%m-%d")
            result = subprocess.run(
                f"{job_cmd} | at {at_time}", shell=True, capture_output=True, text=True
            )
        else:
            script_remote = _remote_path(f"{project_dir_raw}/{script_rel}")
            check = _run_ssh(target, ["test", "-f", script_remote])
            if check.returncode != 0:
                return {"error": f"Скрипт не найден на {target}: {project_dir_raw}/{script_rel}"}
            job_cmd = f"cd {_remote_path(project_dir_raw)} && {script_remote}{' ' + args if args else ''}"
            # Время трактуется в локальной таймзоне целевого сервера
            result = _run_ssh(
                target,
                ["at", dt.strftime("%H:%M"), dt.strftime("%Y-%m-%d")],
                stdin=job_cmd + "\n",
            )
        if result.returncode != 0:
            raise Exception(result.stderr.strip() or "unknown error")
        return {"message": "Задача добавлена!", "output": result.stdout}
    except subprocess.TimeoutExpired:
        return {"error": f"SSH: таймаут подключения ({SSH_TIMEOUT} c)"}
    except Exception as e:
        return {"error": str(e)}


def _project_targets() -> list:
    """Цели очередей (None = локально) по конфигурации проектов, без дублей.

    Источники очереди определяются конфигом, а не успешной загрузкой тасков,
    чтобы при недоступности сервера показывать его ошибку, а не молча
    откатываться на локальную очередь.
    """
    ssh_map = _ssh_map()
    targets = []
    for path in os.environ.get("SCRIPTS_PROJECT_PATHS", "").split(","):
        path = path.strip()
        if not path:
            continue
        name = Path(path).name.lower()
        target = ssh_map.get(name)
        if target not in targets:
            targets.append(target)
    return targets


@router.get("/atq")
def get_queue():
    # Без настроенных проектов — прежнее поведение: локальная очередь
    targets = _project_targets() or [None]
    sections = []
    errors = []
    for target in targets:
        label = target or LOCAL_LABEL
        try:
            if target is None:
                result = subprocess.run("atq", shell=True, capture_output=True, text=True)
            else:
                result = _run_ssh(target, ["atq"])
        except subprocess.TimeoutExpired:
            errors.append(f"[{label}] SSH: таймаут подключения ({SSH_TIMEOUT} c)")
            continue
        if result.returncode != 0:
            errors.append(f"[{label}] {result.stderr.strip() or 'atq failed'}")
            continue
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        if lines:
            sections.append("\n".join(f"[{label}] {line}" for line in lines))
    output = "\n".join(sections)
    if errors:
        output = (output + "\n" if output else "") + "\n".join(errors)
    return {"output": output}


def _parse_task_ref(ref: str):
    """Разобрать ссылку на задачу очереди.

    '123'            → (None, '123')          — локальная очередь
    'local:123'      → (None, '123')
    'user@host:123'  → ('user@host', '123')
    """
    ref = ref.strip()
    if ref.isdigit():
        return None, ref
    if ":" in ref:
        target, _, job_id = ref.rpartition(":")
        if target and job_id.isdigit():
            return (None if target == LOCAL_LABEL else target), job_id
    return None, None


@router.post("/remove-task")
def remove_task(data: RemoveTaskRequest):
    if not data.task_id:
        return {"error": "Task ID is required"}
    target, job_id = _parse_task_ref(data.task_id)
    if job_id is None:
        return {"error": "Неверный формат. Укажите ID или <сервер>:<ID> из очереди."}
    if target is not None and target not in set(_ssh_map().values()):
        return {"error": f"Неизвестный сервер '{target}'"}
    try:
        if target is None:
            result = subprocess.run(
                f"atrm {job_id}", shell=True, capture_output=True, text=True
            )
        else:
            result = _run_ssh(target, ["atrm", job_id])
        if result.returncode != 0:
            return {"error": result.stderr.strip() or "atrm failed"}
        return {"message": f"Задача {data.task_id} удалена!", "output": result.stdout}
    except subprocess.TimeoutExpired:
        return {"error": f"SSH: таймаут подключения ({SSH_TIMEOUT} c)"}
    except Exception as e:
        return {"error": str(e)}
