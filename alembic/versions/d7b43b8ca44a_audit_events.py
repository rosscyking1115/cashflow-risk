"""audit_events

Revision ID: d7b43b8ca44a
Revises: 231699b88165
Create Date: 2026-07-02 13:12:04.385727

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd7b43b8ca44a'
down_revision: Union[str, Sequence[str], None] = '231699b88165'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'audit_events',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('business_id', sa.String(), nullable=False),
        sa.Column('actor_user_id', sa.String(), nullable=False),
        sa.Column('action', sa.String(), nullable=False),
        sa.Column('detail', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['business_id'], ['businesses.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_audit_events_business_id'), 'audit_events', ['business_id'], unique=False
    )
    op.create_index(
        op.f('ix_audit_events_created_at'), 'audit_events', ['created_at'], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_audit_events_created_at'), table_name='audit_events')
    op.drop_index(op.f('ix_audit_events_business_id'), table_name='audit_events')
    op.drop_table('audit_events')
