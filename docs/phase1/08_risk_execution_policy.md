# Risk ve Execution Policy (Phase-1)

## Risk Katmanı
- Position sizing
- ATR tabanlı stop loss parametresi
- Risk/Reward oranı
- Daily loss cutoff
- Max open positions
- Spread/slippage limit alanları
- Liquidity minimum alanı
- Futures leverage üst limiti

## Execution Katmanı
- Phase-1 execution mode: MOCK
- Gerçek emir iletimi kapalı
- Her mock execution audit log + execution event üretir

## Admin Kontrolleri
- STOP ALL BOTS
- Disable Futures
- Force Close All Positions
- Emergency Risk Mode

Bu aksiyonlar UI'da çift onay (double confirmation) ile tetiklenir.
