# Strategy Framework Taslağı

## Desteklenecek Strateji Modları
1. Trend Following
2. Mean Reversion
3. Breakout
4. Volatility Expansion

## Tasarım Prensibi
- Strategy modülleri execution motorundan bağımsızdır.
- Strategy çıktısı standart sinyal sözleşmesi üretir:
  - symbol
  - side
  - confidence
  - stop/tp önerisi

## Faz-1
- Strategy template CRUD aktif
- Canlı sinyal üretimi yok
