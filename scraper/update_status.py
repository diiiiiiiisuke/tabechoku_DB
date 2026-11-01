"""日次取得の成否を公開する。取得できなかった日付をデータに追加しない。"""
import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JST = timezone(timedelta(hours=9))


def make_status(outcome, snapshots, now=None, run_url=""):
    now = now or datetime.now(JST)
    dates = sorted(path.stem for path in Path(snapshots).glob("????-??-??.csv"))
    latest = dates[-1] if dates else None
    # 成功でも当日のCSVがなければ最新取得の成功とは扱わない
    if outcome == "success" and latest != now.astimezone(JST).date().isoformat():
        outcome = "failure"
    return {"outcome": outcome, "last_attempt_at": now.isoformat(timespec="seconds") if outcome != "unknown" else None,
            "latest_date": latest, "run_url": run_url}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outcome", choices=["success", "failure", "unknown"], required=True)
    args = ap.parse_args()
    status = make_status(args.outcome, ROOT / "data/snapshots", run_url=os.environ.get("RUN_URL", ""))
    (ROOT / "docs/update-status.json").write_text(json.dumps(status, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
