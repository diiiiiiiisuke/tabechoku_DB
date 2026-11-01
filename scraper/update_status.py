"""日次取得の成否を公開する。取得できなかった日付をデータに追加しない。"""
import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JST = timezone(timedelta(hours=9))


def make_status(outcome, snapshots, now=None, run_url="", report=None):
    now = now or datetime.now(JST)
    today = now.astimezone(JST).date()
    cutoff = (today - timedelta(days=1)).isoformat()
    dates = sorted(path.stem for path in Path(snapshots).glob("????-??-??.csv"))
    published_dates = [d for d in dates if d <= cutoff]
    latest_observed = dates[-1] if dates else None
    if outcome == "success":
        if latest_observed != today.isoformat():
            outcome = "failure"
        elif report and report.get("outcome") in ("partial", "failure"):
            outcome = report["outcome"]
    return {"outcome": outcome, "last_attempt_at": now.isoformat(timespec="seconds") if outcome != "unknown" else None,
            "latest_date": published_dates[-1] if published_dates else None,
            "latest_observed_date": latest_observed, "through_date": cutoff, "run_url": run_url,
            "completed_pages": (report or {}).get("completed_pages"),
            "product_count": (report or {}).get("product_count")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outcome", choices=["success", "failure", "unknown"], required=True)
    args = ap.parse_args()
    report_path = ROOT / "data/scrape-result.json"
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else None
    status = make_status(args.outcome, ROOT / "data/snapshots", run_url=os.environ.get("RUN_URL", ""), report=report)
    (ROOT / "docs/update-status.json").write_text(json.dumps(status, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

