"""
Fetch real account-wide token utilization from Anthropic API rate-limit headers.

The Anthropic API includes unified rate-limit headers on every response:
  anthropic-ratelimit-unified-7d-utilization  → fraction of weekly budget used (0.0–1.0)
  anthropic-ratelimit-unified-7d-reset        → Unix timestamp of weekly reset
  anthropic-ratelimit-unified-5h-utilization  → fraction of 5-hour burst budget used
  anthropic-ratelimit-unified-5h-reset        → Unix timestamp of 5-hour window reset

These are account-wide and authoritative — they reflect usage from all devices,
claude.ai web, and Claude Code sessions, not just local JSONL files.

We make one minimal call per day (8 input + 1 output = 9 tokens cost).
"""

import json
import subprocess
from datetime import datetime, timezone

import requests

_KEYCHAIN_SERVICE = "Claude Code-credentials"
_API_URL = "https://api.anthropic.com/v1/messages"
_MODEL = "claude-haiku-4-5-20251001"


def _get_oauth_token() -> str | None:
    """Read the Claude Code OAuth access token from macOS keychain."""
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", _KEYCHAIN_SERVICE, "-w"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout.strip())
        token = data.get("claudeAiOauth", {}).get("accessToken")
        expires_at = data.get("claudeAiOauth", {}).get("expiresAt", 0)
        now_ms = datetime.now(timezone.utc).timestamp() * 1000
        if expires_at and now_ms > expires_at:
            print("[api_usage] OAuth token expired — skipping")
            return None
        return token
    except Exception as e:
        print(f"[api_usage] Keychain read failed: {e}")
        return None


def fetch_real_usage() -> dict | None:
    """
    Make a 1-token API call and read the account-wide rate-limit headers.

    Returns:
        {
            "utilization_7d": float,          # 0.0–1.0, weekly budget fraction used
            "reset_7d": datetime,             # exact UTC datetime of weekly reset
            "utilization_5h": float | None,   # 0.0–1.0, 5-hour burst fraction used
            "reset_5h": datetime | None,      # exact UTC datetime of 5-hour reset
            "status_7d": str,                 # "allowed" | "rate_limited"
        }
        or None if unavailable.
    """
    token = _get_oauth_token()
    if not token:
        print("[api_usage] No OAuth token — falling back to local JSONL")
        return None

    try:
        r = requests.post(
            _API_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": _MODEL,
                "max_tokens": 1,
                "messages": [{"role": "user", "content": "k"}],
            },
            timeout=10,
        )

        h = r.headers
        util_7d  = h.get("anthropic-ratelimit-unified-7d-utilization")
        reset_7d = h.get("anthropic-ratelimit-unified-7d-reset")
        status   = h.get("anthropic-ratelimit-unified-7d-status", "unknown")
        util_5h  = h.get("anthropic-ratelimit-unified-5h-utilization")
        reset_5h = h.get("anthropic-ratelimit-unified-5h-reset")

        if util_7d is None:
            print(f"[api_usage] No utilization headers (HTTP {r.status_code})")
            return None

        def _ts(v):
            if not v:
                return None
            try:
                return datetime.fromtimestamp(int(v), tz=timezone.utc)
            except (ValueError, OSError):
                return None

        result = {
            "utilization_7d": float(util_7d),
            "reset_7d":       _ts(reset_7d),
            "status_7d":      status,
            "utilization_5h": float(util_5h) if util_5h else None,
            "reset_5h":       _ts(reset_5h),
        }
        print(
            f"[api_usage] 7d utilization={result['utilization_7d']:.1%}  "
            f"reset={result['reset_7d'].strftime('%a %Y-%m-%d %H:%M UTC') if result['reset_7d'] else '?'}"
        )
        return result

    except Exception as e:
        print(f"[api_usage] API call failed: {e}")
        return None
