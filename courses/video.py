"""Signed video playback.

Course videos are the paid product, so they are never linked as a plain file.
Two providers are supported:

* ``cloudflare`` — a short-lived signed playback token is minted per request,
  so a copied URL stops working within the token's lifetime.
* ``protected_file`` — the file sits under ``MEDIA_ROOT``, which is never served
  directly, and is streamed by ``courses.views.protected_video`` after the
  same access check.

The caller must already have confirmed access; this module only builds URLs.

Course trailers are the exception: they are public marketing, so a pasted
YouTube or Cloudflare Stream link is turned into a plain embed URL.
"""

import base64
import json
import re
import time
from urllib.parse import parse_qs, urlsplit

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
        # fall through to the access-checked file stream instead.
    return {
        "kind": "file",
        "src": reverse("courses:video", kwargs={"pk": module.pk}),
        "poster": "",
    }


def playback_json(module):
    data = playback(module)
    return json.dumps(data) if data else "null"


YOUTUBE_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
CLOUDFLARE_UID = re.compile(r"^[0-9a-f]{32}$")
CLOUDFLARE_CUSTOMER_HOST = re.compile(r"^customer-[a-z0-9]+\.cloudflarestream\.com$")
CLOUDFLARE_HOSTS = {
    "iframe.videodelivery.net",
    "videodelivery.net",
    "watch.videodelivery.net",
    "iframe.cloudflarestream.com",
    "watch.cloudflarestream.com",
}
YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "youtube-nocookie.com",
    "www.youtube-nocookie.com",
}


def _youtube_id(host, path, query):
    if host == "youtu.be":
        candidate = path.strip("/").split("/")[0]
    elif host in YOUTUBE_HOSTS:
        parts = path.strip("/").split("/")
        if parts[0] == "watch":
            candidate = parse_qs(query).get("v", [""])[0]
        elif parts[0] in {"embed", "shorts", "live", "v"} and len(parts) > 1:
            candidate = parts[1]
        else:
            return None
    else:
        return None
    return candidate if YOUTUBE_ID.match(candidate) else None


def _cloudflare_embed(host, path):
    uid = path.strip("/").split("/")[0].lower()
    if not CLOUDFLARE_UID.match(uid):
        return None
    if CLOUDFLARE_CUSTOMER_HOST.match(host):
        return f"https://{host}/{uid}/iframe"
    if host in CLOUDFLARE_HOSTS:
        return f"https://iframe.videodelivery.net/{uid}"
    return None


def trailer_embed_url(url):
    """Embed URL for a YouTube or Cloudflare Stream link, or None if neither.

    Accepts the links people copy from either site (watch pages, share links,
    embed URLs) and always rebuilds the URL, so nothing else from the pasted
    text reaches the page. YouTube goes through youtube-nocookie.com, which
    sets no tracking cookies until the visitor presses play.
    """
    if not url:
        return None
    parts = urlsplit(url.strip())
    if parts.scheme not in {"http", "https"}:
        return None
    host = (parts.hostname or "").lower()
    video_id = _youtube_id(host, parts.path, parts.query)
    if video_id:
        return f"https://www.youtube-nocookie.com/embed/{video_id}?rel=0"
    return _cloudflare_embed(host, parts.path)
