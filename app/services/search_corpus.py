import math
import re
from datetime import datetime

from sqlalchemy import text

from app.extensions import db
from app.models import DriverLog, SearchCorpus, User
from app.services.load_state import cargo_display
from app.services.plant_addresses import plant_label

TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9#._/-]{1,}")
DECAY = 0.045


def normalize_term(value):
    return " ".join((value or "").strip().lower().split())


def _context_for_log(log):
    return f"plant:{log.plant_name}" if getattr(log, "plant_name", None) else None


def _upsert_term(category, term, context_key=None, used_at=None):
    term = (term or "").strip()
    normalized = normalize_term(term)
    if not normalized or len(normalized) < 2:
        return None
    used_at = used_at or datetime.utcnow()
    row = SearchCorpus.query.filter_by(
        category=category,
        normalized_term=normalized,
        context_key=context_key,
    ).first()
    if row:
        row.frequency += 1
        row.last_used_at = used_at
        row.term = term
    else:
        row = SearchCorpus(
            category=category,
            term=term,
            normalized_term=normalized,
            context_key=context_key,
            frequency=1,
            last_used_at=used_at,
        )
        db.session.add(row)
        db.session.flush()
    _sync_fts_row(row)
    return row


def _sync_fts_row(row):
    if db.session.bind and db.session.bind.dialect.name == "sqlite":
        exists = db.session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='search_corpus_fts'")
        ).first()
        if not exists:
            return
    try:
        db.session.execute(
            text(
                "INSERT OR REPLACE INTO search_corpus_fts(rowid, term, category, context_key) "
                "VALUES (:id, :term, :category, :context_key)"
            ),
            {
                "id": row.id,
                "term": row.term,
                "category": row.category,
                "context_key": row.context_key or "",
            },
        )
    except Exception:
        return


def _terms_from_text(value):
    cleaned = (value or "").strip()
    if not cleaned:
        return []
    terms = [cleaned]
    for token in TOKEN_RE.findall(cleaned):
        if len(token) >= 3:
            terms.append(token.upper() if any(ch.isdigit() for ch in token) else token)
    seen = set()
    unique = []
    for term in terms:
        key = normalize_term(term)
        if key not in seen:
            seen.add(key)
            unique.append(term)
    return unique


def ingest_driver_log(log, commit=False):
    if not log:
        return
    used_at = log.created_at or datetime.utcnow()
    context = _context_for_log(log)
    driver = getattr(log, "driver", None) or User.query.get(log.driver_id)

    _upsert_term("plant", log.plant_name, context, used_at)
    _upsert_term("plant", plant_label(log.plant_name), context, used_at)
    if driver:
        _upsert_term("driver", driver.display_name, context, used_at)
        _upsert_term("driver", driver.username, context, used_at)
        if driver.employee_id:
            _upsert_term("driver", driver.employee_id, context, used_at)

    for load in [log.load_size, log.depart_load_size, log.secondary_load]:
        if load:
            _upsert_term("cargo_type", load, context, used_at)
    cargo = cargo_display(log.depart_load_size or log.load_size, log.secondary_load)
    if cargo and cargo != "Empty":
        _upsert_term("cargo_type", cargo, context, used_at)

    for term in _terms_from_text(log.part_number):
        _upsert_term("part_number", term, context, used_at)

    if commit:
        db.session.commit()


def ensure_search_corpus_seeded():
    if SearchCorpus.query.first():
        return
    for log in DriverLog.query.filter(DriverLog.deleted_at.is_(None)).order_by(DriverLog.created_at.asc()).all():
        ingest_driver_log(log, commit=False)
    db.session.commit()


def _fts_row_ids(query):
    normalized = normalize_term(query)
    if not normalized:
        return []
    match = " ".join(f"{part}*" for part in normalized.split())
    try:
        rows = db.session.execute(
            text("SELECT rowid FROM search_corpus_fts WHERE search_corpus_fts MATCH :match LIMIT 50"),
            {"match": match},
        ).fetchall()
        return [row[0] for row in rows]
    except Exception:
        db.session.rollback()
        return []


def suggest_terms(query, *, context_key=None, limit=10):
    ensure_search_corpus_seeded()
    normalized = normalize_term(query)
    if not normalized:
        return []

    row_ids = _fts_row_ids(normalized)
    q = SearchCorpus.query
    if row_ids:
        q = q.filter(SearchCorpus.id.in_(row_ids))
    else:
        like = f"%{normalized}%"
        q = q.filter(SearchCorpus.normalized_term.like(like))
    rows = q.order_by(SearchCorpus.last_used_at.desc()).limit(80).all()

    now = datetime.utcnow()
    scored = []
    for row in rows:
        days = max((now - row.last_used_at).total_seconds() / 86400, 0)
        score = row.frequency * math.exp(-DECAY * days)
        if row.normalized_term.startswith(normalized):
            score *= 1.8
        if context_key and row.context_key == context_key:
            score *= 1.35
        scored.append((score, row))

    scored.sort(key=lambda item: item[0], reverse=True)
    results = []
    seen = set()
    for score, row in scored:
        key = (row.category, row.normalized_term)
        if key in seen:
            continue
        seen.add(key)
        results.append({
            "term": row.term,
            "category": row.category,
            "frequency": row.frequency,
            "context": row.context_key,
            "score": round(score, 3),
        })
        if len(results) >= limit:
            break
    return results
