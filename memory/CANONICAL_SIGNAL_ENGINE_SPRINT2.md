# Canonical Signal Engine — Sprint-2 Tasarım Dokümanı

## 1) Pseudo-code

```pseudo
load_enabled_strategies_from_registry()
for each symbol in tradable_universe:
    candles = load_15m_candles(symbol)
    if candles insufficient: continue

    indicators = compute_indicators(candles)
    regime = detect_market_regime(indicators, candles)

    long_score = 0
    short_score = 0
    contributors = []

    for each strategy in enabled_strategies:
        if strategy.market_regime != any and strategy.market_regime != regime:
            continue

        result = strategy.evaluate(candles, indicators)
        weighted_long = result.long_score * strategy.weight
        weighted_short = result.short_score * strategy.weight

        apply_direction_mode(strategy.direction, weighted_long, weighted_short)

        long_score += weighted_long
        short_score += weighted_short
        contributors.append({strategy_id, weighted_long, weighted_short, reasons})

    signal = resolve_direction(long_score, short_score, threshold=5, reject=2)
    top_source = pick_top_contributor(contributors, signal)
    stop, tp = build_levels(signal, entry, atr, top_source.contract)

    emit_symbol_intent(symbol, signal, long_score, short_score, top_source, stop, tp, contributors)

rank_intents_by(score)
apply_global_risk_gate(max_positions=5, cooldown_symbol=6h, risk_per_trade=1.5%)
persist_pending_signals_and_decision_traces()
```

---

## 2) Veri Akışı

1. **Canonical Registry (DB)**
   - `canonical_strategy_registry` tablosundan aktif stratejiler çekilir.

2. **Market Data Layer**
   - Universe: `universe:spot:tradable`
   - Candle cache: `market_data_store:{symbol}:15m`

3. **Strategy Evaluation Layer**
   - 12 strategy evaluator (deterministik kural seti)
   - Long/Short skorlar ayrı hesaplanır

4. **Master Scoring Layer**
   - `aggregate_long = sum(weighted_long)`
   - `aggregate_short = sum(weighted_short)`
   - Threshold/reject conflict çözümü

5. **Risk & Invalidation Layer**
   - max_positions
   - symbol cooldown
   - risk_per_trade cap
   - opposite-direction conflict block

6. **Intent Output Layer**
   - PendingSignal / SignalEvent
   - Decision trace + audit
   - Admin metrics refresh (quality, false allow/reject, cooldown state)

---

## 3) Strategy Class Mimarisi (Uygulanabilir Şablon)

```python
class StrategyContract:
    strategy_id: str
    family: str
    regime: str
    direction_mode: Literal["long", "short", "both"]
    weight: float
    entry_long: dict
    entry_short: dict
    exit_long: dict
    exit_short: dict
    stop_loss: dict
    take_profit: dict
    invalidation: dict
    signal_score: dict


class StrategyEvaluator:
    def evaluate(self, candles: list[dict], indicators: dict) -> EvalResult:
        # deterministic long_score/short_score
        ...


class EvalResult:
    long_score: float
    short_score: float
    reasons: list[str]
    invalidated: bool


class MasterSignalEngine:
    def run_symbol(self, symbol: str, candles: list[dict], contracts: list[StrategyContract]) -> SymbolIntent:
        ...


class SymbolIntent:
    symbol: str
    signal: Literal["long", "short", "none"]
    long_score: float
    short_score: float
    top_source_strategy_id: str
    stop_loss: float
    take_profit: float
    contributors: list[dict]
```

---

## 4) Sprint-2 Notları

- Contract fields tüm 12 strateji için registry’de tutulur.
- Aktivasyon politikası: 12 tanımlı, yalnız 4 aktif.
- Global risk enforce runtime’da uygulanır.
