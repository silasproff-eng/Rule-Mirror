import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "5e3_portfolio_holdings_repair"
down_revision = "4d2_profile_identity"
branch_labels = None
depends_on = None


def upgrade():
    tables = set(inspect(op.get_bind()).get_table_names())
    if "portfolio_holdings" not in tables:
        op.create_table(
            "portfolio_holdings",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("user_id", sa.String(length=36), nullable=False),
            sa.Column("source", sa.String(length=80), nullable=False),
            sa.Column("account_reference", sa.String(length=128), nullable=False),
            sa.Column("symbol", sa.String(length=32), nullable=False),
            sa.Column("description", sa.String(length=240), nullable=True),
            sa.Column("quantity", sa.Numeric(precision=24, scale=10), nullable=False),
            sa.Column("price", sa.Numeric(precision=24, scale=10), nullable=True),
            sa.Column("market_value", sa.Numeric(precision=24, scale=10), nullable=True),
            sa.Column("cost_basis", sa.Numeric(precision=24, scale=10), nullable=True),
            sa.Column("asset_type", sa.String(length=40), nullable=False),
            sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id", "source", "account_reference", "symbol"),
        )
        op.create_index(op.f("ix_portfolio_holdings_user_id"), "portfolio_holdings", ["user_id"], unique=False)


def downgrade():
    tables = set(inspect(op.get_bind()).get_table_names())
    if "portfolio_holdings" in tables:
        op.drop_index(op.f("ix_portfolio_holdings_user_id"), table_name="portfolio_holdings")
        op.drop_table("portfolio_holdings")
