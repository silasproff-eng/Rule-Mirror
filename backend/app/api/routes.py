import hashlib
import json
import re
import secrets
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.api.dependencies import current_user_id, database
from app.api.schemas import AnalysisRequest, Credentials, ProfileUpdate, RefreshRequest, TokenPair
from app.core.config import get_settings
from app.core.security import (
    access_token,
    hash_password,
    new_refresh_token,
    refresh_hash,
    verify_password,
)
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
from app.imports.csv_parser import (
    ImportValidationError,
    NormalizedExecution,
    parse_executions,
    preview,
)
from app.imports.holdings_parser import parse_holdings
from app.imports.reconstruction import reconstruct
from app.market_data.registry import configured_provider
from app.strategies.catalog import catalog_payload, definition_for
from app.strategies.vwap_reclaim import DEFAULT_DEFINITION, evaluate, result_payload

router = APIRouter(prefix="/api/v1")


def utc_value(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def fail_stale_analysis_run(run: AnalysisRun, stale_seconds: int, now: datetime | None = None) -> bool:
    if run.status not in {"queued", "running"}:
        return False
    current_time = now or datetime.now(UTC)
    last_progress = utc_value(run.started_at or run.created_at)
    if last_progress > current_time - timedelta(seconds=max(stale_seconds, 1)):
        return False
    run.status = "failed"
    run.failure_code = "analysis_interrupted"
    run.finished_at = current_time
    return True


def normalized_from_model(value: Execution) -> NormalizedExecution:
    return NormalizedExecution(
        value.symbol,
        value.side,
        value.quantity,
        value.price,
        utc_value(value.executed_at),
        value.commission,
        value.fees,
        value.account_reference,
        value.asset_type,
        value.external_execution_id,
        value.row_number,
        value.row_hash,
        value.fingerprint,
    )


def trade_identity(user_id: str, symbol: str, asset_type: str, account_reference: str, direction: str, first_open_fingerprint: str, segment: int) -> str:
    value = f"{user_id}|{account_reference}|{symbol}|{asset_type}|{direction}|{first_open_fingerprint}|{segment}"
    return hashlib.sha256(value.encode()).hexdigest()


def revision_hash(value, asset_type: str) -> str:
    allocations = "|".join(f"{item.fingerprint}:{item.quantity}:{item.role}" for item in value.allocations)
    raw = f"{value.symbol}|{asset_type}|{value.account_reference}|{value.direction}|{utc_value(value.opened_at).isoformat()}|{utc_value(value.closed_at).isoformat() if value.closed_at else ''}|{value.opened_quantity}|{allocations}"
    return hashlib.sha256(raw.encode()).hexdigest()


def reconcile_user_trades(session: Session, user_id: str, affected_fingerprints: set[str]) -> tuple[list[Trade], list[dict]]:
    models = session.scalars(select(Execution).where(Execution.user_id == user_id).order_by(Execution.executed_at, Execution.row_number)).all()
    by_fingerprint = {value.fingerprint: value for value in models}
    rebuilt = reconstruct([normalized_from_model(value) for value in models])
    existing = session.scalars(select(Trade).where(Trade.user_id == user_id)).all()
    by_identity = {value.identity_key: value for value in existing}
    active_identities: set[str] = set()
    trades: list[Trade] = []
    affected: list[dict] = []
    for reconstructed in rebuilt:
        first_execution = by_fingerprint[reconstructed.allocations[0].fingerprint]
        first_open = next(item.fingerprint for item in reconstructed.allocations if item.role == "open")
        identity = trade_identity(user_id, reconstructed.symbol, first_execution.asset_type, reconstructed.account_reference, reconstructed.direction, first_open, 0)
        active_identities.add(identity)
        trade = by_identity.get(identity)
        change_type = "updated"
        if trade is None:
            trade = Trade(user_id=user_id, symbol=reconstructed.symbol, asset_type=first_execution.asset_type, account_reference=reconstructed.account_reference, identity_key=identity, direction=reconstructed.direction, opened_at=utc_value(reconstructed.opened_at), closed_at=utc_value(reconstructed.closed_at) if reconstructed.closed_at else None, opened_quantity=reconstructed.opened_quantity, current_revision_id=None, active=True)
            session.add(trade)
            session.flush()
            change_type = "created"
        current_hash = revision_hash(reconstructed, first_execution.asset_type)
        current_revision = session.get(TradeRevision, trade.current_revision_id) if trade.current_revision_id else None
        changed = current_revision is None or current_revision.revision_hash != current_hash
        if changed:
            revision = TradeRevision(trade_id=trade.id, revision_hash=current_hash, direction=reconstructed.direction, opened_at=utc_value(reconstructed.opened_at), closed_at=utc_value(reconstructed.closed_at) if reconstructed.closed_at else None, opened_quantity=reconstructed.opened_quantity, created_at=datetime.now(UTC))
            session.add(revision)
            session.flush()
            for sequence, allocation in enumerate(reconstructed.allocations):
                session.add(TradeRevisionAllocation(trade_revision_id=revision.id, execution_id=by_fingerprint[allocation.fingerprint].id, quantity=allocation.quantity, role=allocation.role, sequence=sequence))
            trade.current_revision_id = revision.id
            trade.direction = reconstructed.direction
            trade.opened_at = utc_value(reconstructed.opened_at)
            trade.closed_at = utc_value(reconstructed.closed_at) if reconstructed.closed_at else None
            trade.opened_quantity = reconstructed.opened_quantity
        trade.active = True
        trades.append(trade)
        if changed and any(allocation.fingerprint in affected_fingerprints for allocation in reconstructed.allocations):
            affected.append({"trade": trade, "revision_id": trade.current_revision_id, "change_type": change_type})
    for trade in existing:
        if trade.identity_key not in active_identities:
            trade.active = False
    return trades, affected


def safe_name(value: str | None) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._ -]", "_", (value or "executions.csv").split("/")[-1].split("\\")[-1])
    return cleaned[:160] or "executions.csv"


def issue(error: ImportValidationError):
    raise HTTPException(422, detail={"code": error.code, "message": error.message, "field": error.field, "row": error.row}) from error


def trade_metrics(session: Session, user_id: str) -> dict:
    trades = session.scalars(select(Trade).where(Trade.user_id == user_id, Trade.active.is_(True))).all()
    trade_ids = [trade.id for trade in trades]
    current_revisions = {trade.id: trade.current_revision_id for trade in trades}
    analyses = session.execute(select(TradeAnalysis, AnalysisRun.trade_revision_id, AnalysisRun.created_at).join(AnalysisRun, TradeAnalysis.run_id == AnalysisRun.id).where(TradeAnalysis.trade_id.in_(trade_ids)).order_by(AnalysisRun.created_at.desc(), TradeAnalysis.id.desc())).all() if trade_ids else []
    closed = [trade for trade in trades if trade.closed_at]
    realized_values = []
    entry_notional = Decimal("0")
    for trade in closed:
        revision = session.get(TradeRevision, trade.current_revision_id) if trade.current_revision_id else None
        allocations = session.scalars(select(TradeRevisionAllocation).where(TradeRevisionAllocation.trade_revision_id == trade.current_revision_id)).all() if revision else []
        execution_ids = [allocation.execution_id for allocation in allocations]
        executions = {value.id: value for value in session.scalars(select(Execution).where(Execution.id.in_(execution_ids))).all()} if execution_ids else {}
        entry_value = exit_value = fees = commission = Decimal("0")
        for allocation in allocations:
            execution = executions.get(allocation.execution_id)
            if not execution:
                continue
            quantity = Decimal(allocation.quantity)
            entry_notional += quantity * Decimal(execution.price) if allocation.role == "open" else Decimal("0")
            fees += Decimal(execution.fees or 0) * quantity / Decimal(execution.quantity)
            commission += Decimal(execution.commission or 0) * quantity / Decimal(execution.quantity)
            if allocation.role == "open":
                entry_value += quantity * Decimal(execution.price)
            elif allocation.role == "close":
                exit_value += quantity * Decimal(execution.price)
        realized = (exit_value - entry_value) if trade.direction == "long" else (entry_value - exit_value)
        realized_values.append(realized - fees - commission)
    total_pnl = sum(realized_values, Decimal("0")) if realized_values else None
    latest_scores: dict[str, int] = {}
    for analysis, revision_id, _created_at in analyses:
        if analysis.score is not None and current_revisions.get(analysis.trade_id) == revision_id:
            latest_scores.setdefault(analysis.trade_id, analysis.score)
    scores = list(latest_scores.values())
    holdings = session.scalars(select(PortfolioHolding).where(PortfolioHolding.user_id == user_id)).all()
    portfolio_values = [Decimal(value.market_value) for value in holdings if value.market_value is not None]
    portfolio_value = sum(portfolio_values, Decimal("0")) if portfolio_values else None
    return {
        "total_pnl": float(total_pnl) if total_pnl is not None else None,
        "return_percent": float((total_pnl / entry_notional) * 100) if total_pnl is not None and entry_notional > 0 else None,
        "win_rate": round(sum(1 for value in realized_values if value > 0) / len(realized_values) * 100, 1) if realized_values else None,
        "discipline": round(sum(scores) / len(scores), 1) if scores else None,
        "portfolio_value": float(portfolio_value) if portfolio_value is not None else None,
        "closed_trades": len(realized_values),
        "reviewed_trades": len(scores),
    }


def public_profile_payload(session: Session, user: User) -> dict:
    return {
        "username": user.public_handle,
        "public_profile": user.public_profile,
        "display_name": user.display_name,
        "metrics": trade_metrics(session, user.id),
    }


def create_pair(session: Session, user_id: str) -> TokenPair:
    raw, hashed = new_refresh_token()
    session.add(RefreshSession(user_id=user_id, token_hash=hashed, expires_at=datetime.now(UTC) + timedelta(days=get_settings().refresh_token_days), revoked_at=None))
    session.commit()
    return TokenPair(access_token=access_token(user_id), refresh_token=raw)


@router.post("/auth/register", response_model=TokenPair, status_code=201)
def register(credentials: Credentials, session: Session = Depends(database)):
    email = credentials.email.lower()
    if session.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, detail={"code": "email_exists", "message": "An account already uses this email"})
    user = None
    for _ in range(5):
        handle = f"member-{secrets.token_hex(6)}"
        if not session.scalar(select(User.id).where(User.public_handle == handle)):
            user = User(email=email, public_handle=handle, password_hash=hash_password(credentials.password), created_at=datetime.now(UTC))
            session.add(user)
            break
    if user is None:
        raise HTTPException(503, detail={"code": "handle_unavailable", "message": "A public handle could not be assigned. Please try again."})
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(503, detail={"code": "handle_unavailable", "message": "A public handle could not be assigned. Please try again."}) from error
    return create_pair(session, user.id)


@router.post("/auth/login", response_model=TokenPair)
def login(credentials: Credentials, session: Session = Depends(database)):
    user = session.scalar(select(User).where(User.email == credentials.email.lower()))
    if not user or not verify_password(user.password_hash, credentials.password):
        raise HTTPException(401, detail={"code": "invalid_credentials", "message": "Email or password is incorrect"})
    return create_pair(session, user.id)


@router.post("/auth/refresh", response_model=TokenPair)
def refresh(request: RefreshRequest, session: Session = Depends(database)):
    current = session.scalar(select(RefreshSession).where(RefreshSession.token_hash == refresh_hash(request.refresh_token)))
    now = datetime.now(UTC)
    if not current or current.revoked_at or current.expires_at.replace(tzinfo=UTC) <= now:
        raise HTTPException(401, detail={"code": "invalid_refresh_token", "message": "Refresh session is invalid"})
    current.revoked_at = now
    session.commit()
    return create_pair(session, current.user_id)


@router.post("/auth/logout", status_code=204)
def logout(request: RefreshRequest, session: Session = Depends(database)):
    current = session.scalar(select(RefreshSession).where(RefreshSession.token_hash == refresh_hash(request.refresh_token)))
    if current and not current.revoked_at:
        current.revoked_at = datetime.now(UTC)
        session.commit()
    return Response(status_code=204)


@router.delete("/account", status_code=204)
def delete_account(user_id: str = Depends(current_user_id), session: Session = Depends(database)):
    trade_ids = select(Trade.id).where(Trade.user_id == user_id)
    run_ids = select(AnalysisRun.id).where(AnalysisRun.user_id == user_id)
    analysis_ids = select(TradeAnalysis.id).where(TradeAnalysis.trade_id.in_(trade_ids))
    revision_ids = select(TradeRevision.id).where(TradeRevision.trade_id.in_(trade_ids))
    execution_ids = select(Execution.id).where(Execution.user_id == user_id)
    batch_ids = select(ImportBatch.id).where(ImportBatch.user_id == user_id)
    session.execute(delete(RuleEvaluation).where(RuleEvaluation.trade_analysis_id.in_(analysis_ids)))
    session.execute(delete(TradeAnalysis).where(TradeAnalysis.run_id.in_(run_ids)))
    session.execute(delete(AnalysisRun).where(AnalysisRun.user_id == user_id))
    session.execute(delete(TradeRevisionAllocation).where(TradeRevisionAllocation.trade_revision_id.in_(revision_ids)))
    session.execute(update(Trade).where(Trade.user_id == user_id).values(current_revision_id=None))
    session.execute(delete(TradeRevision).where(TradeRevision.trade_id.in_(trade_ids)))
    session.execute(delete(Trade).where(Trade.user_id == user_id))
    session.execute(delete(ImportBatchExecution).where(ImportBatchExecution.import_batch_id.in_(batch_ids)))
    session.execute(delete(ImportBatch).where(ImportBatch.user_id == user_id))
    session.execute(delete(Execution).where(Execution.user_id == user_id))
    session.execute(delete(PortfolioHolding).where(PortfolioHolding.user_id == user_id))
    session.execute(delete(RefreshSession).where(RefreshSession.user_id == user_id))
    session.execute(delete(User).where(User.id == user_id))
    session.commit()
    return Response(status_code=204)


@router.put("/account/profile")
def update_profile(request: ProfileUpdate, user_id: str = Depends(current_user_id), session: Session = Depends(database)):
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(404, detail={"code": "not_found", "message": "Account was not found"})
    user.display_name = (request.display_name or "").strip()[:120] or None
    session.commit()
    return public_profile_payload(session, user)


@router.get("/account/profile")
def own_profile(user_id: str = Depends(current_user_id), session: Session = Depends(database)):
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(404, detail={"code": "not_found", "message": "Account was not found"})
    return public_profile_payload(session, user)


@router.post("/portfolio/import", status_code=201)
async def import_portfolio(file: UploadFile = File(), user_id: str = Depends(current_user_id), session: Session = Depends(database)):
    data = await file.read(get_settings().max_csv_bytes + 1)
    try:
        holdings = parse_holdings(data, file.filename, get_settings().max_csv_bytes, get_settings().max_csv_rows)
    except ImportValidationError as error:
        issue(error)
    scopes = {(value.source, value.account_reference) for value in holdings}
    existing_models = session.scalars(select(PortfolioHolding).where(PortfolioHolding.user_id == user_id)).all()
    existing = {(value.source, value.account_reference, value.symbol): value for value in existing_models}
    incoming_keys = {(value.source, value.account_reference, value.symbol) for value in holdings}
    imported_at = datetime.now(UTC)
    created = updated = 0
    for model in existing_models:
        if (model.source, model.account_reference) in scopes and (model.source, model.account_reference, model.symbol) not in incoming_keys:
            session.delete(model)
    for holding in holdings:
        key = (holding.source, holding.account_reference, holding.symbol)
        existing_holding = existing.get(key)
        if existing_holding is None:
            new_holding = PortfolioHolding(user_id=user_id, source=holding.source, account_reference=holding.account_reference, symbol=holding.symbol, description=holding.description, quantity=holding.quantity, price=holding.price, market_value=holding.market_value, cost_basis=holding.cost_basis, asset_type=holding.asset_type, imported_at=imported_at)
            session.add(new_holding)
            created += 1
        else:
            existing_holding.description = holding.description
            existing_holding.quantity = holding.quantity
            existing_holding.price = holding.price
            existing_holding.market_value = holding.market_value
            existing_holding.cost_basis = holding.cost_basis
            existing_holding.asset_type = holding.asset_type
            existing_holding.imported_at = imported_at
            updated += 1
    session.commit()
    value = portfolio_summary(session, user_id)
    return {"created": created, "updated": updated, "holding_count": len(holdings), "imported_at": imported_at.isoformat(), **value}


def portfolio_summary(session: Session, user_id: str) -> dict:
    holdings = session.scalars(select(PortfolioHolding).where(PortfolioHolding.user_id == user_id).order_by(PortfolioHolding.source, PortfolioHolding.symbol)).all()
    total = sum((Decimal(value.market_value) for value in holdings if value.market_value is not None), Decimal("0"))
    return {
        "portfolio_value": float(total) if holdings else None,
        "holdings": [{"id": value.id, "source": value.source, "account_reference": value.account_reference, "symbol": value.symbol, "description": value.description, "quantity": float(value.quantity), "price": float(value.price) if value.price is not None else None, "market_value": float(value.market_value) if value.market_value is not None else None, "cost_basis": float(value.cost_basis) if value.cost_basis is not None else None, "asset_type": value.asset_type, "imported_at": utc_value(value.imported_at).isoformat()} for value in holdings],
    }


@router.get("/portfolio")
def portfolio(user_id: str = Depends(current_user_id), session: Session = Depends(database)):
    return portfolio_summary(session, user_id)


@router.get("/accounts/search")
def search_accounts(q: str = "", user_id: str = Depends(current_user_id), session: Session = Depends(database)):
    query = " ".join(q.split()).casefold()
    if len(query) < 2:
        return []
    candidates = session.scalars(select(User).where(or_(User.id == user_id, User.public_profile.is_(True))).order_by(User.public_handle)).all()
    matches = [user for user in candidates if query in " ".join((user.public_handle or "").split()).casefold() or query in " ".join((user.display_name or "").split()).casefold()][:20]
    return [public_profile_payload(session, user) for user in matches]


@router.get("/accounts/{username}")
def account_profile(username: str, user_id: str = Depends(current_user_id), session: Session = Depends(database)):
    user = session.scalar(select(User).where(func.lower(User.public_handle) == username.strip().lower()))
    if not user or (user.id != user_id and not user.public_profile):
        raise HTTPException(404, detail={"code": "not_found", "message": "Profile was not found"})
    return public_profile_payload(session, user)


@router.put("/account/public-profile")
def set_public_profile(enabled: bool, user_id: str = Depends(current_user_id), session: Session = Depends(database)):
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(404, detail={"code": "not_found", "message": "Account was not found"})
    user.public_profile = enabled
    session.commit()
    return {"public_profile": enabled, "username": user.public_handle}


@router.post("/imports/preview")
async def preview_import(file: UploadFile = File(), user_id: str = Depends(current_user_id)):
    data = await file.read(get_settings().max_csv_bytes + 1)
    try:
        return preview(data, get_settings().max_csv_bytes, get_settings().max_csv_rows)
    except ImportValidationError as error:
        issue(error)


@router.post("/imports", status_code=201)
async def import_csv(file: UploadFile = File(), mapping: str = Form(), timezone: str | None = Form(None), user_id: str = Depends(current_user_id), session: Session = Depends(database)):
    data = await file.read(get_settings().max_csv_bytes + 1)
    try:
        mapping_value = json.loads(mapping)
        if not isinstance(mapping_value, dict) or not all(isinstance(key, str) and isinstance(value, str) for key, value in mapping_value.items()):
            raise ImportValidationError("invalid_mapping", "Mapping must be an object of field and column names", "mapping")
        parsed = parse_executions(data, mapping_value, timezone, get_settings().max_csv_bytes, get_settings().max_csv_rows)
    except ImportValidationError as error:
        issue(error)
    except json.JSONDecodeError as error:
        raise HTTPException(422, detail={"code": "invalid_mapping", "message": "Mapping must be valid JSON", "field": "mapping", "row": None}) from error
    batch = ImportBatch(user_id=user_id, display_name=safe_name(file.filename), file_hash=hashlib.sha256(data).hexdigest(), mapping=mapping_value, status="completed", created_at=datetime.now(UTC))
    session.add(batch)
    session.flush()
    existing = {value.fingerprint: value for value in session.scalars(select(Execution).where(Execution.user_id == user_id)).all()}
    accepted = []
    for value in parsed:
        execution: Execution | None = existing.get(value.fingerprint)
        was_inserted = execution is None
        if execution is None:
            execution = Execution(user_id=user_id, symbol=value.symbol, asset_type=value.asset_type, side=value.side, quantity=value.quantity, price=value.price, commission=value.commission, fees=value.fees, executed_at=value.executed_at, account_reference=value.account_reference, external_execution_id=value.external_execution_id, row_number=value.row_number, row_hash=value.row_hash, fingerprint=value.fingerprint)
            try:
                with session.begin_nested():
                    session.add(execution)
                    session.flush()
            except IntegrityError:
                execution = session.scalar(select(Execution).where(Execution.user_id == user_id, Execution.fingerprint == value.fingerprint))
                was_inserted = False
            assert execution is not None
            if was_inserted:
                accepted.append(value)
                existing[value.fingerprint] = execution
        assert execution is not None
        session.add(ImportBatchExecution(import_batch_id=batch.id, execution_id=execution.id, row_number=value.row_number, row_hash=value.row_hash, was_inserted=was_inserted))
    session.flush()
    trades, candidates = reconcile_user_trades(session, user_id, {value.fingerprint for value in accepted}) if accepted else (session.scalars(select(Trade).where(Trade.user_id == user_id)).all(), [])
    batch.execution_count = len(accepted)
    batch.trade_count = len(candidates)
    batch.duplicate_count = len(parsed) - len(accepted)
    session.commit()
    affected_trades = [{"trade_id": value["trade"].id, "trade_revision_id": value["revision_id"], "change_type": value["change_type"], "analysis_eligible": value["trade"].closed_at is not None, "symbol": value["trade"].symbol, "direction": value["trade"].direction, "opened_at": utc_value(value["trade"].opened_at).isoformat(), "closed_at": utc_value(value["trade"].closed_at).isoformat() if value["trade"].closed_at else None} for value in candidates]
    candidate_trades = [{"id": value["trade_id"], "trade_revision_id": value["trade_revision_id"], "symbol": value["symbol"], "direction": value["direction"], "opened_at": value["opened_at"], "closed_at": value["closed_at"]} for value in affected_trades if value["analysis_eligible"]]
    return {"id": batch.id, "status": batch.status, "created_at": utc_value(batch.created_at).isoformat(), "accepted_execution_count": batch.execution_count, "execution_count": batch.execution_count, "affected_trade_count": batch.trade_count, "trade_count": batch.trade_count, "duplicate_count": batch.duplicate_count, "error_count": 0, "affected_trades": affected_trades, "candidate_trades": candidate_trades, "trades": candidate_trades}


@router.get("/imports/{batch_id}")
def import_summary(batch_id: str, user_id: str = Depends(current_user_id), session: Session = Depends(database)):
    batch = session.scalar(select(ImportBatch).where(ImportBatch.id == batch_id, ImportBatch.user_id == user_id))
    if not batch:
        raise HTTPException(404, detail={"code": "not_found", "message": "Import was not found"})
    return {"id": batch.id, "display_name": batch.display_name, "status": batch.status, "accepted_execution_count": batch.execution_count, "affected_trade_count": batch.trade_count, "execution_count": batch.execution_count, "trade_count": batch.trade_count, "duplicate_count": batch.duplicate_count, "error_count": batch.error_count}


@router.get("/imports")
def import_history(user_id: str = Depends(current_user_id), session: Session = Depends(database)):
    batches = session.scalars(select(ImportBatch).where(ImportBatch.user_id == user_id).order_by(ImportBatch.created_at.desc()).limit(20)).all()
    return [{"id": batch.id, "display_name": batch.display_name, "status": batch.status, "accepted_execution_count": batch.execution_count, "affected_trade_count": batch.trade_count, "duplicate_count": batch.duplicate_count, "error_count": batch.error_count, "created_at": utc_value(batch.created_at).isoformat()} for batch in batches]


@router.get("/trades")
def trade_history(user_id: str = Depends(current_user_id), session: Session = Depends(database)):
    trades = session.scalars(select(Trade).where(Trade.user_id == user_id, Trade.active.is_(True)).order_by(Trade.opened_at.desc()).limit(200)).all()
    trade_ids = [trade.id for trade in trades]
    analyses = session.execute(select(TradeAnalysis, AnalysisRun.trade_revision_id).join(AnalysisRun, TradeAnalysis.run_id == AnalysisRun.id).where(TradeAnalysis.trade_id.in_(trade_ids)).order_by(TradeAnalysis.id.desc())).all() if trade_ids else []
    latest: dict[str, TradeAnalysis] = {}
    current_revisions = {trade.id: trade.current_revision_id for trade in trades}
    for analysis, revision_id in analyses:
        if current_revisions.get(analysis.trade_id) == revision_id:
            latest.setdefault(analysis.trade_id, analysis)
    revision_ids = [trade.current_revision_id for trade in trades if trade.current_revision_id]
    revisions = {value.id: value for value in session.scalars(select(TradeRevision).where(TradeRevision.id.in_(revision_ids))).all()} if revision_ids else {}
    allocations = session.scalars(select(TradeRevisionAllocation).where(TradeRevisionAllocation.trade_revision_id.in_(revision_ids))).all() if revision_ids else []
    allocations_by_revision: dict[str, list[TradeRevisionAllocation]] = {}
    for allocation in allocations:
        allocations_by_revision.setdefault(allocation.trade_revision_id, []).append(allocation)
    execution_ids = [allocation.execution_id for allocation in allocations]
    executions = {value.id: value for value in session.scalars(select(Execution).where(Execution.id.in_(execution_ids))).all()} if execution_ids else {}
    result = []
    for trade in trades:
        revision = revisions.get(trade.current_revision_id) if trade.current_revision_id else None
        trade_allocations = allocations_by_revision.get(trade.current_revision_id, []) if revision else []
        entry_value = exit_value = matched = fees = commission = Decimal("0")
        for allocation in trade_allocations:
            execution = executions.get(allocation.execution_id)
            if not execution:
                continue
            quantity = Decimal(allocation.quantity)
            fees += Decimal(execution.fees or 0) * quantity / Decimal(execution.quantity)
            commission += Decimal(execution.commission or 0) * quantity / Decimal(execution.quantity)
            matched += quantity
            if allocation.role == "open":
                entry_value += quantity * Decimal(execution.price)
            elif allocation.role == "close":
                exit_value += quantity * Decimal(execution.price)
        realized = (exit_value - entry_value) if trade.direction == "long" else (entry_value - exit_value)
        realized -= fees + commission
        realized_pnl = realized if trade.closed_at and matched and entry_value else None
        return_percent = (realized_pnl / entry_value * Decimal("100")) if realized_pnl is not None else None
        result.append({"trade_id": trade.id, "trade_revision_id": trade.current_revision_id, "analysis_eligible": trade.closed_at is not None, "symbol": trade.symbol, "direction": trade.direction, "opened_at": utc_value(trade.opened_at).isoformat(), "closed_at": utc_value(trade.closed_at).isoformat() if trade.closed_at else None, "analyzed": trade.id in latest, "score": latest[trade.id].score if trade.id in latest else None, "quantity": float(matched), "entry_price": float(entry_value / matched) if matched else None, "exit_price": float(exit_value / matched) if matched and exit_value else None, "realized_pnl": float(realized_pnl) if realized_pnl is not None else None, "fees": float(fees + commission), "return_percent": float(return_percent) if return_percent is not None else None})
    return result


@router.delete("/trades/{trade_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_trade(trade_id: str, user_id: str = Depends(current_user_id), session: Session = Depends(database)):
    trade = session.scalar(select(Trade).where(Trade.id == trade_id, Trade.user_id == user_id, Trade.active.is_(True)))
    if not trade:
        raise HTTPException(404, detail={"code": "not_found", "message": "Trade was not found"})
    trade.active = False
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/strategies/vwap-reclaim/default")
def default_strategy(user_id: str = Depends(current_user_id)):
    return DEFAULT_DEFINITION


async def perform_analysis(run_id: str, factory):
    session = factory()
    run = None
    try:
        run = session.get(AnalysisRun, run_id)
        trade = session.get(Trade, run.trade_id if run else None)
        revision = session.get(TradeRevision, run.trade_revision_id if run else None)
        if not run or not trade or not revision:
            return
        run.status = "running"
        run.started_at = datetime.now(UTC)
        session.commit()
        provider = configured_provider(get_settings())
        trade_time = utc_value(revision.opened_at)
        market_session = await provider.get_session(trade.symbol, trade_time)
        bars = await provider.get_bars(trade.symbol, market_session.opens_at, trade_time, "1min")
        opening = session.scalar(select(Execution).join(TradeRevisionAllocation).where(TradeRevisionAllocation.trade_revision_id == revision.id, TradeRevisionAllocation.role == "open").order_by(TradeRevisionAllocation.sequence))
        if not opening:
            raise RuntimeError("opening_execution_missing")
        strategy = session.get(StrategyVersion, run.strategy_version_id)
        if not strategy:
            raise RuntimeError("strategy_missing")
        payload = result_payload(evaluate(bars, trade_time, opening.price)) if strategy.slug == "vwap-reclaim" else catalog_payload(strategy.slug, bars, opening.price, revision.direction)
        method = "completed-minute VWAP/EMA/RVOL" if strategy.slug == "vwap-reclaim" else f"default {strategy.definition.get('engine', 'catalog')} rule profile"
        analysis = TradeAnalysis(run_id=run.id, trade_id=trade.id, score=payload["score"], data_sufficiency="sufficient" if payload["score"] is not None else "insufficient", feedback=payload["feedback"], derived_context={"timeframe": "1min", "completed_bars": len(bars), "method": method, "provider": provider.name})
        session.add(analysis)
        session.flush()
        for value in payload["rules"]:
            session.add(RuleEvaluation(trade_analysis_id=analysis.id, rule_key=value["rule"], result=value["result"], measurement=value["measurement"], threshold=value["threshold"], weight=value["weight"]))
        run.status = "completed"
        run.finished_at = datetime.now(UTC)
        session.commit()
    except Exception as error:
        session.rollback()
        run = session.get(AnalysisRun, run_id)
        if run:
            run.status = "failed"
            run.failure_code = getattr(error, "code", "analysis_failed")
            run.finished_at = datetime.now(UTC)
            session.commit()
    finally:
        session.close()


@router.post("/analysis-runs", status_code=status.HTTP_202_ACCEPTED)
def create_analysis(request: AnalysisRequest, tasks: BackgroundTasks, user_id: str = Depends(current_user_id), session: Session = Depends(database)):
    definition = DEFAULT_DEFINITION if request.strategy_slug == "vwap-reclaim" else definition_for(request.strategy_slug)
    if not definition:
        raise HTTPException(422, detail={"code": "strategy_unknown", "message": "Choose a strategy from the library."})
    trade = session.scalar(select(Trade).where(Trade.id == request.trade_id, Trade.user_id == user_id))
    if not trade:
        raise HTTPException(404, detail={"code": "not_found", "message": "Trade was not found"})
    revision_id = request.trade_revision_id or trade.current_revision_id
    revision = session.scalar(select(TradeRevision).where(TradeRevision.id == revision_id, TradeRevision.trade_id == trade.id))
    if not revision:
        raise HTTPException(404, detail={"code": "not_found", "message": "Trade revision was not found"})
    if revision.closed_at is None:
        raise HTTPException(409, detail={"code": "trade_open", "message": "A closing execution is required before analysis"})
    strategy = session.scalar(select(StrategyVersion).where(StrategyVersion.slug == request.strategy_slug, StrategyVersion.version == 1))
    if not strategy:
        strategy = StrategyVersion(slug=request.strategy_slug, version=1, definition=definition, created_at=datetime.now(UTC))
        session.add(strategy)
        session.flush()
    settings = get_settings()
    retry_of = None
    if request.retry_of_run_id:
        retry_of = session.scalar(select(AnalysisRun).where(AnalysisRun.id == request.retry_of_run_id, AnalysisRun.user_id == user_id, AnalysisRun.trade_revision_id == revision.id, AnalysisRun.status == "failed"))
        if not retry_of:
            raise HTTPException(409, detail={"code": "retry_invalid", "message": "Only a failed run for this revision can be retried"})
    else:
        reusable_runs = session.scalars(select(AnalysisRun).where(AnalysisRun.user_id == user_id, AnalysisRun.trade_revision_id == revision.id, AnalysisRun.strategy_version_id == strategy.id, AnalysisRun.provider == settings.market_data_provider, AnalysisRun.engine_version == f"{request.strategy_slug}-1", AnalysisRun.status.in_(["queued", "running", "completed"])).order_by(AnalysisRun.created_at.desc())).all()
        stale_runs = [run for run in reusable_runs if fail_stale_analysis_run(run, settings.analysis_run_stale_seconds)]
        if stale_runs:
            session.commit()
        reusable = next((run for run in reusable_runs if run.status in {"queued", "running", "completed"}), None)
        if reusable:
            return {"id": reusable.id, "status": reusable.status, "reused": True}
    run = AnalysisRun(user_id=user_id, trade_id=trade.id, trade_revision_id=revision.id, strategy_version_id=strategy.id, retry_of_run_id=retry_of.id if retry_of else None, provider=settings.market_data_provider, engine_version=f"{request.strategy_slug}-1", status="queued", failure_code=None, created_at=datetime.now(UTC), started_at=None, finished_at=None)
    session.add(run)
    session.commit()
    tasks.add_task(perform_analysis, run.id, sessionmaker(bind=session.get_bind(), expire_on_commit=False))
    return {"id": run.id, "status": run.status, "reused": False}


@router.get("/analysis-runs/{run_id}")
def analysis_run(run_id: str, user_id: str = Depends(current_user_id), session: Session = Depends(database)):
    run = session.scalar(select(AnalysisRun).where(AnalysisRun.id == run_id, AnalysisRun.user_id == user_id))
    if not run:
        raise HTTPException(404, detail={"code": "not_found", "message": "Analysis run was not found"})
    if fail_stale_analysis_run(run, get_settings().analysis_run_stale_seconds):
        session.commit()
    analysis = session.scalar(select(TradeAnalysis).where(TradeAnalysis.run_id == run.id))
    return {"id": run.id, "status": run.status, "failure_code": run.failure_code, "retryable": run.status == "failed", "retry_of_run_id": run.retry_of_run_id, "created_at": utc_value(run.created_at).isoformat(), "started_at": utc_value(run.started_at).isoformat() if run.started_at else None, "finished_at": utc_value(run.finished_at).isoformat() if run.finished_at else None, "trade_analysis_id": analysis.id if analysis else None}


@router.get("/trade-analyses/{analysis_id}")
def trade_analysis(analysis_id: str, user_id: str = Depends(current_user_id), session: Session = Depends(database)):
    analysis = session.scalar(select(TradeAnalysis).join(AnalysisRun).where(TradeAnalysis.id == analysis_id, AnalysisRun.user_id == user_id))
    if not analysis:
        raise HTTPException(404, detail={"code": "not_found", "message": "Trade analysis was not found"})
    rules = session.scalars(select(RuleEvaluation).where(RuleEvaluation.trade_analysis_id == analysis.id).order_by(RuleEvaluation.rule_key)).all()
    trade = session.get(Trade, analysis.trade_id)
    run = session.get(AnalysisRun, analysis.run_id)
    assert trade is not None
    assert run is not None
    strategy = session.get(StrategyVersion, run.strategy_version_id)
    revision = session.get(TradeRevision, run.trade_revision_id)
    assert strategy is not None
    assert revision is not None
    labels = {"prior_close_below_vwap": "Prior close below VWAP", "completed_close_reclaimed_vwap": "Completed close reclaimed VWAP", "entry_within_reclaim_bars": "Entry after reclaim", "ema_9_above_20": "EMA alignment", "reclaim_relative_volume": "Reclaim relative volume", "permitted_entry_time": "Permitted entry time", "maximum_vwap_extension": "VWAP extension", "market_history": "Market history"}
    return {"id": analysis.id, "trade_id": trade.id, "trade_revision_id": revision.id, "symbol": trade.symbol, "direction": revision.direction, "entry_time": utc_value(revision.opened_at).isoformat(), "strategy": {"slug": strategy.slug, "name": strategy.definition.get("name", "VWAP Reclaim"), "version": strategy.version}, "score": analysis.score, "data_sufficiency": analysis.data_sufficiency, "derived_context": analysis.derived_context, "rules": [{"rule": value.rule_key, "label": labels.get(value.rule_key, value.rule_key.replace("_", " ").title()), "result": value.result, "measurement": value.measurement, "threshold": value.threshold, "weight": value.weight} for value in rules], "feedback": analysis.feedback, "comparison": {"status": "insufficient_sample", "minimum": 20, "message": "At least 20 analyzed trades are required for comparison with your history."}}
