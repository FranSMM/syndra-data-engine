"""create silver articles table

Revision ID: a1b2c3d4e5f6
Revises: f6b793dfa118
Create Date: 2026-04-10 03:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'f6b793dfa118'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('articles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('raw_article_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('published_at', sa.DateTime(), nullable=True),
        sa.Column('sentiment_label', sa.String(length=20), nullable=True),
        sa.Column('sentiment_score', sa.Float(), nullable=True),
        sa.Column('tickers', sa.ARRAY(sa.String()), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['raw_article_id'], ['raw_articles.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_articles_id'), 'articles', ['id'], unique=False)
    op.create_index(op.f('ix_articles_raw_article_id'), 'articles', ['raw_article_id'], unique=True)
    op.create_index(op.f('ix_articles_published_at'), 'articles', ['published_at'], unique=False)
    op.create_index(op.f('ix_articles_sentiment_label'), 'articles', ['sentiment_label'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_articles_sentiment_label'), table_name='articles')
    op.drop_index(op.f('ix_articles_published_at'), table_name='articles')
    op.drop_index(op.f('ix_articles_raw_article_id'), table_name='articles')
    op.drop_index(op.f('ix_articles_id'), table_name='articles')
    op.drop_table('articles')
