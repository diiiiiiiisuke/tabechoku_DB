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
import statistics
from datetime import date, datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JST = timezone(timedelta(hours=9))
SERIES_DAYS = 180


def load_config():
    with open(os.path.join(ROOT, "config.json"), encoding="utf-8") as f:
        return json.load(f)


def _num(v, cast=float):
    if v in ("", None):
        return None
    try:
        return cast(float(v))
    except ValueError:
        return None


def load_snapshots(snap_dir):
    days = {}
    for path in sorted(glob.glob(os.path.join(snap_dir, "*.csv"))):
        d = os.path.splitext(os.path.basename(path))[0]
        with open(path, encoding="utf-8-sig") as f:
            rows = {}
            for r in csv.DictReader(f):
                rows[r["product_id"]] = {
                    "title": r["title"],
                    "url": r["url"],
                    "producer": r["producer"],
                    "prefecture": r["prefecture"],
                    "variety": r["variety"],
                    "image": r.get("image", ""),
                    "price": _num(r["price"], int),
                    "ship": _num(r["shipping_included"], int) or 0,
                    "weight": _num(r["weight_g"], int),
                    "west": _num(r["weight_estimated"], int) or 0,
                    "ppk": _num(r["price_per_kg"], int),
                    "reviews": _num(r["review_count"], int) or 0,
                    "rating": _num(r["rating"]),
                    "stock": _num(r["stock"], int),
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
            "url": row["url"],
            "producer": row["producer"],
            "prefecture": row["prefecture"],
            "variety": row["variety"],
            "image": row["image"],
            "price": row["price"],
            "ship": row["ship"],
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
            "focus_prefecture": cfg.get("focus_prefecture", ""),
            "search_url": cfg["search_url"],
        },
        "daily": daily,
        "products": products,
        "price_events": events[:300],
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
