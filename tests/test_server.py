import httpx
import pytest
from fastmcp.exceptions import ToolError
from fastmcp.server.auth.providers.jwt import JWTVerifier, RSAKeyPair
from fastmcp.utilities.tests import ASGIServer, asgi_server

from backend.app import app as backend_app
from mcp_server.server import ADMIN, READ, build_server

ISSUER = "https://example.okta.com/oauth2/default"
BASE_URL = "http://localhost:8080"
AUDIENCE = f"{BASE_URL}/mcp"
OKTA = RSAKeyPair.generate()


def okta_token(scp=(READ,), groups=("mcp-readers",), audience=AUDIENCE, issuer=ISSUER, expires_in=3600, key=OKTA) -> str:
    """A token shaped like Okta's: scopes in a `scp` list, groups in a `groups` claim."""
    return key.create_token(
        subject="ada@example.com",
        issuer=issuer,
        audience=audience,
        expires_in_seconds=expires_in,
        additional_claims={"scp": list(scp), "groups": list(groups)},
    )


READER = okta_token()
ADMIN_TOKEN = okta_token(scp=(READ, ADMIN), groups=("mcp-readers", "mcp-admins"))


@pytest.fixture
async def server():
    verifier = JWTVerifier(public_key=OKTA.public_key, issuer=ISSUER, audience=AUDIENCE, required_scopes=[READ])
    backend = httpx.AsyncClient(transport=httpx.ASGITransport(app=backend_app), base_url="http://backend")
    async with asgi_server(build_server(verifier, ISSUER, BASE_URL, backend)) as s:
        yield s
    await backend.aclose()


async def post(server: ASGIServer, token: str | None = None):
    headers = {"Accept": "application/json, text/event-stream"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    async with server.http_client(headers=headers) as http:
        return await http.post(server.url, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})


async def test_no_token_gets_401_pointing_at_the_resource_metadata(server):
    r = await post(server)
    assert r.status_code == 401
    challenge = r.headers["www-authenticate"]
    assert challenge.startswith("Bearer") and 'resource_metadata="http://localhost:8080/.well-known/oauth-protected-resource/mcp"' in challenge


async def test_resource_metadata_names_okta_and_this_server(server):
    async with server.http_client() as http:
        meta = (await http.get("http://127.0.0.1/.well-known/oauth-protected-resource/mcp")).json()
    assert meta["resource"] == AUDIENCE
    assert meta["authorization_servers"] == [ISSUER]
    assert set(meta["scopes_supported"]) == {READ, ADMIN}


@pytest.mark.parametrize(
    "bad",
    [
        okta_token(audience="http://some-other-api/mcp"),
        okta_token(issuer="https://evil.example.com/oauth2/default"),
        okta_token(expires_in=-60),
        okta_token(key=RSAKeyPair.generate()),
        okta_token(scp=("openid",)),
    ],
    ids=["wrong audience", "wrong issuer", "expired", "wrong signing key", "no mcp scope"],
)
async def test_tokens_okta_did_not_issue_for_this_server_are_rejected(server, bad):
    r = await post(server, bad)
    assert r.status_code == 401 and 'error="invalid_token"' in r.headers["www-authenticate"]


async def test_a_reader_sees_and_calls_only_reader_tools(server):
    async with server.client(auth=READER) as client:
        assert sorted(t.name for t in await client.list_tools()) == ["hello", "whoami"]
        assert (await client.call_tool("hello", {"name": "ada"})).data == "hello ada"
        with pytest.raises(ToolError):
            await client.call_tool("admin_stats")


async def test_an_admin_also_gets_admin_stats_from_the_backend(server):
    async with server.client(auth=ADMIN_TOKEN) as client:
        assert sorted(t.name for t in await client.list_tools()) == ["admin_stats", "hello", "whoami"]
        assert (await client.call_tool("admin_stats")).data == {"requests_today": 42, "queue_depth": 3}


async def test_whoami_reports_what_okta_put_in_the_token(server):
    async with server.client(auth=ADMIN_TOKEN) as client:
        me = (await client.call_tool("whoami")).data
    assert me["user"] == "ada@example.com" and me["groups"] == ["mcp-readers", "mcp-admins"]
    assert me["scopes"] == [READ, ADMIN] and me["issuer"] == ISSUER and me["audience"] == AUDIENCE


async def test_every_tool_is_marked_read_only(server):
    async with server.client(auth=ADMIN_TOKEN) as client:
        assert all(t.annotations.read_only_hint for t in await client.list_tools())
