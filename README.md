# MoveDefense

Driver dispatch, pre-trip / post-trip inspection, shift logging, and team
messaging for the MoveDefense fleet.

## Quick start (local dev)

```bash
python -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

cp .env.example .env                # then edit .env to set SECRET_KEY etc.

flask --app lacksdrivers db upgrade
python lacksdrivers.py
```

The dev server listens on `http://127.0.0.1:5000`.

## Configuration

All runtime configuration is loaded from environment variables. See
`.env.example` for the full list. The most important ones:

| Variable | Required? | Notes |
| --- | --- | --- |
| `SECRET_KEY` | yes in any deployment | Long random string |
| `SQLALCHEMY_DATABASE_URI` | no | Defaults to local SQLite |
| `FLASK_DEBUG` | no | Default `false` |
| `SESSION_COOKIE_SECURE` | yes over HTTPS | Default `false` for local HTTP |
| `ENABLE_SOCKETIO` | no | Default `false` in production/Render; keep disabled unless the hosted worker is socket-safe |
| `MANAGER_REGISTRATION_PIN` | no | Unset disables manager self-registration |

## Development

```bash
ruff check .
mypy .
pytest
```
