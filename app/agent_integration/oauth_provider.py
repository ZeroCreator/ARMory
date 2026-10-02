"""Хранилище и OAuth-провайдер для HTTP MCP-клиентов ARMory."""

from __future__ import annotations

import datetime
import hashlib
import secrets
from urllib.parse import urlsplit

from sqlalchemy import select, update

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    AuthorizeError,
    OAuthAuthorizationServerProvider,
    RefreshToken,
    RegistrationError,
    TokenError,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

from app.auth import normalize_email
from app.config import get_settings
from app.database import AsyncSessionLocal
from app.models import MCPOAuthClient, MCPOAuthGrant, MCPOAuthToken


_SCOPE = "kanban"
_AUTHORIZATION_LIFETIME_SECONDS = 600
_ACCESS_LIFETIME_SECONDS = 43200
_REFRESH_LIFETIME_SECONDS = 2592000


class MCPAccessToken(AccessToken):
    """OAuth-токен MCP с подтверждённым email пользователя ARMory."""

    user_email: str | None = None


class MCPAuthorizationCode(AuthorizationCode):
    """Одноразовый код OAuth с email пользователя ARMory."""

    user_email: str


class MCPRefreshToken(RefreshToken):
    """Refresh-токен MCP, связанный с пользователем и семьёй токенов."""

    user_email: str
    resource: str
    family_id: str


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


def _timestamp(value: datetime.datetime) -> int:
    if value.tzinfo is None:
        value = value.replace(tzinfo=datetime.timezone.utc)
    return int(value.timestamp())


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _allowed_redirect_uri(uri: str) -> bool:
    try:
        parsed = urlsplit(uri)
        hostname = (parsed.hostname or "").casefold()
        if parsed.username or parsed.password or parsed.fragment:
            return False
        if parsed.scheme == "https":
            return bool(hostname)
        return parsed.scheme == "http" and hostname in {"localhost", "127.0.0.1", "::1"}
    except ValueError:
        return False


class ArmoryMCPAuthProvider(
    OAuthAuthorizationServerProvider[
        MCPAuthorizationCode,
        MCPRefreshToken,
        MCPAccessToken,
    ]
):
    """Регистрирует MCP-клиенты и выдаёт OAuth-токены после входа в ARMory."""

    @property
    def issuer_url(self) -> str:
        return f"{get_settings().armory_public_url.rstrip('/')}/mcp"

    @property
    def resource_url(self) -> str:
        return self.issuer_url

    @property
    def authorization_complete_url(self) -> str:
        return f"{self.issuer_url}/oauth/complete"

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        async with AsyncSessionLocal() as db:
            row = await db.get(MCPOAuthClient, client_id)
        if row is None:
            return None
        return OAuthClientInformationFull.model_validate(row.client_info)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        if client_info.token_endpoint_auth_method != "none" or client_info.client_secret:
            raise RegistrationError(
                "invalid_client_metadata",
                "ARMory MCP supports public OAuth clients only",
            )
        if not client_info.redirect_uris or any(
            not _allowed_redirect_uri(str(uri)) for uri in client_info.redirect_uris
        ):
            raise RegistrationError(
                "invalid_redirect_uri",
                "Redirect URIs must use HTTPS or a loopback HTTP address",
            )
        requested_scopes = set((client_info.scope or _SCOPE).split())
        if requested_scopes != {_SCOPE}:
            raise RegistrationError("invalid_client_metadata", "Only the kanban scope is supported")

        async with AsyncSessionLocal() as db:
            db.add(
                MCPOAuthClient(
                    client_id=client_info.client_id,
                    client_info=client_info.model_dump(mode="json", exclude_none=True),
                )
            )
            await db.commit()

    async def authorize(
        self,
        client: OAuthClientInformationFull,
        params: AuthorizationParams,
    ) -> str:
        if not params.state:
            raise AuthorizeError("invalid_request", "The state parameter is required")
        if params.resource and params.resource.rstrip("/") != self.resource_url.rstrip("/"):
            raise AuthorizeError("invalid_request", "The requested resource does not match ARMory MCP")

        scopes = params.scopes or (client.scope or _SCOPE).split()
        if set(scopes) != {_SCOPE}:
            raise AuthorizeError("invalid_scope", "Only the kanban scope is supported")

        authorization_id = secrets.token_urlsafe(32)
        now = _now()
        async with AsyncSessionLocal() as db:
            db.add(
                MCPOAuthGrant(
                    id=authorization_id,
                    client_id=client.client_id,
                    redirect_uri=str(params.redirect_uri),
                    redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
                    state=params.state,
                    code_challenge=params.code_challenge,
                    code_challenge_method="S256",
                    scopes=scopes,
                    resource=self.resource_url,
                    status="pending",
                    created_at=now,
                    expires_at=now + datetime.timedelta(seconds=_AUTHORIZATION_LIFETIME_SECONDS),
                )
            )
            await db.commit()

        return construct_redirect_uri(
            self.authorization_complete_url,
            request_id=authorization_id,
        )

    async def complete_authorization(self, request_id: str, email: str) -> str | None:
        email = normalize_email(email)
        if not email:
            return None

        now = _now()
        authorization_code = secrets.token_urlsafe(48)
        code_hash = _hash_token(authorization_code)
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(MCPOAuthGrant).where(
                    MCPOAuthGrant.id == request_id,
                    MCPOAuthGrant.status == "pending",
                    MCPOAuthGrant.used_at.is_(None),
                    MCPOAuthGrant.expires_at > now,
                )
            )
            grant = result.scalar_one_or_none()
            if grant is None:
                return None

            grant.user_email = email
            grant.code_hash = code_hash
            grant.status = "issued"
            grant.expires_at = now + datetime.timedelta(seconds=_AUTHORIZATION_LIFETIME_SECONDS)
            redirect_uri = grant.redirect_uri
            state = grant.state
            await db.commit()

        return construct_redirect_uri(
            redirect_uri,
            code=authorization_code,
            state=state,
            iss=self.issuer_url,
        )

    async def load_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: str,
    ) -> MCPAuthorizationCode | None:
        now = _now()
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(MCPOAuthGrant).where(
                    MCPOAuthGrant.code_hash == _hash_token(authorization_code),
                    MCPOAuthGrant.client_id == client.client_id,
                    MCPOAuthGrant.status == "issued",
                    MCPOAuthGrant.used_at.is_(None),
                    MCPOAuthGrant.expires_at > now,
                )
            )
            grant = result.scalar_one_or_none()
        if grant is None or not grant.user_email:
            return None

        return MCPAuthorizationCode(
            code=authorization_code,
            scopes=grant.scopes,
            expires_at=_timestamp(grant.expires_at),
            client_id=grant.client_id,
            code_challenge=grant.code_challenge,
            redirect_uri=grant.redirect_uri,
            redirect_uri_provided_explicitly=grant.redirect_uri_provided_explicitly,
            resource=grant.resource,
            user_email=grant.user_email,
        )

    async def exchange_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: MCPAuthorizationCode,
    ) -> OAuthToken:
        now = _now()
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                update(MCPOAuthGrant)
                .where(
                    MCPOAuthGrant.code_hash == _hash_token(authorization_code.code),
                    MCPOAuthGrant.client_id == client.client_id,
                    MCPOAuthGrant.status == "issued",
                    MCPOAuthGrant.used_at.is_(None),
                    MCPOAuthGrant.expires_at > now,
                )
                .values(status="used", used_at=now)
            )
            if result.rowcount != 1:
                raise TokenError("invalid_grant", "The authorization code has already been used or expired")
            token_response = self._issue_tokens(
                db,
                client_id=client.client_id,
                email=authorization_code.user_email,
                scopes=authorization_code.scopes,
                resource=authorization_code.resource or self.resource_url,
            )
            await db.commit()
        return token_response

    async def load_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: str,
    ) -> MCPRefreshToken | None:
        now = _now()
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(MCPOAuthToken).where(
                    MCPOAuthToken.token_hash == _hash_token(refresh_token),
                    MCPOAuthToken.token_type == "refresh",
                    MCPOAuthToken.client_id == client.client_id,
                    MCPOAuthToken.revoked_at.is_(None),
                    MCPOAuthToken.expires_at > now,
                )
            )
            token = result.scalar_one_or_none()
        if token is None:
            return None

        return MCPRefreshToken(
            token=refresh_token,
            client_id=token.client_id,
            scopes=token.scopes,
            expires_at=_timestamp(token.expires_at),
            user_email=token.user_email,
            resource=token.resource,
            family_id=token.family_id,
        )

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: MCPRefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        if not set(scopes).issubset(set(refresh_token.scopes)):
            raise TokenError("invalid_scope", "The refresh token does not grant the requested scope")

        now = _now()
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                update(MCPOAuthToken)
                .where(
                    MCPOAuthToken.token_hash == _hash_token(refresh_token.token),
                    MCPOAuthToken.token_type == "refresh",
                    MCPOAuthToken.client_id == client.client_id,
                    MCPOAuthToken.revoked_at.is_(None),
                    MCPOAuthToken.expires_at > now,
                )
                .values(revoked_at=now)
            )
            if result.rowcount != 1:
                raise TokenError("invalid_grant", "The refresh token has already been used or expired")
            token_response = self._issue_tokens(
                db,
                client_id=client.client_id,
                email=refresh_token.user_email,
                scopes=scopes,
                resource=refresh_token.resource,
                family_id=refresh_token.family_id,
            )
            await db.commit()
        return token_response

    async def load_access_token(self, token: str) -> MCPAccessToken | None:
        settings = get_settings()
        if settings.mcp_api_key and secrets.compare_digest(token, settings.mcp_api_key):
            return MCPAccessToken(
                token=token,
                client_id="mcp-api-key",
                scopes=[_SCOPE],
                resource=self.resource_url,
            )

        now = _now()
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(MCPOAuthToken).where(
                    MCPOAuthToken.token_hash == _hash_token(token),
                    MCPOAuthToken.token_type == "access",
                    MCPOAuthToken.revoked_at.is_(None),
                    MCPOAuthToken.expires_at > now,
                    MCPOAuthToken.resource == self.resource_url,
                )
            )
            row = result.scalar_one_or_none()
        if row is None:
            return None

        return MCPAccessToken(
            token=token,
            client_id=row.client_id,
            scopes=row.scopes,
            expires_at=_timestamp(row.expires_at),
            resource=row.resource,
            user_email=row.user_email,
        )

    async def revoke_token(self, token: MCPAccessToken | MCPRefreshToken) -> None:
        now = _now()
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(MCPOAuthToken.family_id).where(
                    MCPOAuthToken.token_hash == _hash_token(token.token),
                    MCPOAuthToken.client_id == token.client_id,
                )
            )
            family_id = result.scalar_one_or_none()
            if family_id:
                await db.execute(
                    update(MCPOAuthToken)
                    .where(MCPOAuthToken.family_id == family_id, MCPOAuthToken.revoked_at.is_(None))
                    .values(revoked_at=now)
                )
                await db.commit()

    def _issue_tokens(
        self,
        db,
        *,
        client_id: str,
        email: str,
        scopes: list[str],
        resource: str,
        family_id: str | None = None,
    ) -> OAuthToken:
        now = _now()
        family_id = family_id or secrets.token_urlsafe(24)
        access_token = secrets.token_urlsafe(48)
        refresh_token = secrets.token_urlsafe(48)
        db.add_all(
            [
                MCPOAuthToken(
                    token_hash=_hash_token(access_token),
                    token_type="access",
                    family_id=family_id,
                    client_id=client_id,
                    user_email=email,
                    scopes=scopes,
                    resource=resource,
                    created_at=now,
                    expires_at=now + datetime.timedelta(seconds=_ACCESS_LIFETIME_SECONDS),
                ),
                MCPOAuthToken(
                    token_hash=_hash_token(refresh_token),
                    token_type="refresh",
                    family_id=family_id,
                    client_id=client_id,
                    user_email=email,
                    scopes=scopes,
                    resource=resource,
                    created_at=now,
                    expires_at=now + datetime.timedelta(seconds=_REFRESH_LIFETIME_SECONDS),
                ),
            ]
        )
        return OAuthToken(
            access_token=access_token,
            token_type="Bearer",
            expires_in=_ACCESS_LIFETIME_SECONDS,
            refresh_token=refresh_token,
            scope=" ".join(scopes),
        )


mcp_oauth_provider = ArmoryMCPAuthProvider()
