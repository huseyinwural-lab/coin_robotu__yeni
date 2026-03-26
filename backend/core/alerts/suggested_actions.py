SUGGESTED_ACTIONS = {
    "runtime_pnl_drop": {
        "suggested_action": "Pozisyon büyüklüğünü azalt, risk limitini doğrula ve ilgili kullanıcı işlemlerini incele.",
        "runbook_hint": "runtime_pnl_drop_investigation",
    },
    "runtime_daily_smoke_degraded": {
        "suggested_action": "Ingest credential bilgisini kontrol et ve smoke zincirini manuel tekrar çalıştır.",
        "runbook_hint": "smoke_ingest_credentials_missing",
    },
    "runtime_queue_depth_high": {
        "suggested_action": "Worker health durumunu ve Redis backlog birikimini kontrol et.",
        "runbook_hint": "queue_backlog_triage",
    },
    "runtime_failed_orders_high": {
        "suggested_action": "Reject reason dağılımını ve adapter route davranışını incele.",
        "runbook_hint": "execution_failure_spike_analysis",
    },
    "runtime_daily_loss_limit": {
        "suggested_action": "Kullanıcı günlük zarar limitini aştı; trading akışını geçici durdurup risk ayarlarını gözden geçir.",
        "runbook_hint": "daily_loss_limit_breach",
    },
}


def get_suggested_action(alert_type: str) -> dict:
    return SUGGESTED_ACTIONS.get(
        str(alert_type or "").strip(),
        {
            "suggested_action": "Alert detaylarını incele, root cause ve son işlemleri doğrulayarak gerekli operasyon aksiyonunu uygula.",
            "runbook_hint": "generic_runtime_triage",
        },
    )
