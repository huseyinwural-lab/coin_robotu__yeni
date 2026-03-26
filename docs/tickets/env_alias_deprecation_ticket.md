# Ticket: Env Alias Deprecation (1 Sprint)

## Kapsam
- Canonical backend env:
  - `BACKEND_INTERNAL_URL`
  - `BACKEND_PUBLIC_URL`
- Frontend env:
  - `REACT_APP_BACKEND_URL`

## Geçici Compatibility (1 sprint)
- `REACT_APP_BACKEND_URL` backend script/cli tarafında fallback olarak geçici kabul.
- Sprint sonunda fallback kaldırılacak.

## Kapatma Kriteri
- Script/CLI kodunda yalnız canonical backend env kullanımı.
- Compatibility katmanı silinmiş olacak.
