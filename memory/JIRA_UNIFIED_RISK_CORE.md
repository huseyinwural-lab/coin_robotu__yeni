# UNIFIED RISK CORE — Jira Epic + Task Breakdown

## Epic URC-P0 — Unified Risk Core
- URC-01 Canonical unified risk data model (position/account/symbol exposure/margin/leverage/capital/risk state)
- URC-02 Position-level liquidation engine (cross vs isolated, maintenance margin, margin ratio, liquidation price, buffer)
- URC-03 Portfolio risk engine (gross/net/directional/hedged/effective leverage)
- URC-04 Capital governance (equity, used margin, free collateral, strategy allocation, risk budget breach)
- URC-05 Unified risk state machine (NORMAL/WARN/HIGH/CRITICAL/BLOCKED)
- URC-06 Risk→execution policy object (block/reduce/pause/kill-switch policy only, no live order)
- URC-07 Risk snapshot artifacts (pre-trade, post-trade, portfolio-level)

## Epic URC-P2 (Early) — Orchestrator Skeleton
- URC-21 Single entrypoint contract: `risk_orchestrator`
- URC-22 Pre-trade simulation: before/after exposure, margin impact, liquidation buffer delta
- URC-23 Explainability/proof payload: decision + triggers + input summary + timestamp
- URC-24 Kill-switch mapping in policy layer

## Epic URC-P1 (Next Sprint) — Advanced Layer
- URC-31 Rolling correlation + cluster concentration hardening
- URC-32 Historical VaR/CVaR + stress scenario coverage expansion
- URC-33 Strategy risk budget throttle/pause policies hardening
- URC-34 Exchange abstraction hardening (ruleset/adapter driven, core code stable)

## Hard Constraints (Locked)
- No module can emit execution decision directly.
- All risk decisions must pass through `risk_orchestrator`.
- Live exchange connection is out of scope.
- Live order placement is out of scope.
- Validation mode: simulation/replay/mock-exchange-state.