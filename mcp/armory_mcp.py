#!/usr/bin/env python3
"""stdio MCP-сервер для интеграции Kimi Code CLI с канбаном ARMory."""

import json
import os
import sys
from typing import Any

from mcp.mcp_logic import handle_message

LOG_FILE = os.environ.get("ARMORY_MCP_LOG", "/tmp/armory_mcp.log")


def _log(*args: Any) -> None:
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(" ".join(str(a) for a in args) + "\n")
    except Exception:
        pass


def send_message(msg: dict[str, Any]) -> None:
    data = json.dumps(msg, ensure_ascii=False)
    _log("SEND", data)
    sys.stdout.write(f"Content-Length: {len(data.encode('utf-8'))}\r\n\r\n{data}")
    sys.stdout.flush()


def make_error(id_: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": id_,
        "error": {"code": code, "message": message},
    }


def main() -> None:
    _log("START")
    while True:
        headers = {}
        while True:
            line = sys.stdin.readline()
            if not line:
                _log("STDIN_CLOSED")
                return
            line = line.strip()
            if line == "":
                break
            if ":" in line:
                key, value = line.split(":", 1)
                headers[key.strip().lower()] = value.strip()

        _log("HEADERS", headers)
        length = int(headers.get("content-length", "0"))
        if length == 0:
            continue

        raw = sys.stdin.read(length)
        _log("BODY", raw)
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError as exc:
            _log("PARSE_ERROR", str(exc))
            send_message(make_error(None, -32700, "Parse error"))
            continue

        result = handle_message(msg)
        id_ = msg.get("id")
        if result is None:
            continue

        response = {"jsonrpc": "2.0", "id": id_}
        if "error" in result:
            response["error"] = result["error"]
        else:
            response["result"] = result
        send_message(response)


if __name__ == "__main__":
    main()
