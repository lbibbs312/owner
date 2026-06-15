import pytest


@pytest.fixture()
def app(monkeypatch, tmp_path):
    monkeypatch.setenv("FLASK_ENV", "testing")
    from app import create_app
    from app.extensions import db

    app = create_app()
    app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        DAMAGE_UPLOAD_FOLDER=str(tmp_path / "damage_uploads"),
        DRIVER_LOG_PHOTO_UPLOAD_FOLDER=str(tmp_path / "driver_log_photo_uploads"),
    )
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def test_welcome_page_serves_local_first_driver_logger(client):
    response = client.get("/")

    assert response.status_code == 200
    page = response.data.decode()
    assert "Driver Activity Log" in page
    assert "Create account" in page
    assert "Login with Google" in page
    assert "Record first stop" in page
    assert "Offline ready" in page
    assert "MoveDefense Operations" not in page
    assert "Manager Dispatch" not in page
