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


def test_purchase_history_redirects_when_guest(client):
    r = client.get("/purchase_history")
    assert r.status_code in (302, 303)
    assert "login" in (r.headers.get("Location") or "").lower()


def test_purchase_history_ok_for_logged_in_buyer(client):
    client.post(
        "/register",
        data={
            "email": "buyer_hist@test.local",
            "password": "secret12",
            "role": "buyer",
            "display_name": "Buyer",
        },
        follow_redirects=True,
    )
    r = client.get("/purchase_history")
    assert r.status_code == 200
    assert "История покупок" in r.get_data(as_text=True)
