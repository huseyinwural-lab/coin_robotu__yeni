import csv
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from models import BotProfile, PaperPosition

REPORT_GENERATOR_VERSION = "pg01_v1"
ARTIFACT_ROOT = Path("/app/artifacts/reports")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _week_range(week: str | None = None) -> tuple[datetime, datetime, str]:
    now = datetime.now(timezone.utc)
    if week:
        year_str, week_str = week.split("-W")
        year = int(year_str)
        week_num = int(week_str)
        week_start = datetime.fromisocalendar(year, week_num, 1).replace(tzinfo=timezone.utc)
    else:
        week_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    week_end = week_start + timedelta(days=7)
    week_label = f"{week_start.isocalendar().year}-W{week_start.isocalendar().week:02d}"
    return week_start, week_end, week_label


def _compute_drawdown(values: list[float]) -> float:
    peak = 0.0
    current = 0.0
    max_drawdown = 0.0
    for pnl in values:
        current += pnl
        peak = max(peak, current)
        drawdown = peak - current
        max_drawdown = max(max_drawdown, drawdown)
    return round(max_drawdown, 4)


def _write_pdf_fallback(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines), encoding="utf-8")


def generate_weekly_user_report(db: Session, user_id: str, week: str | None = None) -> dict:
    week_start, week_end, week_label = _week_range(week)
    report_seed = f"{user_id}:{week_start.isoformat()}:{week_end.isoformat()}"
    report_id = hashlib.sha256(report_seed.encode()).hexdigest()[:16]
    report_dir = ARTIFACT_ROOT / user_id / report_id
    report_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = report_dir / "report_manifest.json"
    if manifest_path.exists():
        return json.loads(manifest_path.read_text(encoding="utf-8"))

    closed_positions = (
        db.query(PaperPosition)
        .filter(
            PaperPosition.user_id == user_id,
            PaperPosition.status != "open",
            PaperPosition.closed_at.is_not(None),
            PaperPosition.closed_at >= week_start,
            PaperPosition.closed_at < week_end,
        )
        .order_by(PaperPosition.closed_at.asc())
        .all()
    )
    open_positions = (
        db.query(PaperPosition)
        .filter(PaperPosition.user_id == user_id, PaperPosition.status == "open")
        .all()
    )

    trade_pnls = [float(item.realized_pnl or 0) for item in closed_positions]
    gross_pnl = round(sum(pnl for pnl in trade_pnls if pnl > 0), 4)
    gross_loss = round(abs(sum(pnl for pnl in trade_pnls if pnl < 0)), 4)
    net_pnl = round(sum(trade_pnls), 4)
    wins = len([p for p in trade_pnls if p > 0])
    losses = len([p for p in trade_pnls if p < 0])
    total = len(trade_pnls)
    win_rate = round((wins / total) * 100, 2) if total else 0.0
    loss_rate = round((losses / total) * 100, 2) if total else 0.0
    max_drawdown = _compute_drawdown(trade_pnls)
    unrealized_snapshot = round(sum(float(item.unrealized_pnl or 0) for item in open_positions), 4)

    durations = []
    for row in closed_positions:
        if row.closed_at and row.opened_at:
            durations.append((row.closed_at - row.opened_at).total_seconds() / 3600)
    average_holding_time = round(sum(durations) / len(durations), 2) if durations else 0.0

    best_trade = round(max(trade_pnls), 4) if trade_pnls else 0.0
    worst_trade = round(min(trade_pnls), 4) if trade_pnls else 0.0

    strategy_contribution: dict[str, float] = {}
    symbol_contribution: dict[str, float] = {}
    bot_profiles = {row.id: row for row in db.query(BotProfile).filter(BotProfile.user_id == user_id).all()}
    for row in closed_positions:
        strategy_name = bot_profiles.get(row.bot_profile_id).strategy_type if row.bot_profile_id in bot_profiles else "unknown"
        strategy_contribution[strategy_name] = round(strategy_contribution.get(strategy_name, 0.0) + float(row.realized_pnl or 0), 4)
        symbol_contribution[row.symbol] = round(symbol_contribution.get(row.symbol, 0.0) + float(row.realized_pnl or 0), 4)

    csv_path = report_dir / "weekly_trades.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["trade_id", "symbol", "side", "entry_price", "closed_at", "realized_pnl"])
        for row in closed_positions:
            writer.writerow([row.id, row.symbol, row.side, row.entry_price, row.closed_at.isoformat() if row.closed_at else "", row.realized_pnl])

    stats_payload = {
        "report_id": report_id,
        "week": week_label,
        "weekly_pnl": net_pnl,
        "gross_pnl": gross_pnl,
        "gross_loss": gross_loss,
        "net_pnl": net_pnl,
        "win_rate": win_rate,
        "loss_rate": loss_rate,
        "max_drawdown": max_drawdown,
        "average_holding_time": average_holding_time,
        "best_trade": best_trade,
        "worst_trade": worst_trade,
        "strategy_contribution": strategy_contribution,
        "symbol_contribution": symbol_contribution,
        "unrealized_snapshot": unrealized_snapshot,
        "trades_count": total,
    }
    stats_path = report_dir / "weekly_strategy_stats.json"
    stats_path.write_text(json.dumps(stats_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    pdf_path = report_dir / "weekly_performance_report.pdf"
    _write_pdf_fallback(
        pdf_path,
        [
            f"Weekly Report {week_label}",
            f"Report ID: {report_id}",
            f"Net PnL: {net_pnl}",
            f"Win Rate: {win_rate}%",
            f"Max Drawdown: {max_drawdown}",
            f"Avg Holding Time(h): {average_holding_time}",
        ],
    )

    artifacts = {
        "weekly_performance_report.pdf": str(pdf_path),
        "weekly_trades.csv": str(csv_path),
        "weekly_strategy_stats.json": str(stats_path),
    }
    sha_payload = {name: _sha256(Path(path)) for name, path in artifacts.items()}

    manifest = {
        "report_id": report_id,
        "user_id": user_id,
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "artifact_files": artifacts,
        "sha256": sha_payload,
        "generator_version": REPORT_GENERATOR_VERSION,
        "summary": {
            "weekly_pnl": net_pnl,
            "gross_pnl": gross_pnl,
            "gross_loss": gross_loss,
            "net_pnl": net_pnl,
            "win_rate": win_rate,
            "loss_rate": loss_rate,
            "max_drawdown": max_drawdown,
            "average_holding_time": average_holding_time,
            "best_trade": best_trade,
            "worst_trade": worst_trade,
            "strategy_contribution": strategy_contribution,
            "symbol_contribution": symbol_contribution,
            "unrealized_snapshot": unrealized_snapshot,
            "status": "ready" if total else "empty_week",
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest