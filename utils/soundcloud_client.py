from __future__ import annotations

import base64
import time
from typing import Any, Dict, List, Optional

import aiohttp

from config import (
    SOUNDCLOUD_CLIENT_ID,
    SOUNDCLOUD_CLIENT_SECRET,
    SOUNDCLOUD_API_BASE,
    SOUNDCLOUD_OAUTH_URL,
)


class SoundCloudClient:
    def __init__(self) -> None:
        self.client_id = SOUNDCLOUD_CLIENT_ID
        self.client_secret = SOUNDCLOUD_CLIENT_SECRET
        self.api_base = SOUNDCLOUD_API_BASE.rstrip("/")
        self.oauth_url = SOUNDCLOUD_OAUTH_URL
        self._token: Optional[str] = None
        self._expires_at: float = 0.0

    def enabled(self) -> bool:
        return bool(self.client_id and self.client_secret)

    async def _get_token(self) -> str:
        now = time.monotonic()
        if self._token and now < self._expires_at:
            return self._token
        if not self.enabled():
            raise RuntimeError("SoundCloud client is not configured")

        basic = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode("utf-8")).decode("ascii")
        headers = {
            "Authorization": f"Basic {basic}",
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {"grant_type": "client_credentials"}
        async with aiohttp.ClientSession() as session:
            async with session.post(self.oauth_url, data=data, headers=headers) as resp:
                if resp.status >= 400:
                    text = await resp.text()
                    raise RuntimeError(f"SoundCloud auth failed: {resp.status} {text}")
                payload = await resp.json()
        token = payload.get("access_token")
        if not token:
            raise RuntimeError("SoundCloud auth failed: missing access_token")
        expires_in = int(payload.get("expires_in") or 3600)
        # Refresh a minute early to avoid expiry during playback
        self._expires_at = time.monotonic() + max(60, expires_in - 60)
        self._token = token
        return token

    async def _api_get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        token = await self._get_token()
        headers = {"Authorization": f"OAuth {token}", "Accept": "application/json"}
        url = f"{self.api_base}{path}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=headers) as resp:
                if resp.status >= 400:
                    text = await resp.text()
                    raise RuntimeError(f"SoundCloud API error: {resp.status} {text}")
                return await resp.json()

    async def resolve_url(self, url: str) -> Dict[str, Any]:
        return await self._api_get("/resolve", params={"url": url})

    async def search_tracks(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        params = {"q": query, "limit": limit, "access": "playable"}
        data = await self._api_get("/tracks", params=params)
        if isinstance(data, dict) and "collection" in data:
            return data["collection"]
        if isinstance(data, list):
            return data
        return []

    async def resolve_stream_url(self, track: Dict[str, Any]) -> str:
        token = await self._get_token()
        headers = {"Authorization": f"OAuth {token}", "Accept": "application/json"}

        media = track.get("media") or {}
        transcodings = media.get("transcodings") or []
        for transcoding in transcodings:
            fmt = transcoding.get("format") or {}
            if fmt.get("protocol") == "progressive":
                url = transcoding.get("url")
                if url:
                    return await self._fetch_transcoding_url(url, headers)
        if transcodings:
            url = transcodings[0].get("url")
            if url:
                return await self._fetch_transcoding_url(url, headers)

        stream_url = track.get("stream_url")
        if stream_url:
            return await self._follow_stream_url(stream_url, headers)

        raise RuntimeError("SoundCloud track has no stream URL")

    async def _fetch_transcoding_url(self, url: str, headers: Dict[str, str]) -> str:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status >= 400:
                    text = await resp.text()
                    raise RuntimeError(f"SoundCloud stream error: {resp.status} {text}")
                data = await resp.json()
        final_url = data.get("url") or data.get("location")
        if not final_url:
            raise RuntimeError("SoundCloud stream error: missing url")
        return final_url

    async def _follow_stream_url(self, url: str, headers: Dict[str, str]) -> str:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, allow_redirects=True) as resp:
                if resp.status >= 400:
                    text = await resp.text()
                    raise RuntimeError(f"SoundCloud stream error: {resp.status} {text}")
                if resp.content_type == "application/json":
                    data = await resp.json()
                    final_url = data.get("url") or data.get("location")
                    if final_url:
                        return final_url
                return str(resp.url)
