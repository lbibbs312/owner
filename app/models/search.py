from datetime import datetime

from app.extensions import db


class SearchCorpus(db.Model):
    __tablename__ = "search_corpus"
    __table_args__ = (
        db.UniqueConstraint("category", "normalized_term", "context_key", name="uq_search_corpus_term_context"),
    )

    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(40), nullable=False, index=True)
    term = db.Column(db.String(160), nullable=False)
    normalized_term = db.Column(db.String(160), nullable=False, index=True)
    context_key = db.Column(db.String(120), nullable=True, index=True)
    frequency = db.Column(db.Integer, nullable=False, default=1)
    last_used_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
