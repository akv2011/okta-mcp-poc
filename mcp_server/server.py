import os

import httpx
from fastmcp import FastMCP
from fastmcp.server.auth import RemoteAuthProvider, require_scopes
from fastmcp.server.auth.providers.jwt import JWTVerifier
from fastmcp.server.dependencies import get_access_token
from pydantic import AnyHttpUrl

ISSUER = os.environ["OKTA_ISSUER"].rstrip("/")
BASE_URL = os.environ["MCP_BASE_URL"].rstrip("/")
AUDIENCE = os.environ.get("MCP_AUDIENCE", BASE_URL)
BACKEND_URL = os.environ.get("BACKEND_URL", "http://backend:8000")

auth = RemoteAuthProvider(
    token_verifier=JWTVerifier(
        jwks_uri=f"{ISSUER}/v1/keys",
        issuer=ISSUER,
        audience=AUDIENCE,
        required_scopes=["mcp:tools.read"],
    ),
    authorization_servers=[AnyHttpUrl(ISSUER)],
    base_url=BASE_URL,
)

mcp = FastMCP(name="okta-poc", auth=auth)


@mcp.tool(auth=require_scopes("mcp:tools.read"))
async def hello(name: str = "world") -> str:
    """Say hello via the backend service."""
    async with httpx.AsyncClient(base_url=BACKEND_URL) as client:
        r = await client.get("/hello", params={"name": name})
        r.raise_for_status()
        return r.json()["message"]


@mcp.tool(auth=require_scopes("mcp:tools.read"))
def whoami() -> dict:
    """Show the Okta identity and roles behind the current token."""
    claims = get_access_token().claims
    return {
        "user": claims.get("sub"),
        "groups": claims.get("groups", []),
        "scopes": claims.get("scp", []),
        "issuer": claims.get("iss"),
        "audience": claims.get("aud"),
    }


@mcp.tool(auth=require_scopes("mcp:tools.write"))
async def admin_stats() -> dict:
    """Backend stats. Requires the mcp:tools.write scope, granted only to mcp-admins."""
    async with httpx.AsyncClient(base_url=BACKEND_URL) as client:
        r = await client.get("/stats")
        r.raise_for_status()
        return r.json()


if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8080, path="/mcp")
