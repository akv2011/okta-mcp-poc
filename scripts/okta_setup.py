#!/usr/bin/env python
"""Configure an Okta org for the MCP POC. Idempotent: safe to re-run.

Needs OKTA_ORG_URL and OKTA_API_TOKEN (Security > API > Tokens in the admin console).
"""
import os
import sys

import httpx

ORG = os.environ["OKTA_ORG_URL"].rstrip("/")
AUDIENCE = os.environ.get("MCP_AUDIENCE", "http://localhost:8080/mcp")
SCOPES = {
    "mcp:tools.read": "Call read-only MCP tools",
    "mcp:tools.admin": "Call admin MCP tools",
}
GROUPS = {
    "mcp-readers": ["mcp:tools.read"],
    "mcp-admins": ["mcp:tools.read", "mcp:tools.admin"],
}
REDIRECT_URIS = [
    "http://127.0.0.1:8765/callback",          # scripts/get_token.py
    "http://localhost/callback",               # Claude Code loopback
    "http://127.0.0.1/callback",               # Claude Code, Codex CLI
    "https://claude.ai/api/mcp/auth_callback",  # Claude app and web
]

http = httpx.Client(
    base_url=ORG,
    headers={"Authorization": f"SSWS {os.environ['OKTA_API_TOKEN']}", "Accept": "application/json"},
    timeout=30,
)


def api(method, path, **kw):
    r = http.request(method, path, **kw)
    if r.status_code >= 400:
        sys.exit(f"{method} {path} -> {r.status_code}\n{r.text}")
    return r.json() if r.content else None


def find(items, key, value):
    return next((i for i in items if i.get(key) == value), None)


def main():
    servers = api("GET", "/api/v1/authorizationServers")
    server = find(servers, "name", "default") or servers[0]
    sid = server["id"]
    issuer = server["issuer"]

    if AUDIENCE not in server["audiences"]:
        server["audiences"] = [AUDIENCE]
        api("PUT", f"/api/v1/authorizationServers/{sid}", json=server)
        print(f"audience -> {AUDIENCE}")

    existing = {s["name"] for s in api("GET", f"/api/v1/authorizationServers/{sid}/scopes")}
    for name, description in SCOPES.items():
        if name not in existing:
            api("POST", f"/api/v1/authorizationServers/{sid}/scopes", json={
                "name": name, "description": description,
                "consent": "IMPLICIT", "metadataPublish": "ALL_CLIENTS",
            })
            print(f"scope -> {name}")

    claims = api("GET", f"/api/v1/authorizationServers/{sid}/claims")
    if not find(claims, "name", "groups"):
        api("POST", f"/api/v1/authorizationServers/{sid}/claims", json={
            "name": "groups", "status": "ACTIVE", "claimType": "RESOURCE",
            "valueType": "GROUPS", "value": "mcp-.*", "group_filter_type": "REGEX",
            "alwaysIncludeInToken": True, "conditions": {"scopes": []},
        })
        print("claim -> groups")

    group_ids = {}
    for name in GROUPS:
        found = next((g for g in api("GET", "/api/v1/groups", params={"q": name})
                      if g["profile"]["name"] == name), None)
        if not found:
            found = api("POST", "/api/v1/groups", json={
                "profile": {"name": name, "description": "MCP POC"}})
            print(f"group -> {name}")
        group_ids[name] = found["id"]

    label = "MCP POC"
    app = next((a for a in api("GET", "/api/v1/apps", params={"q": label})
                if a["label"] == label), None)
    if not app:
        app = api("POST", "/api/v1/apps", json={
            "name": "oidc_client", "label": label, "signOnMode": "OPENID_CONNECT",
            "credentials": {"oauthClient": {"token_endpoint_auth_method": "none"}},
            "settings": {"oauthClient": {
                "application_type": "native",
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "redirect_uris": REDIRECT_URIS,
                "consent_method": "TRUSTED",
                "issuer_mode": "ORG_URL",
            }},
        })
        print(f"app -> {label}")
    client_id = app["credentials"]["oauthClient"]["client_id"]

    for name, gid in group_ids.items():
        api("PUT", f"/api/v1/apps/{app['id']}/groups/{gid}", json={})

    policies = api("GET", f"/api/v1/authorizationServers/{sid}/policies")
    policy = find(policies, "name", label)
    if not policy:
        policy = api("POST", f"/api/v1/authorizationServers/{sid}/policies", json={
            "type": "OAUTH_AUTHORIZATION_POLICY", "status": "ACTIVE", "name": label,
            "description": "Scopes by Okta group", "priority": 1,
            "conditions": {"clients": {"include": [client_id]}},
        })
        print(f"policy -> {label}")

    rules = api("GET", f"/api/v1/authorizationServers/{sid}/policies/{policy['id']}/rules")
    for priority, (group, scopes) in enumerate(reversed(list(GROUPS.items())), start=1):
        if find(rules, "name", group):
            continue
        api("POST", f"/api/v1/authorizationServers/{sid}/policies/{policy['id']}/rules", json={
            "type": "RESOURCE_ACCESS", "name": group, "priority": priority, "status": "ACTIVE",
            "conditions": {
                "people": {"groups": {"include": [group_ids[group]]}},
                "grantTypes": {"include": ["authorization_code"]},
                "scopes": {"include": scopes + ["openid", "profile", "offline_access"]},
            },
            "actions": {"token": {
                "accessTokenLifetimeMinutes": 60,
                "refreshTokenLifetimeMinutes": 0,
                "refreshTokenWindowMinutes": 10080,
            }},
        })
        print(f"rule -> {group} {scopes}")

    print("\nPut these in .env:")
    print(f"OKTA_ISSUER={issuer}")
    print(f"OKTA_CLIENT_ID={client_id}")
    print(f"MCP_AUDIENCE={AUDIENCE}")
    print("\nAdd yourself to a group in the admin console: Directory > Groups > mcp-admins.")


if __name__ == "__main__":
    main()
