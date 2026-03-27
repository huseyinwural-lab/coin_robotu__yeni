from core.execution.futures_execution_contract import FuturesExecutionRequest


class FuturesOrderPreflight:
    def evaluate(self, request: FuturesExecutionRequest, context: dict) -> dict:
        checks: list[dict] = []

        active_symbols = {str(item).upper() for item in (context.get("active_symbols") or [])}
        symbol_active = not active_symbols or request.symbol in active_symbols
        checks.append({"key": "symbol_active", "pass": symbol_active, "reason": "SYMBOL_INACTIVE" if not symbol_active else "PASS"})

        leverage_cap = float(context.get("max_trade_leverage") or 5.0)
        leverage_valid = float(request.leverage) <= leverage_cap
        checks.append(
            {
                "key": "leverage_cap",
                "pass": leverage_valid,
                "reason": "RISK_LEVERAGE_LIMIT" if not leverage_valid else "PASS",
            }
        )

        quantity_valid = float(request.quantity) > 0
        checks.append({"key": "quantity_valid", "pass": quantity_valid, "reason": "INVALID_QUANTITY" if not quantity_valid else "PASS"})

        position_qty = float(context.get("current_position_qty") or 0.0)
        position_side = str(context.get("current_position_side") or "NONE").upper()
        reduce_only_valid = True
        if request.reduce_only:
            if position_qty <= 0:
                reduce_only_valid = False
            elif position_side == "LONG" and request.side == "BUY":
                reduce_only_valid = False
            elif position_side == "SHORT" and request.side == "SELL":
                reduce_only_valid = False
        checks.append(
            {
                "key": "reduce_only_consistency",
                "pass": reduce_only_valid,
                "reason": "REDUCE_ONLY_INCONSISTENT" if not reduce_only_valid else "PASS",
            }
        )

        margin_available = float(context.get("margin_available") or 0.0)
        margin_required = float(context.get("margin_required") or 0.0)
        margin_valid = margin_available >= margin_required
        checks.append(
            {
                "key": "margin_available",
                "pass": margin_valid,
                "reason": "INSUFFICIENT_MARGIN" if not margin_valid else "PASS",
            }
        )

        testnet_enabled = bool(context.get("testnet_mode_enabled", False))
        checks.append(
            {
                "key": "testnet_mode_enabled",
                "pass": testnet_enabled,
                "reason": "TESTNET_MODE_DISABLED" if not testnet_enabled else "PASS",
            }
        )

        release_gate_status = str(context.get("release_gate_status") or "BLOCKED").upper()
        release_gate_pass = release_gate_status in {"PASS", "PASS_WITH_WARNINGS"}
        checks.append(
            {
                "key": "release_gate",
                "pass": release_gate_pass,
                "reason": "RELEASE_GATE_BLOCKED" if not release_gate_pass else "PASS",
            }
        )

        go_live_validator = context.get("go_live_validator")
        env = str(context.get("environment") or "").lower()
        if go_live_validator and env in {"live", "prod", "production"}:
            allowed = bool(go_live_validator.get("execution_allowed"))
            checks.append(
                {
                    "key": "go_live_validator",
                    "pass": allowed,
                    "reason": "GO_LIVE_BLOCKED" if not allowed else "PASS",
                }
            )

        environment = str(context.get("environment") or "testnet").lower()
        live_endpoint_forbidden = environment == "testnet"
        checks.append(
            {
                "key": "live_endpoint_block",
                "pass": live_endpoint_forbidden,
                "reason": "LIVE_ENDPOINT_FORBIDDEN" if not live_endpoint_forbidden else "PASS",
            }
        )

        passed = all(item["pass"] for item in checks)
        return {
            "preflight_pass": passed,
            "reason_code": next((item["reason"] for item in checks if not item["pass"]), "PASS"),
            "checks": checks,
        }
