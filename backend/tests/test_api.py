from app.seed import DEMO_PASSWORD
from tests.conftest import login


def test_login_and_me(client):
    assert client.get("/api/auth/me").status_code == 401
    r = client.post("/api/auth/login", json={"email": "Support@Deskpilot.test", "password": DEMO_PASSWORD})
    assert r.status_code == 200
    assert (
        "httponly" in r.headers["set-cookie"].lower() and "samesite=strict" in r.headers["set-cookie"].lower()
    )
    me = client.get("/api/auth/me").json()
    assert me["role"] == "support" and "orders.refund" in me["permissions"]


def test_wrong_password_and_rate_limit(client):
    codes = [
        client.post(
            "/api/auth/login", json={"email": "viewer@deskpilot.test", "password": "nope"}
        ).status_code
        for _ in range(11)
    ]
    assert codes[:10] == [401] * 10 and codes[10] == 429


def test_writes_need_csrf_header(client):
    login(client)
    r = client.post("/api/orders/ORD-1001/cancel", json={"reason": "test"}, headers={"X-Requested-With": ""})
    assert r.status_code == 403


def test_rest_writes_follow_the_same_rules(client):
    login(client, "viewer")
    assert client.post("/api/orders/ORD-1002/refund", json={"amount": 5, "reason": "test"}).status_code == 403
    login(client, "support")
    r = client.post("/api/orders/ORD-1002/refund", json={"amount": 80, "reason": "seam"})
    assert r.status_code == 409 and "manager" in r.json()["detail"]
    assert (
        client.post("/api/orders/ORD-1002/refund", json={"amount": "abc", "reason": "x"}).status_code == 422
    )
    assert (
        client.post("/api/orders/ORD-1002/refund", json={"amount": 20, "reason": "seam"}).json()["refunded"]
        == "$20.00"
    )


def test_audit_is_manager_only_and_records_denials(client):
    login(client, "viewer")
    client.post("/api/orders/ORD-1002/refund", json={"amount": 5, "reason": "test"})
    assert client.get("/api/audit").status_code == 403
    login(client, "manager")
    rows = client.get("/api/audit").json()
    assert rows[0]["action"] == "refund_order" and rows[0]["outcome"] == "denied"
    assert rows[0]["user"] == "Vera Viewer" and rows[0]["via_assistant"] is False


def test_stats_and_lists(client):
    login(client, "viewer")
    stats = client.get("/api/stats").json()
    assert sum(stats["orders"].values()) == 40 and stats["tickets"]["open"] == 3
    assert len(client.get("/api/orders?status=pending").json()) >= 2
    assert client.get("/api/orders/ORD-9999").status_code == 404


def test_logout(client):
    login(client)
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_security_headers(client):
    r = client.get("/api/health")
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"


def test_voice_is_off_by_default(client):
    login(client, "viewer")
    assert client.get("/api/voice").json() == {"enabled": False, "speak_languages": []}
    assert client.post("/api/voice/speak", json={"text": "hi"}).status_code == 503
