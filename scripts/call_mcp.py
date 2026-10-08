#!/usr/bin/env python
"""Call an MCP tool with the token from get_token.py. Usage: call_mcp.py whoami [json-args]"""
import json
import os
import pathlib
import sys

import httpx

URL = os.environ.get("MCP_URL", "http://localhost:8080/mcp")
TOKEN = pathlib.Path(__file__).with_name("..").joinpath(".token").resolve().read_text().strip()
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}


def body(response):
    if response.headers.get("content-type", "").startswith("text/event-stream"):
        for line in response.text.splitlines():
            if line.startswith("data:"):
                return json.loads(line[5:])
    return response.json() if response.content else None


def main():
    name = sys.argv[1]
    args = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    with httpx.Client(headers=HEADERS, timeout=30) as client:
        r = client.post(URL, json={
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                       "clientInfo": {"name": "poc", "version": "0"}}})
        if r.status_code != 200:
            print(r.status_code, dict(r.headers), r.text)
            return
        client.headers["mcp-session-id"] = r.headers["mcp-session-id"]
        client.post(URL, json={"jsonrpc": "2.0", "method": "notifications/initialized"})

        listed = body(client.post(URL, json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"}))
        print("tools:", [t["name"] for t in listed["result"]["tools"]])

        r = client.post(URL, json={"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                                   "params": {"name": name, "arguments": args}})
        print(f"{name}: {r.status_code}", json.dumps(body(r), indent=2) if r.content else r.headers)


if __name__ == "__main__":
    main()
