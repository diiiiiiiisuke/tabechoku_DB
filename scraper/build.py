"""日次スナップショットCSVを集計し、ダッシュボード用の docs/data.js を生成する。

販売数は食べチョク上で公開されていないため、次の指標から推定する:
  1. 在庫数「残りN個」が前日から減った数（取得できた場合）
  2. レビュー件数の増加 ÷ レビュー投稿率（config.json の review_rate）
"""
import argparse
import csv
import glob
import json
import os
import re
import statistics
from datetime import date, datetime, timedelta, timezone

import markdown

from scraper.parse import NOT_STRAWBERRY, classify

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JST = timezone(timedelta(hours=9))
SERIES_DAYS = 180
PPK_RANGE = (300, 30000)


def load_config():
    with open(os.path.join(ROOT, "config.json"), encoding="utf-8") as f:
        return json.load(f)


def schedule_jst():
    """daily.yml の cron（UTC）を日本時間の「H:MM」に変換する。"""
    path = os.path.join(ROOT, ".github", "workflows", "daily.yml")
    try:
        with open(path, encoding="utf-8") as f:
            m = re.search(r'cron:\s*"(\d+)\s+(\d+)\s', f.read())
    except OSError:
        m = None
    if not m:
        return "（未設定）"
    minute, hour = int(m.group(1)), int(m.group(2))
    return f"{(hour + 9) % 24}:{minute:02d}"


def render_manual(cfg):
    """docs/manual.md の {{キー}} を現在の設定値で置き換えてHTMLにする。"""
    with open(os.path.join(ROOT, "docs", "manual.md"), encoding="utf-8") as f:
        text = f.read()
    values = {
        "schedule_jst": schedule_jst(),
        "search_url": cfg["search_url"],
        "max_pages": cfg["max_pages"],
        "max_products": cfg["max_pages"] * 48,
        "request_interval_sec": cfg["request_interval_sec"],
        "review_rate": cfg["review_rate"],
        "review_rate_pct": round(cfg["review_rate"] * 100),
        "default_pack_grams": cfg["default_pack_grams"],
        "default_berry_grams": cfg["default_berry_grams"],
        "price_band_width": cfg["price_band_width"],
        "cliff_drop_ratio": cfg["cliff_drop_ratio"],
        "cliff_drop_pct": round(cfg["cliff_drop_ratio"] * 100),
        "weight_ratio": cfg["comparable_weight_ratio"],
        "own_product_ids": ", ".join(cfg.get("own_product_ids", [])) or "（未設定）",
        "ppk_min": f"{PPK_RANGE[0]:,}",
        "ppk_max": f"{PPK_RANGE[1]:,}",
    }

    def sub(m):
        key = m.group(1)
        if key not in values:
            raise KeyError(f"manual.md の未定義キー: {key}")
        return str(values[key])

    text = re.sub(r"\{\{\s*(\w+)\s*\}\}", sub, text)
    return markdown.markdown(text, extensions=["tables"])


def _num(v, cast=float):
    if v in ("", None):
        return None
    try:
        return cast(float(v))
    except ValueError:
        return None


def _sane_ppk(v):
    """内容量の読み取りミス（例: 10g×5包のドライフルーツ）による極端な円/kgを除外する。"""
    return v if v is not None and PPK_RANGE[0] <= v <= PPK_RANGE[1] else None


def load_snapshots(snap_dir):
    days = {}
    for path in sorted(glob.glob(os.path.join(snap_dir, "*.csv"))):
        d = os.path.splitext(os.path.basename(path))[0]
        with open(path, encoding="utf-8-sig") as f:
            rows = {}
            for r in csv.DictReader(f):
                kind = r.get("kind") or classify(r["title"])
                if kind == NOT_STRAWBERRY:
                    continue
                rows[r["product_id"]] = {
                    "title": r["title"],
                    "kind": kind,
                    "url": r["url"],
                    "producer": r["producer"],
                    "prefecture": r["prefecture"],
                    "variety": r["variety"],
                    "image": r.get("image", ""),
                    "price": _num(r["price"], int),
                    "ship": _num(r["shipping_included"], int) or 0,
                    "fee": _num(r.get("shipping_fee"), int),
                    "rank": _num(r.get("rank"), int),
                    "status": r.get("status", ""),
                    "weight": _num(r["weight_g"], int),
                    "west": _num(r["weight_estimated"], int) or 0,
                    "ppk": _sane_ppk(_num(r["price_per_kg"], int)),
                    "reviews": _num(r["review_count"], int) or 0,
                    "rating": _num(r["rating"]),
                    "stock": _num(r["stock"], int) if r["stock"] else _num(r.get("status") if (r.get("status") or "").isdigit() else None, int),
                    "sold_out": _num(r["sold_out"], int) or 0,
                }
        days[d] = rows
    return days


def estimate_sales(prev, cur, gap_days, review_rate):
    """前回スナップショットからの1日あたり推定販売数。"""
    if prev is None:
        return None
    if prev["stock"] is not None and cur["stock"] is not None and cur["stock"] < prev["stock"]:
        return (prev["stock"] - cur["stock"]) / gap_days
    delta = cur["reviews"] - prev["reviews"]
    return max(delta, 0) / review_rate / gap_days


def pct(values, q):
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def r0(v):
    return None if v is None else round(v)


def r2(v):
    return None if v is None else round(v, 2)


def build(days, cfg, is_demo):
    dates = sorted(days)
    if not dates:
        raise SystemExit("スナップショットがありません")
    review_rate = cfg["review_rate"]

    # 商品ごとの時系列（推定販売数付き）
    history = {}  # pid -> list of (date, row, sales)
    last_seen = {}
    sales_by_date = {}
    for d in dates:
        for pid, row in days[d].items():
            prev = last_seen.get(pid)
            sales = None
            if prev:
                gap = (date.fromisoformat(d) - date.fromisoformat(prev[0])).days or 1
                sales = estimate_sales(prev[1], row, gap, review_rate)
            history.setdefault(pid, []).append((d, row, sales))
            sales_by_date[d] = sales_by_date.get(d, 0.0) + (sales or 0.0)
            last_seen[pid] = (d, row)

    # 日別の市場サマリー
    daily = []
    for d in dates:
        rows = days[d]
        avail = [r for r in rows.values() if not r["sold_out"]]
        ppks = [r["ppk"] for r in avail if r["ppk"]]
        prices = [r["price"] for r in avail if r["price"]]
        sales = sales_by_date.get(d, 0.0)
        daily.append({
            "date": d,
            "listed": len(rows),
            "available": len(avail),
            "soldout_rate": r2((len(rows) - len(avail)) / len(rows)) if rows else None,
            "ppk_p25": r0(pct(ppks, 0.25)),
            "ppk_median": r0(pct(ppks, 0.5)),
            "ppk_p75": r0(pct(ppks, 0.75)),
            "price_median": r0(pct(prices, 0.5)),
            "est_sales": round(sales, 1),
        })

    # 商品一覧（最新値 + 期間集計）
    latest_date = dates[-1]
    latest_dt = date.fromisoformat(latest_date)
    series_start = (latest_dt - timedelta(days=SERIES_DAYS)).isoformat()
    products = []
    events = []
    for pid, hist in history.items():
        d_last, row, _ = hist[-1]

        def window_sales(n):
            start = (latest_dt - timedelta(days=n)).isoformat()
            vals = [s for hd, _, s in hist if hd > start and s is not None]
            return round(sum(vals) / n, 2) if vals else 0.0

        recent = [r for hd, r, _ in hist if hd > (latest_dt - timedelta(days=14)).isoformat()]
        ppk14 = [r["ppk"] for r in recent if r["ppk"]]
        week_ago = next((r for hd, r, _ in reversed(hist) if hd <= (latest_dt - timedelta(days=7)).isoformat()), None)
        products.append({
            "id": pid,
            "title": row["title"],
            "kind": row["kind"],
            "url": row["url"],
            "producer": row["producer"],
            "prefecture": row["prefecture"],
            "variety": row["variety"],
            "image": row["image"],
            "price": row["price"],
            "ship": row["ship"],
            "fee": row["fee"],
            "rank": row["rank"],
            "status_label": row["status"],
            "weight": row["weight"],
            "west": row["west"],
            "ppk": row["ppk"],
            "ppk14": r0(statistics.mean(ppk14)) if ppk14 else None,
            "reviews": row["reviews"],
            "rating": row["rating"],
            "stock": row["stock"],
            "sold_out": row["sold_out"],
            "active": d_last == latest_date,
            "first_seen": hist[0][0],
            "last_seen": d_last,
            "price_7d": week_ago["price"] if week_ago else None,
            "sales7": window_sales(7),
            "sales14": window_sales(14),
            "sales30": window_sales(30),
            "own": pid in cfg.get("own_product_ids", []),
            "series": [
                [hd, r["price"], r["ppk"], r["reviews"], r2(s), r["sold_out"]]
                for hd, r, s in hist if hd >= series_start
            ],
        })

        # 価格変更イベント: 変更前後7日の販売ペースを比較
        for i in range(1, len(hist)):
            p0, p1 = hist[i - 1][1]["price"], hist[i][1]["price"]
            if not p0 or not p1 or p0 == p1:
                continue
            d_change = date.fromisoformat(hist[i][0])

            def pace(lo, hi):
                vals = [s for hd, _, s in hist
                        if s is not None and lo < date.fromisoformat(hd) <= hi]
                return round(sum(vals) / len(vals), 2) if vals else None

            events.append({
                "date": hist[i][0],
                "id": pid,
                "title": row["title"],
                "old": p0,
                "new": p1,
                "old_ppk": hist[i - 1][1]["ppk"],
                "new_ppk": hist[i][1]["ppk"],
                "before": pace(d_change - timedelta(days=7), d_change - timedelta(days=1)),
                "after": pace(d_change - timedelta(days=1), d_change + timedelta(days=6)),
            })

    events.sort(key=lambda e: e["date"], reverse=True)
    products.sort(key=lambda p: (-p["sales14"], p["title"]))
    return {
        "generated_at": datetime.now(JST).isoformat(timespec="minutes"),
        "is_demo": is_demo,
        "latest_date": latest_date,
        "config": {
            "review_rate": review_rate,
            "price_band_width": cfg["price_band_width"],
            "cliff_drop_ratio": cfg["cliff_drop_ratio"],
            "comparable_weight_ratio": cfg["comparable_weight_ratio"],
            "focus_prefecture": cfg.get("focus_prefecture", ""),
            "search_url": cfg["search_url"],
        },
        "daily": daily,
        "products": products,
        "price_events": events[:300],
        "manual_html": render_manual(cfg),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshots", default=os.path.join(ROOT, "data", "snapshots"))
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "data.js"))
    ap.add_argument("--demo", action="store_true", help="デモデータとして表示する")
    args = ap.parse_args()

    data = build(load_snapshots(args.snapshots), load_config(), args.demo)
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    with open(args.out, "w", encoding="utf-8") as f:
        f.write("window.DASHBOARD_DATA = " + payload + ";\n")
    print(f"wrote {args.out}: {len(data['products'])} products, {len(data['daily'])} days")


if __name__ == "__main__":
    main()
