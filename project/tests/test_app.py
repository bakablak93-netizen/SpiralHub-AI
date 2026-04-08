# -*- coding: utf-8 -*-
def test_index_ok(client):
    r = client.get("/")
    assert r.status_code == 200


def test_catalog_ok(client):
    r = client.get("/catalog")
    assert r.status_code == 200


def test_login_page_ok(client):
    r = client.get("/login")
    assert r.status_code == 200


def test_set_locale_json(client):
    r = client.post(
        "/settings/lang",
        json={"lang": "en"},
        headers={"Accept": "application/json", "Content-Type": "application/json"},
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data.get("ok") is True
    assert data.get("locale") == "en"
