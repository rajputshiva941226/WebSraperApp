"""
user_agents.py — Shared random User-Agent loader for all scrapers.

Reads db-1.txt (6,718 real browser UAs) from the same directory as this file.
Used by chrome_display_mixin.py and sciencedirect/index.cjs.

Usage:
    from user_agents import get_random_ua, get_desktop_ua
    ua = get_random_ua()          # any UA from the file
    ua = get_desktop_ua()         # desktop-only (no Mobile/Android/iPhone)
"""

import os
import random
from typing import List

_UA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "db-1.txt")

# Cache loaded at first import
_ALL_UAS:     List[str] = []
_DESKTOP_UAS: List[str] = []


def _load():
    global _ALL_UAS, _DESKTOP_UAS
    if _ALL_UAS:
        return
    try:
        with open(_UA_FILE, encoding="utf-8", errors="ignore") as f:
            lines = [l.strip() for l in f if l.strip()]
        _ALL_UAS = lines
        # Desktop = no Mobile/Android/iPhone/iPad keywords
        _DESKTOP_UAS = [
            ua for ua in lines
            if not any(m in ua for m in ("Mobile", "Android", "iPhone", "iPad", "UCBrowser"))
            and "Windows" in ua or "Macintosh" in ua or "X11" in ua
        ]
        if not _DESKTOP_UAS:
            _DESKTOP_UAS = _ALL_UAS
    except Exception:
        # Fallback if file missing
        _ALL_UAS = [
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        ]
        _DESKTOP_UAS = _ALL_UAS


def get_random_ua() -> str:
    """Return a random UA from db-1.txt."""
    _load()
    return random.choice(_ALL_UAS)


def get_desktop_ua() -> str:
    """
    Return a random desktop (non-mobile) UA.
    Preferred for Selenium scrapers — mobile UAs can trigger different site layouts.
    """
    _load()
    return random.choice(_DESKTOP_UAS)


def get_all_uas() -> List[str]:
    """Return the full list (for Node.js JSON embed)."""
    _load()
    return list(_ALL_UAS)