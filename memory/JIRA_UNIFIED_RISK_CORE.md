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

## Epic URC-P2 Hardening + Calibration ✅ Done in Sprint-3
- URC-41 Multi-factor kill-switch matrix
- URC-42 Scenario pack engine (reusable + deterministic)
- URC-43 Calibration layer (threshold optimization)
- URC-44 Replay engine (time-step timeline + export)
- URC-45 Policy stability guard (hysteresis)
- URC-46 Explainability root-cause chain

## Component Map (Sprint-3)

### Reused modüller
- `run_unified_risk_orchestrator` (tek entry kontratı korunarak hardening)
- Snapshot manifest altyapısı (calibration/replay input kaynağı olarak)

### Refactor edilenler
- Risk state machine (threshold-driven + hysteresis + kill-switch entegrasyonu)
- Explainability çıktısı (root_cause + chain)
- API router (`strategy_domain`) unified-core alt rotaları genişletildi

### Yeni eklenenler
- Scenario pack kütüphanesi (`SCENARIO_PACK_FILE`)
- Calibration engine + persisted thresholds (`CALIBRATION_FILE`)
- Replay timeline + export artefact
- Multi-factor kill-switch matrix
- Sprint-3 scenario test seti (`test_unified_risk_core_sprint3.py`)

## Epic URC-P2 Policy Benchmark + Drift Control ✅ Done in Sprint-4
- URC-51 Policy benchmark runner (A/B/C)
- URC-52 Policy scoring model (strategy-class aware)
- URC-53 Drift monitor (threshold + kill-switch frequency)
- URC-54 Regime-aware benchmark results
- URC-55 Offline recommended policy output
- URC-56 Benchmark report/compare API

## Component Map (Sprint-4)

### Reused modüller
- `run_unified_risk_orchestrator` (benchmark evaluate çekirdeği)
- Scenario pack / calibration dosya altyapısı (Sprint-3)

### Refactor edilenler
- Unified service içinde threshold/metric tüketimi benchmark scoring’e bağlandı
- Router’da unified-core benchmark/drift endpointleri eklendi

### Yeni eklenenler
- Policy benchmark runner + persisted benchmark run artefact
- Policy scoring fonksiyonu (regime/strategy-class aware)
- Drift monitor raporu (`/drift/status`)
- Benchmark report + compare fonksiyonları
- Sprint-4 test seti (`test_unified_risk_core_sprint4.py`)

## Hard Constraints (Locked)
- No module can emit execution decision directly.
- All risk decisions must pass through `risk_orchestrator`.
- Live exchange connection is out of scope.
- Live order placement is out of scope.
- Validation mode: simulation/replay/mock-exchange-state.