import logging
from typing import Any

import httpx
from fastapi import Request

from app.config import get_settings

logger = logging.getLogger(__name__)


def get_current_user(request: Request) -> dict[str, str]:
    """Определить текущего пользователя по заголовкам oauth2-proxy.

    В локальной разработке (без прокси) можно задать DEV_USER_EMAIL/DEV_USER_NAME.
    """
    email = (
        request.headers.get("x-forwarded-email")
        or request.headers.get("x-forwarded-user")
        or request.headers.get("remote-user")
    )
    name = request.headers.get("x-forwarded-preferred-username")
    if not email:
        settings = get_settings()
        email = settings.dev_user_email or "unknown"
        name = settings.dev_user_name or name or email
    if not name:
        name = email
    return {"email": email, "name": name}


class PocketBaseClient:
    def __init__(self):
        settings = get_settings()
        self.enabled = settings.pocketbase_enabled
        self.base_url = settings.pocketbase_url.rstrip("/")
        self.admin_token = settings.pocketbase_admin_token
        self.admin_email = settings.pocketbase_admin_email
        self.admin_password = settings.pocketbase_admin_password

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.admin_token:
            headers["Authorization"] = self.admin_token
        return headers

    async def _auth_with_password(self) -> bool:
        """Получить admin-токен (superuser) по email/паролю."""
        if not self.admin_email or not self.admin_password:
            return False
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{self.base_url}/api/collections/_superusers/auth-with-password",
                    json={"identity": self.admin_email, "password": self.admin_password},
                    timeout=10.0,
                )
                resp.raise_for_status()
                data = resp.json()
                self.admin_token = data.get("token")
                return bool(self.admin_token)
        except Exception as e:
            logger.warning("Failed to authenticate PocketBase admin: %s", e)
            return False

    async def _ensure_token(self) -> bool:
        """Убедиться, что есть рабочий токен."""
        if self.admin_token:
            return True
        return await self._auth_with_password()

    async def _request(
        self,
        method: str,
        path: str,
        json_data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        allow_retry: bool = True,
    ) -> httpx.Response | None:
        """Выполнить запрос к PocketBase с retry при 401."""
        if not await self._ensure_token():
            return None
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.request(
                    method=method,
                    url=f"{self.base_url}{path}",
                    headers=self._headers(),
                    json=json_data,
                    params=params,
                    timeout=10.0,
                )
                if resp.status_code == 401 and allow_retry:
                    # Токен мог устареть или быть неверным — пробуем авторизоваться заново
                    self.admin_token = None
                    if await self._auth_with_password():
                        return await self._request(
                            method, path, json_data, params, allow_retry=False
                        )
                    return None
                return resp
        except Exception as e:
            logger.warning("PocketBase request error: %s", e)
            return None

    async def list_records(
        self,
        collection: str,
        filter_expr: str | None = None,
        sort: str | None = None,
        expand: str | None = None,
    ) -> list[dict[str, Any]]:
        if not self.enabled:
            return []
        params: dict[str, Any] = {}
        if filter_expr:
            params["filter"] = filter_expr
        if sort:
            params["sort"] = sort
        if expand:
            params["expand"] = expand
        resp = await self._request(
            "GET", f"/api/collections/{collection}/records", params=params
        )
        if resp is None:
            return []
        try:
            resp.raise_for_status()
            return resp.json().get("items", [])
        except Exception as e:
            logger.warning("PocketBase list_records error: %s", e)
            return []

    async def create_record(self, collection: str, data: dict[str, Any]) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        resp = await self._request(
            "POST", f"/api/collections/{collection}/records", json_data=data
        )
        if resp is None:
            return None
        try:
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning("PocketBase create_record error: %s", e)
            return None

    async def update_record(
        self, collection: str, record_id: str, data: dict[str, Any]
    ) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        resp = await self._request(
            "PATCH", f"/api/collections/{collection}/records/{record_id}", json_data=data
        )
        if resp is None:
            return None
        try:
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning("PocketBase update_record error: %s", e)
            return None

    async def delete_record(self, collection: str, record_id: str) -> bool:
        if not self.enabled:
            return False
        resp = await self._request(
            "DELETE", f"/api/collections/{collection}/records/{record_id}"
        )
        if resp is None:
            return False
        try:
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.warning("PocketBase delete_record error: %s", e)
            return False

    async def get_collection(self, name: str) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        resp = await self._request("GET", f"/api/collections/{name}")
        if resp is None:
            return None
        if resp.status_code == 404:
            return None
        try:
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning("PocketBase get_collection error: %s", e)
            return None

    async def create_collection(self, name: str, schema: list[dict[str, Any]]) -> bool:
        if not self.enabled:
            return False
        payload = {
            "name": name,
            "type": "base",
            "fields": schema,
            "options": {},
        }
        resp = await self._request("POST", "/api/collections", json_data=payload)
        if resp is None:
            return False
        try:
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.warning("PocketBase create_collection error: %s", e)
            return False

    async def ensure_collection(self, name: str, schema: list[dict[str, Any]]) -> bool:
        if not self.enabled:
            return False
        existing = await self.get_collection(name)
        if existing:
            existing_names = {f.get("name") for f in existing.get("fields", [])}
            missing = [f for f in schema if f.get("name") not in existing_names]
            if not missing:
                return True
            # Дополняем схему недостающими полями (например, autodate при создании вручную)
            fields = list(existing.get("fields", []))
            fields.extend(missing)
            payload = {
                "name": existing["name"],
                "type": existing["type"],
                "fields": fields,
                "options": existing.get("options", {}),
            }
            resp = await self._request(
                "PATCH", f"/api/collections/{existing['id']}", json_data=payload
            )
            if resp is None:
                return False
            try:
                resp.raise_for_status()
                return True
            except Exception as e:
                logger.warning("PocketBase update_collection error: %s", e)
                return False
        return await self.create_collection(name, schema)


def _autodate_field(name: str, on_update: bool) -> dict[str, Any]:
    return {
        "name": name,
        "type": "autodate",
        "onCreate": True,
        "onUpdate": on_update,
        "system": False,
        "hidden": False,
        "presentable": False,
    }


# Глобальный клиент
pb_client = PocketBaseClient()


async def ensure_project_comments_collection() -> bool:
    schema = [
        {"name": "project_id", "type": "number", "required": True, "options": {}},
        {"name": "user_email", "type": "text", "required": True, "options": {}},
        {"name": "user_name", "type": "text", "required": False, "options": {}},
        {"name": "text", "type": "text", "required": True, "options": {}},
        {"name": "parent_id", "type": "text", "required": False, "options": {}},
        _autodate_field("created", False),
        _autodate_field("updated", True),
    ]
    return await pb_client.ensure_collection("project_comments", schema)


async def ensure_project_notes_collection() -> bool:
    schema = [
        {"name": "project_id", "type": "number", "required": True, "options": {}},
        {"name": "title", "type": "text", "required": True, "options": {}},
        {"name": "content", "type": "text", "required": True, "options": {}},
        {"name": "user_email", "type": "text", "required": True, "options": {}},
        {"name": "user_name", "type": "text", "required": False, "options": {}},
        {"name": "pinned", "type": "bool", "required": False, "options": {}},
        _autodate_field("created", False),
        _autodate_field("updated", True),
    ]
    return await pb_client.ensure_collection("project_notes", schema)


async def ensure_project_tasks_collection() -> bool:
    schema = [
        {"name": "project_id", "type": "number", "required": True, "options": {}},
        {"name": "title", "type": "text", "required": True, "options": {}},
        {"name": "done", "type": "bool", "required": False, "options": {}},
        {"name": "assignee_email", "type": "text", "required": False, "options": {}},
        {"name": "due_date", "type": "date", "required": False, "options": {}},
        {"name": "sort_order", "type": "number", "required": False, "options": {}},
        _autodate_field("created", False),
        _autodate_field("updated", True),
    ]
    return await pb_client.ensure_collection("project_tasks", schema)


async def ensure_project_activity_collection() -> bool:
    schema = [
        {"name": "project_id", "type": "number", "required": True, "options": {}},
        {"name": "user_email", "type": "text", "required": True, "options": {}},
        {"name": "user_name", "type": "text", "required": False, "options": {}},
        {"name": "action", "type": "text", "required": True, "options": {}},
        {"name": "entity_type", "type": "text", "required": True, "options": {}},
        {"name": "entity_id", "type": "text", "required": True, "options": {}},
        {"name": "description", "type": "text", "required": False, "options": {}},
        _autodate_field("created", False),
        _autodate_field("updated", True),
    ]
    return await pb_client.ensure_collection("project_activity", schema)


async def _log_activity(
    project_id: int,
    user: dict[str, str],
    action: str,
    entity_type: str,
    entity_id: str,
    description: str = "",
) -> None:
    """Записать событие в ленту активности проекта."""
    if not pb_client.enabled:
        return
    await ensure_project_activity_collection()
    await pb_client.create_record(
        "project_activity",
        {
            "project_id": project_id,
            "user_email": user.get("email", "unknown"),
            "user_name": user.get("name") or user.get("email", "unknown"),
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "description": description,
        },
    )
