from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_cloudflare_worker_snapshots_public_shell_only():
    worker = (ROOT / "cloudflare" / "movedefense-r2-fallback-worker.js").read_text()
    wrangler = (ROOT / "wrangler.toml").read_text()
    warmup = (ROOT / "scripts" / "warm_r2_fallback.sh").read_text()
    combined = worker + wrangler + warmup

    assert "MD_R2_FALLBACK" in combined
    assert "movedefense-app-shell" in wrangler
    assert "movedefense.com/*" in wrangler
    assert "746191c2d2bef207e6254e4ba80e95da" in wrangler
    for status in ("502", "503", "504", "522", "523", "524"):
        assert status in worker
    assert 'url.pathname.startsWith("/api/")' in worker
    assert 'response.headers.has("set-cookie")' in worker
    assert "readSnapshot(bucket, key, request)) || updatingResponse(key)" in worker
    assert "/?source=r2-warm" in warmup
    assert "/sw.js" in warmup
    assert "cfat_" not in combined
