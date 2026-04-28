"""
Fetch latest stable Chrome versions for Android from Google's public API.
Caches results to a local file (TTL 24 hours).

Usage:
    from chrome_versions import get_chrome_versions
    versions = get_chrome_versions()  # e.g. ["137.0.7151.104", "136.0.7103.125", ...]
"""

from __future__ import annotations

import json
import time
import logging
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

CACHE_FILE = Path(__file__).parent / 'chrome_versions_cache.json'
CACHE_TTL = 86400  # 24 hours

API_URL = (
    'https://versionhistory.googleapis.com/v1/chrome/platforms/android'
    '/channels/stable/versions?pageSize=200'
)

# Fallback: keep reasonably recent versions if API is unreachable
FALLBACK_VERSIONS = [
    "133.0.6917.132", "132.0.6834.163", "131.0.6778.135",
    "130.0.6723.107", "129.0.6668.100", "128.0.6613.127",
    "127.0.6533.103", "126.0.6478.122", "125.0.6422.165",
    "124.0.6367.179", "123.0.6312.118", "122.0.6261.119",
]

NUM_VERSIONS = 12  # how many major versions to keep


def _fetch_from_api() -> list[str]:
    """Fetch versions from Google VersionHistory API."""
    req = urllib.request.Request(API_URL, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode())

    # Group by major version, take latest patch for each
    major_map: dict[int, str] = {}
    for entry in data.get('versions', []):
        ver = entry.get('version', '')
        parts = ver.split('.')
        if len(parts) != 4:
            continue
        major = int(parts[0])
        if major not in major_map:
            major_map[major] = ver

    # Sort descending by major, take last NUM_VERSIONS
    sorted_majors = sorted(major_map.keys(), reverse=True)[:NUM_VERSIONS]
    return [major_map[m] for m in sorted_majors]


def _load_cache() -> list[str] | None:
    """Load cached versions if not expired."""
    if not CACHE_FILE.exists():
        return None
    try:
        data = json.loads(CACHE_FILE.read_text(encoding='utf-8'))
        if time.time() - data.get('ts', 0) < CACHE_TTL:
            return data.get('versions', [])
    except (json.JSONDecodeError, KeyError):
        pass
    return None


def _save_cache(versions: list[str]) -> None:
    """Save versions to cache file."""
    try:
        CACHE_FILE.write_text(
            json.dumps({'ts': time.time(), 'versions': versions}),
            encoding='utf-8',
        )
    except OSError as e:
        logger.warning(f"Cannot save chrome versions cache: {e}")


def get_chrome_versions() -> list[str]:
    """
    Return list of latest stable Chrome version strings for Android.
    Uses cache (24h TTL), falls back to hardcoded list if API is down.
    """
    cached = _load_cache()
    if cached:
        return cached

    try:
        versions = _fetch_from_api()
        if versions:
            _save_cache(versions)
            logger.info(f"Chrome versions updated: {versions[0]} ... {versions[-1]} ({len(versions)} total)")
            return versions
    except Exception as e:
        logger.warning(f"Cannot fetch Chrome versions from API: {e}, using fallback")

    return FALLBACK_VERSIONS
