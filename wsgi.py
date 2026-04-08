# -*- coding: utf-8 -*-
"""Точка входа WSGI из корня репозитория (Amvera ищет модуль здесь, без --chdir)."""
from __future__ import annotations

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
_project = os.path.join(_root, "project")
if _project not in sys.path:
    sys.path.insert(0, _project)

from app import app  # noqa: E402

__all__ = ["app"]
