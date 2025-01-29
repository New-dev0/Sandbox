"""Initial migration

Revision ID: 001
Revises: 
Create Date: 2024-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Create users table
    op.create_table('users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(length=50), nullable=False),
        sa.Column('api_key', sa.String(length=64), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('username'),
        sa.UniqueConstraint('api_key')
    )

    # Create user_quotas table
    op.create_table('user_quotas',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('max_containers', sa.Integer(), nullable=False),
        sa.Column('max_cpu', sa.Float(), nullable=False),
        sa.Column('max_memory', sa.Integer(), nullable=False),
        sa.Column('max_storage', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create sandboxes table
    op.create_table('sandboxes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('container_id', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('image', sa.String(length=255), nullable=False),
        sa.Column('command', sa.String(length=1000), nullable=True),
        sa.Column('entrypoint', sa.String(length=1000), nullable=True),
        sa.Column('resources', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('environment', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('terminated_at', sa.DateTime(), nullable=True),
        sa.Column('last_active', sa.DateTime(), nullable=False),
        sa.Column('auto_remove', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('container_id')
    )

    # Create volumes table
    op.create_table('volumes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('sandbox_id', sa.Integer(), nullable=False),
        sa.Column('volume_id', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('mount_path', sa.String(length=255), nullable=False),
        sa.Column('size', sa.Integer(), nullable=False),
        sa.Column('driver', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['sandbox_id'], ['sandboxes.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('volume_id')
    )

    # Create ports table
    op.create_table('ports',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('sandbox_id', sa.Integer(), nullable=False),
        sa.Column('internal_port', sa.Integer(), nullable=False),
        sa.Column('external_port', sa.Integer(), nullable=False),
        sa.Column('protocol', sa.String(length=10), nullable=False),
        sa.Column('url', sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(['sandbox_id'], ['sandboxes.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create sandbox_logs table
    op.create_table('sandbox_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('sandbox_id', sa.Integer(), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('log_type', sa.String(length=10), nullable=False),
        sa.Column('level', sa.String(length=10), nullable=False),
        sa.Column('message', sa.String(), nullable=False),
        sa.ForeignKeyConstraint(['sandbox_id'], ['sandboxes.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create sandbox_metrics table
    op.create_table('sandbox_metrics',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('sandbox_id', sa.Integer(), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('cpu_usage', sa.Float(), nullable=False),
        sa.Column('memory_usage', sa.Integer(), nullable=False),
        sa.Column('memory_limit', sa.Integer(), nullable=False),
        sa.Column('network_rx_bytes', sa.Integer(), nullable=False),
        sa.Column('network_tx_bytes', sa.Integer(), nullable=False),
        sa.Column('block_read_bytes', sa.Integer(), nullable=False),
        sa.Column('block_write_bytes', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['sandbox_id'], ['sandboxes.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create alerts table
    op.create_table('alerts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('sandbox_id', sa.Integer(), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('alert_type', sa.String(length=50), nullable=False),
        sa.Column('severity', sa.String(length=20), nullable=False),
        sa.Column('message', sa.String(), nullable=False),
        sa.Column('resolved', sa.Boolean(), nullable=False),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['sandbox_id'], ['sandboxes.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

def downgrade() -> None:
    op.drop_table('alerts')
    op.drop_table('sandbox_metrics')
    op.drop_table('sandbox_logs')
    op.drop_table('ports')
    op.drop_table('volumes')
    op.drop_table('sandboxes')
    op.drop_table('user_quotas')
    op.drop_table('users') 