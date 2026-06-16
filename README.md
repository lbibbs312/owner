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

## Cloudflare R2 deploy-fallback

MoveDefense uses a Cloudflare Worker plus R2 bucket to avoid showing Render
gateway errors during deploys. The Worker proxies normal traffic to Render,
snapshots only public app-shell files into R2, and serves the last good shell
when Render returns `502`, `503`, `504`, `522`, `523`, or `524`.

Cloudflare DNS for `movedefense.com` should use a proxied apex `CNAME` to the
Render hostname (`lacksdrivers-com.onrender.com`) so Workers routes fire on the
root domain. `www.movedefense.com` should also be proxied and covered by the
Worker route.

No Cloudflare token belongs in this repo. Set it only in your shell or CI:

```bash
export CLOUDFLARE_API_TOKEN="..."
npm exec --yes wrangler r2 bucket create movedefense-app-shell
npm exec --yes wrangler deploy --config wrangler.toml
scripts/warm_r2_fallback.sh
```

If your existing R2 bucket has a different name, update `bucket_name` in
`wrangler.toml` before deploying. After any token has been pasted into chat or
logs, revoke it in Cloudflare and create a new scoped token before production
use.
