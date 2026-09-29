#!/usr/bin/env python3
"""One-time Futunn OAuth setup; saves only the refresh token in GitHub Secrets."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import subprocess
import urllib.parse
import urllib.request
import webbrowser


REDIRECT_URI = "https://optimus25564.github.io/A-share-dashboard/"
API_BASE = "https://webapi.futunn.com"
REPOSITORY = "Optimus25564/A-share-dashboard"


def post_json(url: str, value: dict) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(value).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=45) as response:
        return json.load(response)


def exchange(code: str, client_id: str, verifier: str) -> dict:
    form = urllib.parse.urlencode(
        {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": verifier,
        }
    ).encode()
    req = urllib.request.Request(
        f"{API_BASE}/oauth2/token",
        data=form,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=45) as response:
        return json.load(response)


def set_secret(name: str, value: str) -> None:
    subprocess.run(
        ["gh", "secret", "set", name, "--repo", REPOSITORY, "--body", value],
        check=True,
        stdout=subprocess.DEVNULL,
    )


def main() -> None:
    registration = post_json(
        f"{API_BASE}/oauth2/register",
        {
            "redirect_uris": [REDIRECT_URI],
            "token_endpoint_auth_method": "none",
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "client_name": "A-share Dashboard Backend",
        },
    )
    client_id = registration["client_id"]
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(32)
    params = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "redirect_uri": REDIRECT_URI,
            "response_type": "code",
            "state": state,
        }
    )
    auth_url = f"{API_BASE}/oauth2/authorize/confirm?{params}"
    print("Opening Futunn authorization page. Authorize quote read access only.", flush=True)
    print(auth_url, flush=True)
    webbrowser.open(auth_url)
    callback_url = input("Paste the complete callback URL here: ").strip()
    query = urllib.parse.parse_qs(urllib.parse.urlparse(callback_url).query)
    if query.get("state", [None])[0] != state:
        raise SystemExit("OAuth state mismatch")
    code = query.get("code", [None])[0]
    if not code:
        raise SystemExit(query.get("error_description", ["No authorization code"])[0])
    tokens = exchange(code, client_id, verifier)
    set_secret("FUTU_CLIENT_ID", client_id)
    set_secret("FUTU_REFRESH_TOKEN", tokens["refresh_token"])
    print("FUTU_CLIENT_ID and FUTU_REFRESH_TOKEN saved to GitHub Secrets.")


if __name__ == "__main__":
    main()
