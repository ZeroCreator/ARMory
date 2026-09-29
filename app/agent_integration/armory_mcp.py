"""Точка входа stdio MCP-сервера для локальных клиентов ARMory."""

from app.agent_integration.server import mcp_server


def main() -> None:
    mcp_server.run(transport="stdio")


if __name__ == "__main__":
    main()
