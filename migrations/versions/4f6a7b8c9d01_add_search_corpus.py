"""add search corpus

Revision ID: 4f6a7b8c9d01
Revises: 3adc4fb15abb
Create Date: 2026-05-16 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "4f6a7b8c9d01"
down_revision = "3adc4fb15abb"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "search_corpus",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("term", sa.String(length=160), nullable=False),
        sa.Column("normalized_term", sa.String(length=160), nullable=False),
        sa.Column("context_key", sa.String(length=120), nullable=True),
        sa.Column("frequency", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("last_used_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_search_corpus_category", "search_corpus", ["category"])
    op.create_index("ix_search_corpus_context_key", "search_corpus", ["context_key"])
    op.create_index("ix_search_corpus_last_used_at", "search_corpus", ["last_used_at"])
    op.create_index("ix_search_corpus_normalized_term", "search_corpus", ["normalized_term"])
    op.create_index(
        "uq_search_corpus_term_context",
        "search_corpus",
        ["category", "normalized_term", "context_key"],
        unique=True,
    )
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS search_corpus_fts "
            "USING fts5(term, category UNINDEXED, context_key UNINDEXED, content='search_corpus', content_rowid='id')"
        )


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute("DROP TABLE IF EXISTS search_corpus_fts")
    op.drop_index("uq_search_corpus_term_context", table_name="search_corpus")
    op.drop_index("ix_search_corpus_normalized_term", table_name="search_corpus")
    op.drop_index("ix_search_corpus_last_used_at", table_name="search_corpus")
    op.drop_index("ix_search_corpus_context_key", table_name="search_corpus")
    op.drop_index("ix_search_corpus_category", table_name="search_corpus")
    op.drop_table("search_corpus")
