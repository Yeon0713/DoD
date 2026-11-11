"""drop store dayparts

시간대(점심·저녁·야간)는 서버가 정한다. DB 매장 정보에는 절대 시각(영업시간, 알림 시각)만 둔다.

Revision ID: b7d3e1f0c2a4
Revises: a62b412aa231
Create Date: 2026-11-11 00:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b7d3e1f0c2a4'
down_revision: Union[str, Sequence[str], None] = 'a62b412aa231'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_column('store', 'dayparts')
    op.drop_column('store', 'busy_dayparts')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('store', sa.Column('busy_dayparts', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='[]'))
    op.add_column('store', sa.Column('dayparts', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='[]'))
