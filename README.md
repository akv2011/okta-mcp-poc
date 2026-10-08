# MCP server with Okta sign-in and group-based tool access

An MCP server that acts as an OAuth resource server, in front of a small hello-world backend. Okta signs people in and issues the tokens, and Okta groups decide which tools each person can see and call. No secret sits in any config file and no token has to be rotated by hand.

A call without a token gets `401` with a pointer to the server's protected resource metadata, which names the Okta authorization server. The client opens the browser, the person signs in to Okta, and the client receives a token whose audience is this MCP server. On every call the server checks the token's signature against Okta's published keys, its issuer, expiry and audience, then reads the `groups` and `scp` claims to decide what the caller may do.

## Tools and roles

| Tool | Scope | Okta groups |
|---|---|---|
| `hello` | `mcp:tools.read` | mcp-readers, mcp-admins |
| `whoami` | `mcp:tools.read` | mcp-readers, mcp-admins |
| `admin_stats` | `mcp:tools.admin` | mcp-admins |

A reader's `tools/list` returns only `hello` and `whoami`. Moving a person between groups in Okta changes what they can call, with no code change and no restart. All three tools are marked read-only.

## 1. Configure Okta

Needs an Okta org (the Integrator Free Plan is enough) and an API token from Security > API > Tokens.

```sh
uv sync
export OKTA_ORG_URL=https://<your-org>.okta.com
export OKTA_API_TOKEN=<api token>
export MCP_AUDIENCE=http://localhost:8080/mcp
uv run python scripts/okta_setup.py
```

On the built-in `default` authorization server this creates the audience, the scopes `mcp:tools.read` and `mcp:tools.admin`, a `groups` claim filtered to `mcp-*`, the groups `mcp-readers` and `mcp-admins`, a public OIDC app holding every client's redirect URI, and the policy rules that grant the admin scope to admins only. Running it again changes nothing.

It prints the issuer and client ID. Copy `.env.example` to `.env` and paste them in, then add yourself to a group under Directory > Groups.

Revoke the API token afterwards. Nothing else needs it.

## 2. Run

```sh
docker compose up -d --build
```

## 3. Check it

```sh
curl -i -X POST http://localhost:8080/mcp -d '{}'                    # 401 + WWW-Authenticate
curl http://localhost:8080/.well-known/oauth-protected-resource/mcp
uv run --env-file .env python scripts/get_token.py                  # Okta sign-in, writes .token
uv run python scripts/call_mcp.py whoami
uv run python scripts/call_mcp.py hello '{"name": "world"}'
uv run python scripts/call_mcp.py admin_stats
```

`whoami` echoes the Okta user, groups, scopes, issuer and audience taken from the token. `.token` is written with owner-only permissions and is ignored by git.

## 4. Connect a client

```sh
claude mcp add --transport http --client-id <client id> --callback-port 8765 \
  okta-mcp http://localhost:8080/mcp
```

`/mcp` then shows "needs authentication"; choosing Authenticate opens Okta in the browser and comes back connected. Codex CLI takes the same client ID with `mcp_oauth_callback_port`. The Claude and ChatGPT apps need the server on a public HTTPS URL, so put it behind a tunnel or Cloud Run and set `MCP_BASE_URL` and `MCP_AUDIENCE` to that URL (plus `/mcp` for the audience).

## Tests

```sh
uv run pytest
```

11 tests run the real HTTP stack in-process with tokens signed locally in Okta's shape (`scp` as a list, a `groups` claim), so they need no Okta org. They cover the 401 challenge, the protected resource metadata, five kinds of bad token (wrong audience, wrong issuer, expired, wrong signing key, missing scope), a reader seeing two tools and being refused `admin_stats`, an admin getting all three, and `whoami` echoing the token's claims. Granting the admin tool to readers, removing its scope check, reading the wrong claim, advertising the wrong issuer, or removing auth each makes a test fail.

## Layout

```
backend/      hello-world service, the thing being protected
mcp_server/   MCP server, token validation and the three tools
scripts/      okta_setup.py, get_token.py, call_mcp.py
tests/        auth and tool access, without an Okta org
```

## License

MIT
