"""Signed video playback.

Course videos are the paid product, so they are never linked as a plain file.
Two providers are supported:

* ``cloudflare`` — a short-lived signed playback token is minted per request,
  so a copied URL stops working within the token's lifetime.
* ``protected_file`` — the file sits outside ``MEDIA_ROOT`` and is streamed by
  ``courses.views.protected_video`` after the same access check.

The caller must already have confirmed access; this module only builds URLs.
"""

import base64
import json
import time

from django.conf import settings
from django.urls import reverse


def _cloudflare_token(video_uid):
    """Mint a Cloudflare Stream signed token, or None when unconfigured."""
    config = settings.CLOUDFLARE_STREAM
    key_id = config.get("signing_key_id")
    key_pem = config.get("signing_key_pem")
    if not (key_id and key_pem):
        return None
    try:
        import jwt  # PyJWT, only needed when Cloudflare signing is configured
    except ImportError:  # pragma: no cover - optional dependency
        return None
    now = int(time.time())
    payload = {
        "sub": video_uid,
        "kid": key_id,
        "exp": now + int(config.get("token_ttl_seconds", 7200)),
        "nbf": now - 60,
        "downloadable": False,
    }
    private_key = base64.b64decode(key_pem) if "-----" not in key_pem else key_pem.encode()
    return jwt.encode(payload, private_key, algorithm="RS256", headers={"kid": key_id})


def playback(module):
    """Return ``{"kind", "src", "poster"}`` for a module, or None if no video."""
    if not module.video_uid:
        return None
    if module.video_provider == "cloudflare":
        token = _cloudflare_token(module.video_uid)
        if token:
            return {
                "kind": "iframe",
                "src": f"https://iframe.videodelivery.net/{token}",
                "poster": "",
            }
        # Unsigned Cloudflare playback would expose the video publicly, so
        # fall through to the protected-file stream instead.
    return {
        "kind": "file",
        "src": reverse("courses:video", kwargs={"pk": module.pk}),
        "poster": "",
    }


def playback_json(module):
    data = playback(module)
    return json.dumps(data) if data else "null"
