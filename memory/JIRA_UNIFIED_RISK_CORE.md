# UNIFIED RISK CORE — Jira Epic + Task Breakdown

## Epic URC-P0 — Unified Risk Core ✅ Done
- URC-01 Canonical unified risk data model (position/account/symbol exposure/margin/leverage/capital/risk state)
- URC-02 Position-level liquidation engine (cross vs isolated, maintenance margin, margin ratio, liquidation price, buffer)
- URC-03 Portfolio risk engine (gross/net/directional/hedged/effective leverage)
- URC-04 Capital governance (equity, used margin, free collateral, strategy allocation, risk budget breach)
- URC-05 Unified risk state machine (NORMAL/WARN/HIGH/CRITICAL/BLOCKED)
- URC-06 Risk→execution policy object (block/reduce/pause/kill-switch policy only, no live order)
- URC-07 Risk snapshot artifacts (pre-trade, post-trade, portfolio-level)

## Epic URC-P1 — Advanced Risk Layer ✅ Done in Sprint-2
- URC-31 Rolling correlation windows (30/60/120) + symbol-level matrix
- URC-32 Cluster grouping + concentration + directional stacking
- URC-33 Tail risk engine (Historical VaR/CVaR + stress scenarios)
- URC-34 Strategy risk budget governance (throttle/pause/block)
- URC-35 Ruleset deepening (tier-based maintenance + leverage brackets + collateral haircuts)
- URC-36 Explainability expansion (decision reasons + metrics)

## Epic URC-P2 (Early) — Orchestrator Skeleton ✅ Done
- URC-21 Single entrypoint contract: `risk_orchestrator`
- URC-22 Pre-trade simulation: before/after exposure, margin impact, liquidation buffer delta
- URC-23 Explainability/proof payload: decision + triggers + input summary + timestamp
- URC-24 Kill-switch mapping in policy layer

## Component Map (Sprint-2)

### Reused modüller
- `services.unified_risk_core_service.run_unified_risk_orchestrator` (tek giriş kararı korunarak genişletildi)
- `services.audit_service.create_audit_log`
- Snapshot manifest/artifact altyapısı (`/app/artifacts/...`)

### Refactor edilenler
- `unified_risk_core_service` içinde:
  - liquidation hesapları (tier-based ruleset)
  - risk state machine (P1 metrik etkisi)
  - explainability payload (reason/metrics/policy_result)
- Jira breakdown çıktısı (`jira_epic_breakdown`) Sprint-2 kapsamına güncellendi

### Yeni eklenenler
- Rolling correlation + cluster risk engine
- Tail risk engine (VaR/CVaR + 4 zorunlu stress scenario)
- Strategy risk governance (throttle/pause/block)
- Symbol-specific ruleset derinliği (binance/bybit)
- P1 zorunlu scenario testleri (pytest)

## Hard Constraints (Locked)
- No module can emit execution decision directly.
- All risk decisions must pass through `risk_orchestrator`.
- Live exchange connection is out of scope.
- Live order placement is out of scope.
- Validation mode: simulation/replay/mock-exchange-state.