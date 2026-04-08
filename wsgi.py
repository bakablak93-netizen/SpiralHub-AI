# -*- coding: utf-8 -*-
"""Точка входа WSGI из корня репозитория (Amvera ищет модуль здесь, без --chdir)."""
from __future__ import annotations

import json
import os
import sys
import time

_root = os.path.dirname(os.path.abspath(__file__))
_project = os.path.join(_root, "project")
if _project not in sys.path:
    sys.path.insert(0, _project)

from app import app  # noqa: E402

# #region agent log
try:
    _log = os.path.join(_root, "debug-88bfc6.log")
    with open(_log, "a", encoding="utf-8") as _f:
        _f.write(
            json.dumps(
                {
                    "sessionId": "88bfc6",
                    "runId": "local-import",
                    "hypothesisId": "A",
                    "location": "wsgi.py:post-import",
                    "message": "wsgi loaded app",
                    "data": {"project_dir": _project, "has_app_py": os.path.isfile(os.path.join(_project, "app.py"))},
                    "timestamp": int(time.time() * 1000),
                },
                ensure_ascii=False,
            )
            + "\n"
        )
except OSError:
    pass
# #endregion

__all__ = ["app"]
