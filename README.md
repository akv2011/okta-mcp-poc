# MCP server with Okta authentication and role-based access

A hello-world backend behind an MCP server that acts as an OAuth 2.1 resource server.
Okta issues the tokens, Okta groups decide which tools a caller can use. No secret sits in
any config file and no token has to be rotated by hand.

An unauthenticated call returns `401` with a pointer to the server's protected resource
metadata, which names the Okta authorization server. The client opens the browser, the
user signs in to Okta, and the client receives a token whose audience is this MCP server.
Every later call carries that token; the server checks the signature against Okta's JWKS,
the issuer, the expiry and the audience, and reads the `groups` and `scp` claims to decide
what the caller may do.

## 1. Configure Okta

Needs an Okta org (the Integrator Free Plan is enough) and an API token from
Security > API > Tokens.

```sh
export OKTA_ORG_URL=https://<your-org>.okta.com
export OKTA_API_TOKEN=<api token>
export MCP_AUDIENCE=http://localhost:8080/mcp
python scripts/okta_setup.py
```

This creates, on the built-in `default` authorization server: the audience, the scopes
`mcp:tools.read` and `mcp:tools.write`, a `groups` claim filtered to `mcp-*`, the groups
`mcp-readers` and `mcp-admins`, a public OIDC app holding every client's redirect URI, and
the policy rules that grant the write scope to admins only. Re-running it changes nothing.

It prints the issuer and client ID. Copy `.env.example` to `.env` and paste them in, then
add yourself to a group under Directory > Groups.

Revoke the API token afterwards. Nothing else needs it.

## 2. Run

```sh
docker compose up -d --build
```

## 3. Prove it works

```sh
curl -i -X POST http://localhost:8080/mcp -d '{}'                 # 401 + WWW-Authenticate
curl http://localhost:8080/.well-known/oauth-protected-resource/mcp
python scripts/get_token.py                                        # Okta login, writes .token
python scripts/call_mcp.py whoami
python scripts/call_mcp.py hello '{"name":"world"}'
python scripts/call_mcp.py admin_stats
```

`whoami` echoes the Okta user, groups, scopes, issuer and audience taken from the token.

## 4. Connect a client

```sh
claude mcp add --transport http --client-id <client id> --callback-port 8765 \
  okta-poc http://localhost:8080/mcp
```

`/mcp` then shows "needs authentication"; choosing Authenticate opens Okta in the browser
and comes back connected. Codex CLI takes the same client ID with
`mcp_oauth_callback_port`. The Claude and ChatGPT apps need the server on a public HTTPS
URL, so put it behind a tunnel or Cloud Run and set `MCP_BASE_URL` and `MCP_AUDIENCE` to
that URL plus `/mcp`.

## Tools and roles

| tool | scope | groups |
|---|---|---|
| `hello` | `mcp:tools.read` | readers, admins |
| `whoami` | `mcp:tools.read` | readers, admins |
| `admin_stats` | `mcp:tools.write` | admins |

A reader's `tools/list` returns only `hello` and `whoami`. Moving a user between groups in
Okta changes what they can call, with no code change and no restart.

## Layout

```
backend/      hello-world service, the thing being protected
mcp_server/   MCP server, token validation and the three tools
scripts/      okta_setup.py, get_token.py, call_mcp.py
```
