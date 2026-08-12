import secrets
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect, text

revision = "6f1_opaque_public_handles"
down_revision = "5e3_portfolio_holdings_repair"
branch_labels = None
depends_on = None


def upgrade():
    columns = {value["name"] for value in inspect(op.get_bind()).get_columns("users")}
    if "public_handle" not in columns:
        op.add_column("users", sa.Column("public_handle", sa.String(length=32), nullable=True))
    bind = op.get_bind()
    rows = bind.execute(text("SELECT id FROM users WHERE public_handle IS NULL OR public_handle = ''")).fetchall()
    for row in rows:
        handle = f"member-{secrets.token_hex(6)}"
        while bind.execute(text("SELECT 1 FROM users WHERE public_handle = :handle"), {"handle": handle}).first():
            handle = f"member-{secrets.token_hex(6)}"
        bind.execute(text("UPDATE users SET public_handle = :handle WHERE id = :id"), {"handle": handle, "id": row[0]})
    op.alter_column("users", "public_handle", nullable=False)
    op.create_index("ix_users_public_handle", "users", ["public_handle"], unique=True)


def downgrade():
    op.drop_index("ix_users_public_handle", table_name="users")
    op.drop_column("users", "public_handle")
