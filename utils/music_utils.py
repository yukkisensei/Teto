from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse, unquote

URL_RE = re.compile(r"^https?://")


@dataclass
class Track:
    title: str
    url: str
    video_id: str
    filepath: str
    duration: Optional[int]


def is_url(query: str) -> bool:
    return bool(URL_RE.match(query))


def _guess_title(url: str) -> str:
    parsed = urlparse(url)
    name = parsed.path.rsplit("/", 1)[-1]
    if name:
        return unquote(name)
    if parsed.netloc:
        return parsed.netloc
    return "Stream"


def build_track_from_url(url: str) -> Track:
    title = _guess_title(url)
    return Track(title=title, url=url, video_id=url, filepath=url, duration=None)
