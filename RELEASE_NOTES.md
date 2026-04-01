# Release Notes — Repo Hijyen Kapanışı

## Resmi Kaynaklar

- Resmi karar dosyası: `artifacts/final_release_gate_report.json`
- Resmi proof bundle: `artifacts/final/final_closure_proof_bundle.zip`

## Artifact Retention Modeli

- `artifacts/final/`: tek resmi kapanış/proof çıktıları
- `artifacts/latest/`: son çalışan snapshotlar
- `artifacts/archive/obsolete/`: superseded/çelişkili eski karar özetleri
- `artifacts/archive/history/`: geçmiş rapor geçmişi

## Kullanım Dışı Kabul Edilenler

- Eski faz gate summary/no-go özetleri
- Tekrarlı canary/daily smoke snapshot serileri
- Root seviyesinde tek kullanımlık test/debug scriptleri
