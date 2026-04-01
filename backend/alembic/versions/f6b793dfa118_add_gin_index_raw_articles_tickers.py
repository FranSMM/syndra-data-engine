"""add_gin_index_raw_articles_tickers

Revision ID: f6b793dfa118
Revises: d08e16e8528a
Create Date: 2026-03-27 00:04:02.684815

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f6b793dfa118'
down_revision: Union[str, None] = 'd08e16e8528a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.execute("""
        CREATE INDEX ix_raw_articles_tickers 
        ON raw_articles 
        USING GIN ((payload -> 'financial_metadata' -> 'tickers'));
    """)

def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_raw_articles_tickers;")