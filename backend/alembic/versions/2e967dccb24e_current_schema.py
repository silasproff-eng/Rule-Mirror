import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "2e967dccb24e"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None

EXPECTED_TABLES = {
    "analysis_runs",
    "executions",
    "import_batch_executions",
    "import_batches",
    "market_cache_entries",
    "refresh_sessions",
    "rule_evaluations",
    "strategy_versions",
    "trade_analyses",
    "trade_revision_allocations",
    "trade_revisions",
    "trades",
    "users",
}


def upgrade():
    existing = set(inspect(op.get_bind()).get_table_names()) - {"alembic_version"}
    if existing >= EXPECTED_TABLES:
        return
    if existing:
        missing = ", ".join(sorted(EXPECTED_TABLES - existing))
        raise RuntimeError(f"Partial foundation schema requires manual repair; missing: {missing}")
    op.create_table('market_cache_entries',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('provider', sa.String(length=40), nullable=False),
    sa.Column('instrument', sa.String(length=32), nullable=False),
    sa.Column('asset_type', sa.String(length=20), nullable=False),
    sa.Column('session_date', sa.String(length=10), nullable=False),
    sa.Column('timeframe', sa.String(length=10), nullable=False),
    sa.Column('schema_version', sa.Integer(), nullable=False),
    sa.Column('normalized_payload', sa.Text(), nullable=False),
    sa.Column('checksum', sa.String(length=64), nullable=False),
    sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('storage_policy', sa.String(length=80), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('provider', 'instrument', 'asset_type', 'session_date', 'timeframe', 'schema_version')
    )
    op.create_table('strategy_versions',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('slug', sa.String(length=80), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('definition', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_strategy_versions_slug'), 'strategy_versions', ['slug'], unique=False)
    op.create_table('users',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('password_hash', sa.String(length=512), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_table('executions',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('symbol', sa.String(length=32), nullable=False),
    sa.Column('asset_type', sa.String(length=20), nullable=False),
    sa.Column('side', sa.String(length=8), nullable=False),
    sa.Column('quantity', sa.Numeric(precision=24, scale=10), nullable=False),
    sa.Column('price', sa.Numeric(precision=24, scale=10), nullable=False),
    sa.Column('commission', sa.Numeric(precision=24, scale=10), nullable=False),
    sa.Column('fees', sa.Numeric(precision=24, scale=10), nullable=False),
    sa.Column('executed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('account_reference', sa.String(length=128), nullable=False),
    sa.Column('external_execution_id', sa.String(length=160), nullable=True),
    sa.Column('row_number', sa.Integer(), nullable=False),
    sa.Column('row_hash', sa.String(length=64), nullable=False),
    sa.Column('fingerprint', sa.String(length=64), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'fingerprint')
    )
    op.create_index(op.f('ix_executions_executed_at'), 'executions', ['executed_at'], unique=False)
    op.create_index(op.f('ix_executions_user_id'), 'executions', ['user_id'], unique=False)
    op.create_table('import_batches',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('display_name', sa.String(length=160), nullable=False),
    sa.Column('file_hash', sa.String(length=64), nullable=False),
    sa.Column('mapping', sa.JSON(), nullable=False),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('execution_count', sa.Integer(), nullable=False),
    sa.Column('trade_count', sa.Integer(), nullable=False),
    sa.Column('duplicate_count', sa.Integer(), nullable=False),
    sa.Column('error_count', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_import_batches_user_id'), 'import_batches', ['user_id'], unique=False)
    op.create_table('refresh_sessions',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token_hash')
    )
    op.create_index(op.f('ix_refresh_sessions_user_id'), 'refresh_sessions', ['user_id'], unique=False)
    op.create_table('trades',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('symbol', sa.String(length=32), nullable=False),
    sa.Column('asset_type', sa.String(length=20), nullable=False),
    sa.Column('account_reference', sa.String(length=128), nullable=False),
    sa.Column('identity_key', sa.String(length=64), nullable=False),
    sa.Column('direction', sa.String(length=8), nullable=False),
    sa.Column('opened_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('opened_quantity', sa.Numeric(precision=24, scale=10), nullable=False),
    sa.Column('current_revision_id', sa.String(length=36), nullable=True),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['current_revision_id'], ['trade_revisions.id'], use_alter=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'identity_key')
    )
    op.create_index(op.f('ix_trades_user_id'), 'trades', ['user_id'], unique=False)
    op.create_table('import_batch_executions',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('import_batch_id', sa.String(length=36), nullable=False),
    sa.Column('execution_id', sa.String(length=36), nullable=False),
    sa.Column('row_number', sa.Integer(), nullable=False),
    sa.Column('row_hash', sa.String(length=64), nullable=False),
    sa.Column('was_inserted', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['execution_id'], ['executions.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['import_batch_id'], ['import_batches.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('import_batch_id', 'row_number')
    )
    op.create_index(op.f('ix_import_batch_executions_execution_id'), 'import_batch_executions', ['execution_id'], unique=False)
    op.create_index(op.f('ix_import_batch_executions_import_batch_id'), 'import_batch_executions', ['import_batch_id'], unique=False)
    op.create_table('trade_revisions',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('trade_id', sa.String(length=36), nullable=False),
    sa.Column('revision_hash', sa.String(length=64), nullable=False),
    sa.Column('direction', sa.String(length=8), nullable=False),
    sa.Column('opened_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('opened_quantity', sa.Numeric(precision=24, scale=10), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['trade_id'], ['trades.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('trade_id', 'revision_hash')
    )
    op.create_table('analysis_runs',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('trade_id', sa.String(length=36), nullable=False),
    sa.Column('trade_revision_id', sa.String(length=36), nullable=False),
    sa.Column('strategy_version_id', sa.String(length=36), nullable=False),
    sa.Column('retry_of_run_id', sa.String(length=36), nullable=True),
    sa.Column('provider', sa.String(length=40), nullable=False),
    sa.Column('engine_version', sa.String(length=30), nullable=False),
    sa.Column('status', sa.String(length=24), nullable=False),
    sa.Column('failure_code', sa.String(length=80), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['retry_of_run_id'], ['analysis_runs.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['strategy_version_id'], ['strategy_versions.id'], ),
    sa.ForeignKeyConstraint(['trade_id'], ['trades.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['trade_revision_id'], ['trade_revisions.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_analysis_runs_user_id'), 'analysis_runs', ['user_id'], unique=False)
    op.create_table('trade_revision_allocations',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('trade_revision_id', sa.String(length=36), nullable=False),
    sa.Column('execution_id', sa.String(length=36), nullable=False),
    sa.Column('quantity', sa.Numeric(precision=24, scale=10), nullable=False),
    sa.Column('role', sa.String(length=12), nullable=False),
    sa.Column('sequence', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['execution_id'], ['executions.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['trade_revision_id'], ['trade_revisions.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('trade_revision_id', 'sequence')
    )
    op.create_table('trade_analyses',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('run_id', sa.String(length=36), nullable=False),
    sa.Column('trade_id', sa.String(length=36), nullable=False),
    sa.Column('score', sa.Integer(), nullable=True),
    sa.Column('data_sufficiency', sa.String(length=30), nullable=False),
    sa.Column('feedback', sa.JSON(), nullable=False),
    sa.Column('derived_context', sa.JSON(), nullable=False),
    sa.ForeignKeyConstraint(['run_id'], ['analysis_runs.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['trade_id'], ['trades.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('run_id')
    )
    op.create_table('rule_evaluations',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('trade_analysis_id', sa.String(length=36), nullable=False),
    sa.Column('rule_key', sa.String(length=80), nullable=False),
    sa.Column('result', sa.String(length=24), nullable=False),
    sa.Column('measurement', sa.String(length=100), nullable=True),
    sa.Column('threshold', sa.String(length=100), nullable=True),
    sa.Column('weight', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['trade_analysis_id'], ['trade_analyses.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('trade_analysis_id', 'rule_key')
    )


def downgrade():
    op.drop_table('rule_evaluations')
    op.drop_table('trade_analyses')
    op.drop_table('trade_revision_allocations')
    op.drop_index(op.f('ix_analysis_runs_user_id'), table_name='analysis_runs')
    op.drop_table('analysis_runs')
    op.drop_table('trade_revisions')
    op.drop_index(op.f('ix_import_batch_executions_import_batch_id'), table_name='import_batch_executions')
    op.drop_index(op.f('ix_import_batch_executions_execution_id'), table_name='import_batch_executions')
    op.drop_table('import_batch_executions')
    op.drop_index(op.f('ix_trades_user_id'), table_name='trades')
    op.drop_table('trades')
    op.drop_index(op.f('ix_refresh_sessions_user_id'), table_name='refresh_sessions')
    op.drop_table('refresh_sessions')
    op.drop_index(op.f('ix_import_batches_user_id'), table_name='import_batches')
    op.drop_table('import_batches')
    op.drop_index(op.f('ix_executions_user_id'), table_name='executions')
    op.drop_index(op.f('ix_executions_executed_at'), table_name='executions')
    op.drop_table('executions')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
    op.drop_index(op.f('ix_strategy_versions_slug'), table_name='strategy_versions')
    op.drop_table('strategy_versions')
    op.drop_table('market_cache_entries')
