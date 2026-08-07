import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "4d2_profile_identity"
down_revision = "3c1_public_profiles"
branch_labels = None
depends_on = None


def upgrade():
    existing = {column["name"] for column in inspect(op.get_bind()).get_columns("users")}
    if "display_name" not in existing:
        op.add_column("users", sa.Column("display_name", sa.String(length=120), nullable=True))
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
    existing = {column["name"] for column in inspect(op.get_bind()).get_columns("users")}
    tables = set(inspect(op.get_bind()).get_table_names())
    if "portfolio_holdings" in tables:
        op.drop_index(op.f("ix_portfolio_holdings_user_id"), table_name="portfolio_holdings")
        op.drop_table("portfolio_holdings")
    if "display_name" in existing:
        op.drop_column("users", "display_name")
