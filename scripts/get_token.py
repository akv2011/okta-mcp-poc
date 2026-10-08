#!/usr/bin/env python
"""Run the Okta login the way an MCP client does, and print the token's claims.

Proves the whole chain: PKCE authorization code, resource parameter, audience, groups.
"""
import base64
import hashlib
import http.server
import json
import os
import secrets
import threading
import urllib.parse
import webbrowser

import httpx

ISSUER = os.environ["OKTA_ISSUER"].rstrip("/")
CLIENT_ID = os.environ["OKTA_CLIENT_ID"]
RESOURCE = os.environ.get("MCP_AUDIENCE", "http://localhost:8080")
REDIRECT_URI = "http://127.0.0.1:8765/callback"
SCOPE = os.environ.get("SCOPES", "openid profile mcp:tools.read mcp:tools.write offline_access")

verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).rstrip(b"=").decode()
challenge = base64.urlsafe_b64encode(
    hashlib.sha256(verifier.encode()).digest()
).rstrip(b"=").decode()
state = secrets.token_urlsafe(16)
received = {}


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        received.update(urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query))
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Done, close this tab.")
        threading.Thread(target=self.server.shutdown).start()

    def log_message(self, *args):
        pass


def main():
    url = f"{ISSUER}/v1/authorize?" + urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "response_type": "code",
        "scope": SCOPE,
        "redirect_uri": REDIRECT_URI,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "resource": RESOURCE,
    })
    print(url)
    webbrowser.open(url)
    server = http.server.HTTPServer(("127.0.0.1", 8765), Handler)
    server.serve_forever()

    if received.get("state", [None])[0] != state:
        raise SystemExit("state mismatch")
    if "code" not in received:
        raise SystemExit(f"no code: {received}")

    r = httpx.post(f"{ISSUER}/v1/token", data={
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "code": received["code"][0],
        "redirect_uri": REDIRECT_URI,
        "code_verifier": verifier,
        "resource": RESOURCE,
    })
    r.raise_for_status()
    token = r.json()["access_token"]

    payload = token.split(".")[1]
    claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    print(json.dumps(claims, indent=2))
    with open(".token", "w") as f:
        f.write(token)
    print("\naccess token written to .token")


if __name__ == "__main__":
    main()
