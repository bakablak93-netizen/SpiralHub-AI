# -*- coding: utf-8 -*-
"""Локализация UI: ru / kk / en. Строки в locales/<lang>.json."""
from __future__ import annotations

import json
import os
from typing import Any

SUPPORTED_LOCALES = ("ru", "kk", "en")
_DEFAULT_LANG = "ru"
_BASE = os.path.dirname(os.path.abspath(__file__))
_LOCALES_DIR = os.path.join(_BASE, "locales")
_cache: dict[str, dict[str, str]] = {}


def _load_file(lang: str) -> dict[str, str]:
    if lang in _cache:
        return _cache[lang]
    path = os.path.join(_LOCALES_DIR, f"{lang}.json")
    data: dict[str, str] = {}
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
            if isinstance(raw, dict):
                data = {str(k): v for k, v in raw.items() if isinstance(v, str)}
    except (OSError, json.JSONDecodeError):
        data = {}
    pages_path = os.path.join(_LOCALES_DIR, f"pages_{lang}.json")
    try:
        with open(pages_path, encoding="utf-8") as f:
            extra = json.load(f)
            if isinstance(extra, dict):
                for k, v in extra.items():
                    if isinstance(v, str):
                        data[str(k)] = v
    except (OSError, json.JSONDecodeError):
        pass
    _cache[lang] = data
    return data


def normalize_locale(lang: str | None) -> str:
    if not lang:
        return _DEFAULT_LANG
    code = str(lang).lower().strip().split("-")[0]
    return code if code in SUPPORTED_LOCALES else _DEFAULT_LANG


def translate(lang: str | None, key: str, **kwargs: Any) -> str:
    """Строка по ключу; подстановка {name} из kwargs."""
    loc = normalize_locale(lang)
    bundle = _load_file(loc)
    s = bundle.get(key)
    if s is None and loc != _DEFAULT_LANG:
        s = _load_file(_DEFAULT_LANG).get(key)
    if s is None:
        s = key
    if kwargs:
        try:
            s = s.format(**kwargs)
        except (KeyError, ValueError):
            pass
    return s


def default_user_prefs() -> dict[str, Any]:
    return {
        "theme": "light",
        "font_scale": "md",
        "currency": "KZT",
        "notif_push": True,
        "notif_email": True,
        "notif_sms": False,
        "notif_products": True,
        "notif_promo": True,
        "notif_sellers": True,
        "privacy_analytics": True,
        "privacy_personalized": True,
        "two_factor": False,
    }


def merged_prefs(session_prefs: dict | None) -> dict[str, Any]:
    base = default_user_prefs()
    if not session_prefs:
        return base
    for k, v in session_prefs.items():
        if k in base:
            base[k] = v
    return base


def clear_locale_cache() -> None:
    _cache.clear()
