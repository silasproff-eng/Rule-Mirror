import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "3c1_public_profiles"
down_revision = "2e967dccb24e"
branch_labels = None
depends_on = None


def upgrade():
    if "public_profile" not in {column["name"] for column in inspect(op.get_bind()).get_columns("users")}:
        op.add_column("users", sa.Column("public_profile", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column("users", "public_profile")
