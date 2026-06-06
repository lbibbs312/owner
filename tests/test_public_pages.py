import re

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


def _visible_text(html):
    html = re.sub(r"<style\b[^>]*>.*?</style>", " ", html, flags=re.I | re.S)
    html = re.sub(r"<script\b[^>]*>.*?</script>", " ", html, flags=re.I | re.S)
    html = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", html).strip()


def test_welcome_page_positions_packets_and_pricing(client):
    response = client.get("/")

    assert response.status_code == 200
    text = _visible_text(response.get_data(as_text=True))

    assert "Turn driver paperwork into clean route, incident, and IFTA support packets." in text
    assert "We help owner-operators and small fleets" in text
    assert "Preview packets" in text
    assert "Start free" in text
    assert "Set up small fleet" in text
    assert "Free Preview" in text
    assert "Solo Driver" in text
    assert "Owner-Operator" in text
    assert "Small Fleet" in text
    assert "Fleet Office" in text
    assert "Includes up to 5 drivers or vehicles" in text
    assert "$15/month per extra driver or vehicle" in text
    assert "MoveDefense Paperwork Cleanup" in text
    assert "starting at $299/month" in text


def test_welcome_page_uses_safe_product_language(client):
    response = client.get("/")

    assert response.status_code == 200
    text = _visible_text(response.get_data(as_text=True))
    lower_text = text.lower()

    assert "MoveDefense" in text
    assert re.search(r"\bwe\b", lower_text)
    assert re.search(r"\bour\b", lower_text)
    assert not re.search(r"\b(i|my|me)\b", lower_text)
    for banned in (
        "critical",
        "exception",
        "gap",
        "warning",
        "FCSMA",
        "DOT approved",
        "FMCSA certified",
        "guaranteed compliant",
    ):
        assert banned.lower() not in lower_text
    assert "FMCSA-aligned" in text
    assert "DOT-ready recordkeeping" in text
    assert "insurance-ready packet" in lower_text
    assert "IFTA support worksheet" in text
