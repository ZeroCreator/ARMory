import datetime

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agent_integration import oauth_provider
from app.database import Base
from app.models import MCPOAuthClient, MCPOAuthToken
from mcp.shared.auth import OAuthClientInformationFull


@pytest_asyncio.fixture
async def oauth_sessions(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(oauth_provider, "AsyncSessionLocal", sessions)
    yield sessions
    await engine.dispose()


def make_client() -> OAuthClientInformationFull:
    return OAuthClientInformationFull(
        client_id="<client-id>",
        redirect_uris=["https://localhost/callback"],
        token_endpoint_auth_method="none",
        scope="kanban",
    )


@pytest.mark.asyncio
async def test_refresh_token_can_be_exchanged_more_than_once(oauth_sessions):
    client = make_client()
    refresh_value = "<refresh-token>"
    now = oauth_provider._now()
    async with oauth_sessions() as db:
        db.add(MCPOAuthClient(client_id=client.client_id, client_info=client.model_dump(mode="json")))
        db.add(
            MCPOAuthToken(
                token_hash=oauth_provider._hash_token(refresh_value),
                token_type="refresh",
                family_id="<family-id>",
                client_id=client.client_id,
                user_email="<authenticated-email>",
                scopes=["kanban"],
                resource="https://<service-host>/mcp",
                created_at=now,
                expires_at=now + datetime.timedelta(days=1),
            )
        )
        await db.commit()

    provider = oauth_provider.ArmoryMCPAuthProvider()
    refresh = oauth_provider.MCPRefreshToken(
        token=refresh_value,
        client_id=client.client_id,
        scopes=["kanban"],
        expires_at=int((now + datetime.timedelta(days=1)).timestamp()),
        user_email="<authenticated-email>",
        resource="https://<service-host>/mcp",
        family_id="<family-id>",
    )

    first = await provider.exchange_refresh_token(client, refresh, ["kanban"])
    second = await provider.exchange_refresh_token(client, refresh, ["kanban"])

    assert first.refresh_token == refresh_value
    assert second.refresh_token == refresh_value
    assert first.access_token != second.access_token

    async with oauth_sessions() as db:
        stored = await db.execute(
            select(MCPOAuthToken).where(
                MCPOAuthToken.token_hash == oauth_provider._hash_token(refresh_value),
            )
        )
        assert stored.scalar_one().revoked_at is None
