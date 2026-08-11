import json
from pathlib import Path
from datetime import UTC, datetime, timedelta

import jwt

from app.api.dependencies import database
from app.api.routes import trade_history
from app.db.base import Base, build_engine
from app.db.models import (
    AnalysisRun,
    Execution,
    ImportBatch,
    ImportBatchExecution,
    PortfolioHolding,
    RefreshSession,
    RuleEvaluation,
    StrategyVersion,
    Trade,
    TradeAnalysis,
    TradeRevision,
    TradeRevisionAllocation,
    User,
)
from app.main import app
from app.core.config import get_settings
from app.strategies.vwap_reclaim import DEFAULT_DEFINITION
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session, sessionmaker

FIXTURE = Path(__file__).parents[1] / "fixtures" / "executions.csv"


def test_cors_allows_profile_put_for_trusted_origin_and_rejects_untrusted():
    client = TestClient(app)
    headers = {
        "Origin": get_settings().allowed_origins[0],
        "Access-Control-Request-Method": "PUT",
        "Access-Control-Request-Headers": "authorization,content-type",
    }
    allowed = client.options("/api/v1/account/profile", headers=headers)
    assert allowed.status_code == 200
    assert "PUT" in allowed.headers["access-control-allow-methods"]
    rejected = client.options(
        "/api/v1/account/profile",
        headers={**headers, "Origin": "https://untrusted.example"},
    )
    assert rejected.status_code == 400


def client_for(tmp_path):
    engine = build_engine(f"sqlite:///{tmp_path}/api.db")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[database] = override
    return TestClient(app), factory


def register(client, email):
    response = client.post("/api/v1/auth/register", json={"email": email, "password": "a-secure-password"})
    assert response.status_code == 201
    return response.json()


def authorization(tokens):
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def test_protected_routes_use_structured_auth_errors(tmp_path):
    client, _ = client_for(tmp_path)
    for headers in ({}, {"Authorization": "Basic abc"}, {"Authorization": "Bearer malformed"}):
        response = client.get("/api/v1/trades", headers=headers)
        assert response.status_code == 401
        assert response.headers["cache-control"] == "no-store"
        assert response.json()["detail"] == {"code": "invalid_access_token", "message": "Authentication is required"}
    expired = jwt.encode({"sub": "user", "typ": "access", "exp": datetime.now(UTC) - timedelta(minutes=1)}, get_settings().secret_key, algorithm="HS256")
    response = client.get("/api/v1/trades", headers={"Authorization": f"Bearer {expired}"})
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "invalid_access_token"
    tokens = register(client, "valid-token@example.com")
    valid = client.get("/api/v1/trades", headers=authorization(tokens))
    assert valid.status_code == 200
    assert valid.headers["cache-control"] == "no-store"


def test_auth_refresh_revocation_preview_and_owner_scope(tmp_path):
    client, factory = client_for(tmp_path)
    first = register(client, "first@example.com")
    second = register(client, "second@example.com")
    rotated = client.post("/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert rotated.status_code == 200
    rejected = client.post("/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert rejected.status_code == 401
    before = factory().scalar(select(func.count()).select_from(ImportBatch))
    preview = client.post("/api/v1/imports/preview", files={"file": ("fills.csv", FIXTURE.read_bytes(), "text/csv")}, headers=authorization(rotated.json()))
    after = factory().scalar(select(func.count()).select_from(ImportBatch))
    assert preview.status_code == 200
    assert "created_at" not in preview.json()
    assert before == after == 0
    mapping = preview.json()["suggested_mapping"]
    imported = client.post("/api/v1/imports", files={"file": ("fills.csv", FIXTURE.read_bytes(), "text/csv")}, data={"mapping": json.dumps(mapping)}, headers=authorization(rotated.json()))
    assert imported.status_code == 201
    imports = client.get("/api/v1/imports", headers=authorization(rotated.json()))
    assert imports.status_code == 200
    assert imports.json()[0]["id"] == imported.json()["id"]
    trades = client.get("/api/v1/trades", headers=authorization(rotated.json()))
    assert trades.status_code == 200
    assert trades.json()[0]["symbol"] == "NVDA"
    trade_id = imported.json()["trades"][0]["id"]
    run = client.post("/api/v1/analysis-runs", json={"trade_id": trade_id}, headers=authorization(rotated.json()))
    assert run.status_code == 202
    status = client.get(f"/api/v1/analysis-runs/{run.json()['id']}", headers=authorization(rotated.json()))
    assert status.json()["status"] == "completed"
    result = client.get(f"/api/v1/trade-analyses/{status.json()['trade_analysis_id']}", headers=authorization(rotated.json()))
    assert result.json()["symbol"] == "NVDA"
    assert result.json()["strategy"] == {"slug": "vwap-reclaim", "name": "VWAP Reclaim", "version": 1}
    assert "rules" in result.json()
    assert "bars" not in result.json()
    retried = client.post("/api/v1/analysis-runs", json={"trade_id": trade_id}, headers=authorization(rotated.json()))
    assert retried.status_code == 202
    assert retried.json()["id"] == run.json()["id"]
    assert retried.json()["reused"] is True
    retry_status = client.get(f"/api/v1/analysis-runs/{retried.json()['id']}", headers=authorization(rotated.json()))
    assert retry_status.json()["status"] == "completed"
    with factory() as session:
        original = session.get(AnalysisRun, run.json()["id"])
        failed = AnalysisRun(user_id=original.user_id, trade_id=original.trade_id, trade_revision_id=original.trade_revision_id, strategy_version_id=original.strategy_version_id, retry_of_run_id=None, provider=original.provider, engine_version=original.engine_version, status="failed", failure_code="provider_error", created_at=original.created_at, started_at=original.started_at, finished_at=original.finished_at)
        session.add(failed)
        session.commit()
        failed_id = failed.id
    retry_failed = client.post("/api/v1/analysis-runs", json={"trade_id": trade_id, "retry_of_run_id": failed_id}, headers=authorization(rotated.json()))
    assert retry_failed.json()["id"] not in {run.json()["id"], failed_id}
    retry_failed_status = client.get(f"/api/v1/analysis-runs/{retry_failed.json()['id']}", headers=authorization(rotated.json()))
    assert retry_failed_status.json()["retry_of_run_id"] == failed_id
    old_failed = client.get(f"/api/v1/analysis-runs/{failed_id}", headers=authorization(rotated.json()))
    assert old_failed.json()["status"] == "failed"
    with factory() as session:
        before_duplicate = (session.scalar(select(func.count()).select_from(Trade)), session.scalar(select(func.count()).select_from(TradeRevision)), session.scalar(select(func.count()).select_from(TradeAnalysis)), session.scalar(select(func.count()).select_from(RuleEvaluation)))
    duplicate = client.post("/api/v1/imports", files={"file": ("fills.csv", FIXTURE.read_bytes(), "text/csv")}, data={"mapping": json.dumps(mapping)}, headers=authorization(rotated.json()))
    assert duplicate.json()["duplicate_count"] == 5
    assert duplicate.json()["trades"] == []
    assert duplicate.json()["candidate_trades"] == []
    with factory() as session:
        after_duplicate = (session.scalar(select(func.count()).select_from(Trade)), session.scalar(select(func.count()).select_from(TradeRevision)), session.scalar(select(func.count()).select_from(TradeAnalysis)), session.scalar(select(func.count()).select_from(RuleEvaluation)))
    assert after_duplicate == before_duplicate
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Execution)) == 5
        assert session.scalar(select(func.count()).select_from(ImportBatchExecution)) == 10
    preserved = client.get(f"/api/v1/analysis-runs/{run.json()['id']}", headers=authorization(rotated.json()))
    assert preserved.status_code == 200
    assert preserved.json()["trade_analysis_id"] == status.json()["trade_analysis_id"]
    aapl = b"Symbol,Side,Quantity,Price,Execution Time,Execution ID,Account\nAAPL,Buy,10,200,2026-08-06T14:17:32Z,a1,main\nAAPL,Sell,10,202,2026-08-06T15:17:32Z,a2,main\n"
    added = client.post("/api/v1/imports", files={"file": ("aapl.csv", aapl, "text/csv")}, data={"mapping": json.dumps(mapping)}, headers=authorization(rotated.json()))
    assert [value["symbol"] for value in added.json()["candidate_trades"]] == ["AAPL"]
    still_preserved = client.get(f"/api/v1/analysis-runs/{run.json()['id']}", headers=authorization(rotated.json()))
    assert still_preserved.status_code == 200
    forbidden = client.get(f"/api/v1/imports/{imported.json()['id']}", headers=authorization(second))
    assert forbidden.status_code == 404
    app.dependency_overrides.clear()


def test_account_deletion_revokes_owned_data(tmp_path):
    client, factory = client_for(tmp_path)
    tokens = register(client, "delete@example.com")
    headers = authorization(tokens)
    preview = client.post("/api/v1/imports/preview", files={"file": ("fills.csv", FIXTURE.read_bytes(), "text/csv")}, headers=headers)
    mapping = preview.json()["suggested_mapping"]
    imported = client.post("/api/v1/imports", files={"file": ("fills.csv", FIXTURE.read_bytes(), "text/csv")}, data={"mapping": json.dumps(mapping)}, headers=headers)
    trade = imported.json()["candidate_trades"][0]
    assert client.post("/api/v1/analysis-runs", json={"trade_id": trade["id"], "trade_revision_id": trade["trade_revision_id"]}, headers=headers).status_code == 202
    assert client.post("/api/v1/portfolio/import", files={"file": ("positions.csv", b"Symbol,Description,Quantity,Price,Market Value\nNVDA,NVIDIA CORP,1,$100,$100\n", "text/csv")}, headers=headers).status_code == 201
    response = client.delete("/api/v1/account", headers=authorization(tokens))
    assert response.status_code == 204
    with factory() as session:
        for model in (User, RefreshSession, ImportBatch, Execution, PortfolioHolding, Trade, TradeRevision, TradeRevisionAllocation, AnalysisRun, TradeAnalysis, RuleEvaluation, ImportBatchExecution):
            assert session.scalar(select(func.count()).select_from(model)) == 0
        assert session.scalar(select(func.count()).select_from(StrategyVersion)) == 1
    app.dependency_overrides.clear()


def test_public_profile_search_includes_identity_and_metrics(tmp_path):
    client, factory = client_for(tmp_path)
    tokens = register(client, "profile@example.com")
    profile = client.put("/api/v1/account/profile", json={"display_name": "Silas"}, headers=authorization(tokens))
    assert profile.status_code == 200
    portfolio = client.post("/api/v1/portfolio/import", files={"file": ("positions.csv", b"Symbol,Description,Quantity,Price,Market Value\nNVDA,NVIDIA CORP,0.5,$200,$100\n", "text/csv")}, headers=authorization(tokens))
    assert portfolio.status_code == 201
    enabled = client.put("/api/v1/account/public-profile?enabled=true", headers=authorization(tokens))
    assert enabled.status_code == 200
    result = client.get("/api/v1/accounts/search?q=profile", headers=authorization(tokens))
    assert result.status_code == 200
    account = result.json()[0]
    assert account["display_name"] == "Silas"
    assert "avatar_data_url" not in account
    assert account["metrics"]["portfolio_value"] == 100
    assert set(account["metrics"]) >= {"total_pnl", "win_rate", "discipline", "portfolio_value", "closed_trades", "reviewed_trades"}
    opened = client.get("/api/v1/accounts/profile%40example.com", headers=authorization(tokens))
    assert opened.status_code == 200
    assert opened.json()["display_name"] == "Silas"
    app.dependency_overrides.clear()


def test_split_file_reconstructs_against_full_execution_history(tmp_path):
    client, factory = client_for(tmp_path)
    tokens = register(client, "split@example.com")
    lines = FIXTURE.read_text().splitlines()
    first_data = ("\n".join([lines[0], *lines[1:3]]) + "\n").encode()
    second_data = ("\n".join([lines[0], *lines[3:]]) + "\n").encode()
    preview_response = client.post("/api/v1/imports/preview", files={"file": ("first.csv", first_data, "text/csv")}, headers=authorization(tokens))
    mapping = preview_response.json()["suggested_mapping"]
    first = client.post("/api/v1/imports", files={"file": ("first.csv", first_data, "text/csv")}, data={"mapping": json.dumps(mapping)}, headers=authorization(tokens))
    assert first.json()["created_at"].endswith("+00:00")
    assert first.json()["candidate_trades"] == []
    assert first.json()["affected_trades"][0]["analysis_eligible"] is False
    first_trade_id = first.json()["affected_trades"][0]["trade_id"]
    first_revision_id = first.json()["affected_trades"][0]["trade_revision_id"]
    second = client.post("/api/v1/imports", files={"file": ("second.csv", second_data, "text/csv")}, data={"mapping": json.dumps(mapping)}, headers=authorization(tokens))
    assert len(second.json()["candidate_trades"]) == 2
    updated_long = next(value for value in second.json()["affected_trades"] if value["direction"] == "long")
    assert updated_long["trade_id"] == first_trade_id
    assert updated_long["trade_revision_id"] != first_revision_id
    assert all(value["closed_at"] for value in second.json()["candidate_trades"])
    app.dependency_overrides.clear()


def test_non_object_mapping_is_structured_422(tmp_path):
    client, factory = client_for(tmp_path)
    tokens = register(client, "mapping@example.com")
    response = client.post("/api/v1/imports", files={"file": ("fills.csv", FIXTURE.read_bytes(), "text/csv")}, data={"mapping": "[]"}, headers=authorization(tokens))
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_mapping"
    app.dependency_overrides.clear()


def test_superseded_trade_history_and_analysis_remain_queryable(tmp_path):
    client, factory = client_for(tmp_path)
    tokens = register(client, "history@example.com")
    headers = authorization(tokens)
    preview_response = client.post("/api/v1/imports/preview", files={"file": ("fills.csv", FIXTURE.read_bytes(), "text/csv")}, headers=headers)
    mapping = preview_response.json()["suggested_mapping"]
    imported = client.post("/api/v1/imports", files={"file": ("fills.csv", FIXTURE.read_bytes(), "text/csv")}, data={"mapping": json.dumps(mapping)}, headers=headers)
    original_trade = next(value for value in imported.json()["candidate_trades"] if value["direction"] == "long")
    run_response = client.post("/api/v1/analysis-runs", json={"trade_id": original_trade["id"], "trade_revision_id": original_trade["trade_revision_id"]}, headers=headers)
    run_id = run_response.json()["id"]
    run_before = client.get(f"/api/v1/analysis-runs/{run_id}", headers=headers).json()
    analysis_id = run_before["trade_analysis_id"]
    older = b"Symbol,Side,Quantity,Price,Execution Time,Execution ID,Account\nNVDA,Buy,10,100.50,2026-08-05T14:16:00Z,e0,main\n"
    later_import = client.post("/api/v1/imports", files={"file": ("older.csv", older, "text/csv")}, data={"mapping": json.dumps(mapping)}, headers=headers)
    assert later_import.status_code == 201
    replacement_long = next(value for value in later_import.json()["affected_trades"] if value["direction"] == "long")
    assert replacement_long["trade_id"] != original_trade["id"]
    with factory() as session:
        old_trade = session.get(Trade, original_trade["id"])
        assert old_trade is not None
        assert old_trade.active is False
        assert session.get(TradeRevision, original_trade["trade_revision_id"]) is not None
    run_after = client.get(f"/api/v1/analysis-runs/{run_id}", headers=headers)
    result_after = client.get(f"/api/v1/trade-analyses/{analysis_id}", headers=headers)
    assert run_after.status_code == 200
    assert run_after.json()["trade_analysis_id"] == analysis_id
    assert result_after.status_code == 200
    assert result_after.json()["trade_id"] == original_trade["id"]
    assert result_after.json()["trade_revision_id"] == original_trade["trade_revision_id"]
    app.dependency_overrides.clear()


def test_trade_history_bulk_loads_current_revision_details(tmp_path):
    client, factory = client_for(tmp_path)
    tokens = register(client, "history-bulk@example.com")
    headers = authorization(tokens)
    preview_response = client.post("/api/v1/imports/preview", files={"file": ("fills.csv", FIXTURE.read_bytes(), "text/csv")}, headers=headers)
    imported = client.post("/api/v1/imports", files={"file": ("fills.csv", FIXTURE.read_bytes(), "text/csv")}, data={"mapping": json.dumps(preview_response.json()["suggested_mapping"])}, headers=headers)
    assert imported.status_code == 201
    with factory() as session:
        user_id = session.scalar(select(User.id).where(User.email == "history-bulk@example.com"))
        statements: list[str] = []

        def record_statement(_connection, _cursor, statement, _parameters, _context, _executemany):
            if statement.lstrip().upper().startswith("SELECT"):
                statements.append(statement)

        event.listen(session.bind, "before_cursor_execute", record_statement)
        try:
            history = trade_history(user_id=user_id, session=session)
        finally:
            event.remove(session.bind, "before_cursor_execute", record_statement)
    assert len(history) == 2
    assert len(statements) == 5
    app.dependency_overrides.clear()


def test_stale_analysis_runs_fail_before_status_or_reuse(tmp_path):
    client, factory = client_for(tmp_path)
    tokens = register(client, "stale-run@example.com")
    headers = authorization(tokens)
    preview_response = client.post("/api/v1/imports/preview", files={"file": ("fills.csv", FIXTURE.read_bytes(), "text/csv")}, headers=headers)
    imported = client.post("/api/v1/imports", files={"file": ("fills.csv", FIXTURE.read_bytes(), "text/csv")}, data={"mapping": json.dumps(preview_response.json()["suggested_mapping"])}, headers=headers)
    trade_id = imported.json()["candidate_trades"][0]["id"]
    revision_id = imported.json()["candidate_trades"][0]["trade_revision_id"]
    with factory() as session:
        user = session.scalar(select(User).where(User.email == "stale-run@example.com"))
        strategy = StrategyVersion(slug="vwap-reclaim", version=1, definition=DEFAULT_DEFINITION, created_at=datetime.now(UTC))
        session.add(strategy)
        session.flush()
        stale = AnalysisRun(user_id=user.id, trade_id=trade_id, trade_revision_id=revision_id, strategy_version_id=strategy.id, retry_of_run_id=None, provider=get_settings().market_data_provider, engine_version="vwap-reclaim-1", status="running", failure_code=None, created_at=datetime.now(UTC) - timedelta(seconds=get_settings().analysis_run_stale_seconds + 1), started_at=datetime.now(UTC) - timedelta(seconds=get_settings().analysis_run_stale_seconds + 1), finished_at=None)
        session.add(stale)
        session.commit()
        stale_id = stale.id
    replacement = client.post("/api/v1/analysis-runs", json={"trade_id": trade_id}, headers=headers)
    assert replacement.status_code == 202
    assert replacement.json()["id"] != stale_id
    assert replacement.json()["reused"] is False
    with factory() as session:
        previous = session.get(AnalysisRun, stale_id)
        assert previous.status == "failed"
        assert previous.failure_code == "analysis_interrupted"
        strategy = session.get(StrategyVersion, previous.strategy_version_id)
        stale_status_run = AnalysisRun(user_id=previous.user_id, trade_id=trade_id, trade_revision_id=revision_id, strategy_version_id=strategy.id, retry_of_run_id=None, provider=get_settings().market_data_provider, engine_version="vwap-reclaim-1", status="running", failure_code=None, created_at=datetime.now(UTC) - timedelta(seconds=get_settings().analysis_run_stale_seconds + 1), started_at=datetime.now(UTC) - timedelta(seconds=get_settings().analysis_run_stale_seconds + 1), finished_at=None)
        session.add(stale_status_run)
        session.commit()
        stale_status_id = stale_status_run.id
    stale_status = client.get(f"/api/v1/analysis-runs/{stale_status_id}", headers=headers)
    assert stale_status.json()["status"] == "failed"
    assert stale_status.json()["failure_code"] == "analysis_interrupted"
    assert stale_status.json()["finished_at"] is not None
    app.dependency_overrides.clear()


def test_recent_analysis_run_remains_reusable(tmp_path):
    client, factory = client_for(tmp_path)
    tokens = register(client, "recent-run@example.com")
    headers = authorization(tokens)
    preview_response = client.post("/api/v1/imports/preview", files={"file": ("fills.csv", FIXTURE.read_bytes(), "text/csv")}, headers=headers)
    imported = client.post("/api/v1/imports", files={"file": ("fills.csv", FIXTURE.read_bytes(), "text/csv")}, data={"mapping": json.dumps(preview_response.json()["suggested_mapping"])}, headers=headers)
    trade_id = imported.json()["candidate_trades"][0]["id"]
    revision_id = imported.json()["candidate_trades"][0]["trade_revision_id"]
    with factory() as session:
        user = session.scalar(select(User).where(User.email == "recent-run@example.com"))
        strategy = StrategyVersion(slug="vwap-reclaim", version=1, definition=DEFAULT_DEFINITION, created_at=datetime.now(UTC))
        session.add(strategy)
        session.flush()
        current_time = datetime.now(UTC)
        recent = AnalysisRun(user_id=user.id, trade_id=trade_id, trade_revision_id=revision_id, strategy_version_id=strategy.id, retry_of_run_id=None, provider=get_settings().market_data_provider, engine_version="vwap-reclaim-1", status="queued", failure_code=None, created_at=current_time, started_at=None, finished_at=None)
        session.add(recent)
        session.commit()
        recent_id = recent.id
    recent_status = client.get(f"/api/v1/analysis-runs/{recent_id}", headers=headers)
    assert recent_status.json()["status"] == "queued"
    reused = client.post("/api/v1/analysis-runs", json={"trade_id": trade_id}, headers=headers)
    assert reused.json() == {"id": recent_id, "status": "queued", "reused": True}
    app.dependency_overrides.clear()


def test_analysis_failure_rolls_back_partial_result_rows(tmp_path):
    client, factory = client_for(tmp_path)
    tokens = register(client, "rollback@example.com")
    headers = authorization(tokens)
    preview_response = client.post("/api/v1/imports/preview", files={"file": ("fills.csv", FIXTURE.read_bytes(), "text/csv")}, headers=headers)
    mapping = preview_response.json()["suggested_mapping"]
    imported = client.post("/api/v1/imports", files={"file": ("fills.csv", FIXTURE.read_bytes(), "text/csv")}, data={"mapping": json.dumps(mapping)}, headers=headers)
    trade = imported.json()["candidate_trades"][0]
    raised = False

    def fail_result_commit(session):
        nonlocal raised
        if not raised and any(isinstance(value, RuleEvaluation) for value in session.new):
            raised = True
            raise RuntimeError("forced_result_commit_failure")

    event.listen(Session, "before_commit", fail_result_commit)
    try:
        response = client.post("/api/v1/analysis-runs", json={"trade_id": trade["id"], "trade_revision_id": trade["trade_revision_id"]}, headers=headers)
    finally:
        event.remove(Session, "before_commit", fail_result_commit)
    assert response.status_code == 202
    status_response = client.get(f"/api/v1/analysis-runs/{response.json()['id']}", headers=headers)
    assert status_response.json()["status"] == "failed"
    assert status_response.json()["retryable"] is True
    with factory() as session:
        analyses = session.scalar(select(func.count()).select_from(TradeAnalysis).where(TradeAnalysis.run_id == response.json()["id"]))
        rules = session.scalar(select(func.count()).select_from(RuleEvaluation).join(TradeAnalysis).where(TradeAnalysis.run_id == response.json()["id"]))
        assert analyses == 0
        assert rules == 0
    app.dependency_overrides.clear()
