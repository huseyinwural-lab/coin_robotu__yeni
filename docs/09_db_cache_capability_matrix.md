# DB/Cache Capability Matrix

## PostgreSQL Mode (Primary)
- Alembic migration zinciri tek şema otoritesidir.
- Transaction semantiği ve eşzamanlılık davranışı production referansıdır.
- Kalıcı veri bütünlüğü (audit, learning memory, runtime trace, scanner persistence) PostgreSQL üzerinde garanti edilir.

## embeddeddb Mode (Fallback)
- Yalnız geliştirme/preview/debug için kabul edilir.
- Alembic migration uygulanır; startup ad hoc schema patch çalışmaz.
- Yüksek eşzamanlılık ve production-grade transaction davranışı PostgreSQL ile birebir değildir.
- Büyük hacimli runtime altında performans kıyas sonucu production kararı için kullanılamaz.

## Redis Mode (Primary Cache/Coordination)
- TTL, lock, cooldown, duplicate suppression davranışı referans cache semantiğidir.
- Queue/backpressure yardımcı state verileri Redis üzerinde beklenen şekilde yaşar/süresi dolar.

## In-Memory Cache Mode (Fallback)
- Redis erişilemezse devreye girer.
- TTL semantiği uygulanır (expire + key eviction).
- Süreç yeniden başlatıldığında tüm cache/state kaybolur.
- Çok-instance dağıtık koordinasyon davranışı garanti edilmez.

## Production İçin Desteklenmeyen Modlar
- embeddeddb + In-memory cache kombinasyonu production dağıtım modu olarak kabul edilmez.
- Fallback modları yalnız lokal geliştirme, preview ve teşhis amaçlıdır.

## Operasyonel Kural
- Production release gate değerlendirmesinde PostgreSQL + Redis zorunludur.
- Fallback modunda alınan davranış doğrulamaları, production eşdeğeri kabul edilmeden önce primary stack üzerinde tekrar doğrulanmalıdır.