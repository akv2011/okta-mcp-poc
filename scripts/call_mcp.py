#!/usr/bin/env python
"""Call an MCP tool with the token from get_token.py. Usage: call_mcp.py whoami [json-args]"""
import asyncio
import json
import os
import sys
from pathlib import Path

from fastmcp import Client

URL = os.environ.get("MCP_URL", "http://localhost:8080/mcp")
TOKEN_FILE = Path(__file__).resolve().parent.parent / ".token"


async def main() -> None:
    name = sys.argv[1]
    args = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    async with Client(URL, auth=TOKEN_FILE.read_text().strip()) as client:
        print("tools:", [t.name for t in await client.list_tools()])
        result = await client.call_tool(name, args, raise_on_error=False)
        if result.is_error:
            print(f"{name} refused:", " ".join(getattr(c, "text", "") for c in result.content))
        else:
            print(f"{name}:", json.dumps(result.data, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
