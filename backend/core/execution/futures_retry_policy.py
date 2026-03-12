class FuturesRetryPolicy:
    RETRYABLE_CODES = {"TIMEOUT", "RATE_LIMIT", "NETWORK_ERROR", "EXCHANGE_5XX"}
    NON_RETRYABLE_CODES = {"INVALID_ORDER", "INSUFFICIENT_MARGIN", "REDUCE_ONLY_REJECTED"}

    def classify(self, error_code: str) -> dict:
        code = (error_code or "UNKNOWN").upper()
        if code in self.RETRYABLE_CODES:
            return {"should_retry": True, "action": "retry", "reason": code}
        if code == "DUPLICATE_CLIENT_ORDER":
            return {"should_retry": False, "action": "reconcile", "reason": code}
        if code in self.NON_RETRYABLE_CODES:
            return {"should_retry": False, "action": "fail_fast", "reason": code}
        return {"should_retry": False, "action": "manual_review", "reason": code}

    def next_backoff_seconds(self, attempt: int, error_code: str) -> float:
        decision = self.classify(error_code)
        if not decision["should_retry"]:
            return 0.0
        safe_attempt = max(1, int(attempt))
        base = 0.7 if error_code.upper() == "RATE_LIMIT" else 0.4
        delay = min(8.0, base * (2 ** (safe_attempt - 1)))
        return round(delay, 3)
