from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text

ROOT = Path(__file__).parents[3]
EXPECTED_TABLES = {
    "analysis_runs",
    "executions",
    "import_batch_executions",
    "import_batches",
    "market_cache_entries",
    "portfolio_holdings",
    "refresh_sessions",
    "rule_evaluations",
    "strategy_versions",
    "trade_analyses",
    "trade_revision_allocations",
    "trade_revisions",
    "trades",
    "users",
}


def alembic_config() -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "backend" / "alembic"))
    config.set_main_option("prepend_sys_path", str(ROOT / "backend"))
    return config


def assert_current_schema(database_url: str):
    engine = create_engine(database_url)
    schema = inspect(engine)
    assert set(schema.get_table_names()) >= EXPECTED_TABLES
    execution_uniques = {tuple(value["column_names"]) for value in schema.get_unique_constraints("executions")}
    batch_uniques = {tuple(value["column_names"]) for value in schema.get_unique_constraints("import_batch_executions")}
    assert ("user_id", "fingerprint") in execution_uniques
    assert ("import_batch_id", "row_number") in batch_uniques
    run_columns = {value["name"] for value in schema.get_columns("analysis_runs")}
    trade_columns = {value["name"] for value in schema.get_columns("trades")}
    user_columns = {value["name"] for value in schema.get_columns("users")}
    assert {"trade_revision_id", "retry_of_run_id", "failure_code", "started_at", "finished_at"} <= run_columns
    assert {"identity_key", "current_revision_id", "active"} <= trade_columns
    assert {"public_profile", "display_name"} <= user_columns
    analysis_targets = {value["referred_table"] for value in schema.get_foreign_keys("analysis_runs")}
    assert {"users", "trades", "trade_revisions", "strategy_versions", "analysis_runs"} <= analysis_targets
    with engine.connect() as connection:
        assert MigrationContext.configure(connection).get_current_revision() == "5e3_portfolio_holdings_repair"
    engine.dispose()


def test_upgrade_creates_schema_in_explicit_database_and_repairs_empty_foundation(tmp_path, monkeypatch):
    fresh_path = tmp_path / "fresh.db"
    fresh_url = f"sqlite:///{fresh_path}"
    monkeypatch.setenv("DATABASE_URL", fresh_url)
    command.upgrade(alembic_config(), "head")
    assert_current_schema(fresh_url)

    legacy_path = tmp_path / "legacy.db"
    legacy_url = f"sqlite:///{legacy_path}"
    legacy_engine = create_engine(legacy_url)
    with legacy_engine.begin() as connection:
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)"))
        connection.execute(text("INSERT INTO alembic_version (version_num) VALUES ('0001_foundation')"))
    legacy_engine.dispose()
    monkeypatch.setenv("DATABASE_URL", legacy_url)
    command.upgrade(alembic_config(), "head")
    assert_current_schema(legacy_url)
