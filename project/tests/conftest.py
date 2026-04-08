# -*- coding: utf-8 -*-
import os
import tempfile

import pytest

from app import create_app, db


@pytest.fixture
def app():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        app = create_app(
            {
                "TESTING": True,
                "SQLALCHEMY_DATABASE_URI": f"sqlite:///{path}",
                "WTF_CSRF_ENABLED": False,
                "SECRET_KEY": "test-secret-key",
            }
        )
        with app.app_context():
            db.create_all()
        yield app
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


@pytest.fixture
def client(app):
    return app.test_client()
