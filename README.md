# Rule Mirror

Rule Mirror is an educational trading-journal platform designed to make post-trade review more structured, transparent, and useful. It turns user-owned brokerage exports into an auditable record of executions, reconstructed trades, portfolio holdings, and historical strategy review.

## Product vision

Most trading tools optimize for what happens next. Rule Mirror focuses on understanding what already happened. The product gives people a calm, evidence-based workspace for reviewing process, documenting decisions, and identifying patterns in their own records without pretending that past performance predicts future results.

## What makes it distinctive

- **Evidence-first review:** Imported executions remain traceable to their source rows, timestamps, quantities, prices, and order identifiers.
- **Deterministic analysis:** Trade reconstruction, realized P/L, return percentages, win rate, and discipline metrics are calculated from normalized records and explicit strategy rules.
- **Broker-aware resilience:** The importer recognizes common brokerage export conventions, including Charles Schwab Order Status and holdings formats, while providing structured validation for ambiguous or incomplete files.
- **Separation of concerns:** Executions, reconstructed trades, and `My portfolio` holdings are modeled separately so a position snapshot cannot silently become a strategy-scored trade.
- **Privacy by design:** Public profiles use opaque handles, expose only intentionally shared metrics, and keep raw trade and account data private.
- **Trustworthy states:** Import timestamps, data-source status, result limits, stale analysis detection, request IDs, and accessible loading/error states make system behavior visible instead of mysterious.

## Engineering profile

Rule Mirror is a full-stack product built around clear boundaries and maintainable domain logic:

- **FastAPI and SQLAlchemy:** typed API routes, authentication, ownership checks, profile privacy, persistence, and operational health reporting.
- **Alembic migrations:** explicit schema evolution for durable user, execution, trade, portfolio, analysis, and strategy data.
- **Deterministic import pipeline:** CSV detection, alias mapping, strict numeric and timestamp parsing, timezone normalization, atomic validation, broker-specific handling, and idempotent fingerprints.
- **Trade reconstruction engine:** execution matching that preserves revisions, allocations, open positions, historical analyses, and realized outcomes.
- **TypeScript web client:** responsive dashboard surfaces for analysis, trades, portfolio, account search, profiles, settings, legal content, and clear empty/loading/error/success states.
- **Flutter/iOS client:** a native companion experience with shared API contracts, refreshable data, trade deletion, search, accessibility semantics, session recovery, and the same restrained forest-green visual language.
- **Security and observability:** secure response headers, API cache controls, request identifiers, bounded uploads, sanitized avatars, safe browser-storage fallbacks, and intentionally minimal health disclosure.

## Responsible scope

Rule Mirror is for education, journaling, and historical self-review. It does not place orders, automate trading, recommend securities, predict returns, redistribute raw market data, or provide financial, legal, tax, brokerage, or fiduciary advice. A discipline score describes alignment with a selected historical rule profile; it is not a measure of investment quality or a promise of future performance.

Users are responsible for the accuracy of their exports, the permissions associated with uploaded files, and the decisions they make outside the product.

## Selected product capabilities

### Review and analysis

Users can select a strategy profile, upload execution history, inspect reconstructed trades, and review the calculation context behind historical results. Completed analyses remain tied to the trade revision they evaluated, preventing later imports from silently rewriting the audit record.

### P/L and portfolio context

Closed trades can show realized profit or loss, return percentage based on matched entry notional, and portfolio context. Holdings imports remain available in `My portfolio`, with source-aware values and visible synchronization times.

### Public profile controls

Users can choose whether selected metrics appear on an opaque public handle. Shared profiles can include P/L, win rate, discipline, strategy performance, and portfolio value only when the corresponding visibility setting is enabled. Email addresses and raw holdings are not public profile fields.

### Import quality

The import flow is intentionally strict where ambiguity could corrupt an audit. It accepts common currency and quantity notation, broker-specific headers, date-first and time-first timestamps, daylight-saving-aware timezone conversion, and split portfolio sources. Invalid rows produce structured feedback without partially writing an import.

## Repository shape

```text
backend/             API, domain models, migrations, import and analysis engines
web/                 TypeScript dashboard and responsive product UI
clients/ios_flutter/ Native Flutter client and shared mobile flows
scripts/              Operational helpers for the application environment
LICENSE               Source-available evaluation and demonstration terms
```

## Why this is a strong engineering portfolio

Rule Mirror demonstrates more than a polished interface. It shows how product decisions, data integrity, privacy, accessibility, and operational clarity can be designed together in a domain where users need to trust the record before they trust the insight.

The codebase includes real domain constraints rather than demo-only happy paths: malformed broker data, duplicate and stale analyses, timezone edge cases, revision-aware metrics, public/private boundaries, session expiry, partial browser storage, capped result sets, and mobile/web parity. The result is a product foundation that is both approachable to use and serious about the consequences of incorrect financial records.

## Contact

For product or project inquiries, contact **silas@rulemirror.com**.

## License

Rule Mirror is source-available for evaluation and demonstration. It is proprietary and not open source. See `LICENSE` for the governing terms.
