"""Smoke tests for decommissioned legacy board UI surfaces."""
from datetime import datetime, timedelta

import pytest


@pytest.fixture()
def app(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "testing")
    from app import create_app
    from app.extensions import db

    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def _user(username="mgr", role="management"):
    from app.extensions import db
    from app.models import User

    user = User(username=username, email=f"{username}@example.com", role=role)
    user.set_password("password1")
    db.session.add(user)
    db.session.commit()
    return user


def _login(client, username):
    return client.post(
        "/login",
        data={"login_name": username, "password": "password1"},
        follow_redirects=False,
    )


def _move_request(creator_id, **kw):
    from app.extensions import db
    from app.models import MoveRequest

    base = dict(
        raw_text="Move rack from Raleigh East to Paint Central",
        created_by_id=creator_id,
        status="open",
        priority="high",
        origin_location_text="Raleigh East",
        destination_location_text="Paint Central",
        cargo_text="Rack load",
        request_number="MR-DECOM-1",
        requested_at=datetime.utcnow() - timedelta(minutes=10),
    )
    base.update(kw)
    req = MoveRequest(**base)
    db.session.add(req)
    db.session.commit()
    return req


def test_manager_workspace_does_not_embed_legacy_board_component(client, app):
    with app.app_context():
        manager = _user("boss", "management")
        _move_request(manager.id)

    _login(client, "boss")
    resp = client.get("/manager/dashboard")

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Manager Workspace" in body
    assert "MR-DECOM-1" in body
    assert "Live Flow Map" not in body
    assert 'data-component="FlowMapDashboard"' not in body
    assert 'data-route-map-mode="production"' not in body


def test_legacy_operations_board_redirects_by_role(client, app):
    with app.app_context():
        _user("ops-boss", "management")
        _user("ops-driver", "driver")

    _login(client, "ops-boss")
    manager_resp = client.get("/operations-board", follow_redirects=False)
    assert manager_resp.status_code == 302
    assert manager_resp.headers["Location"].endswith("/manager/dashboard")

    client.get("/logout")
    _login(client, "ops-driver")
    driver_resp = client.get("/operations_board", follow_redirects=False)
    assert driver_resp.status_code == 302
    assert driver_resp.headers["Location"].endswith("/mobile")


def test_removed_board_urls_and_mobile_fragment_do_not_render(client, app):
    with app.app_context():
        _user("board-driver", "driver")

    _login(client, "board-driver")

    assert client.get("/production-flow-board").status_code == 404
    assert client.get("/production_flow_board").status_code == 404
    assert client.get("/mobile/production-flow-fragment").status_code == 404
