import os

import httpx
from fastmcp import FastMCP
from fastmcp.server.auth import RemoteAuthProvider, TokenVerifier, require_scopes
from fastmcp.server.auth.providers.jwt import JWTVerifier
from fastmcp.server.dependencies import get_access_token
from mcp_types import ToolAnnotations
from pydantic import AnyHttpUrl

READ = "mcp:tools.read"
ADMIN = "mcp:tools.admin"
READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)


def build_server(verifier: TokenVerifier, issuer: str, base_url: str, backend: httpx.AsyncClient) -> FastMCP:
    auth = RemoteAuthProvider(
        token_verifier=verifier,
        authorization_servers=[AnyHttpUrl(issuer)],
        base_url=base_url,
        scopes_supported=[READ, ADMIN],
    )
    mcp = FastMCP(name="okta-poc", auth=auth)

    @mcp.tool(auth=require_scopes(READ), annotations=READ_ONLY)
    async def hello(name: str = "world") -> str:
        """Say hello via the backend service."""
        r = await backend.get("/hello", params={"name": name})
        r.raise_for_status()
        return r.json()["message"]

    @mcp.tool(auth=require_scopes(READ), annotations=READ_ONLY)
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

    @mcp.tool(auth=require_scopes(ADMIN), annotations=READ_ONLY)
    async def admin_stats() -> dict:
        """Backend stats. Needs the mcp:tools.admin scope, which Okta grants only to mcp-admins."""
        r = await backend.get("/stats")
        r.raise_for_status()
        return r.json()

    return mcp


def main() -> None:
    issuer = os.environ["OKTA_ISSUER"].rstrip("/")
    base_url = os.environ["MCP_BASE_URL"].rstrip("/")
    audience = os.environ.get("MCP_AUDIENCE", f"{base_url}/mcp")
    verifier = JWTVerifier(jwks_uri=f"{issuer}/v1/keys", issuer=issuer, audience=audience, required_scopes=[READ])
    backend = httpx.AsyncClient(base_url=os.environ.get("BACKEND_URL", "http://backend:8000"), timeout=10)
    build_server(verifier, issuer, base_url, backend).run(transport="http", host="0.0.0.0", port=8080, path="/mcp")


if __name__ == "__main__":
    main()
