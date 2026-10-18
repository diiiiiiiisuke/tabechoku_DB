"""動作確認用のデモ・スナップショットを生成する（実データではありません）。

    python -m scraper.demo && python -m scraper.build --snapshots data/demo_snapshots --demo
"""
import argparse
import csv
import math
import os
import random
from datetime import date, timedelta

from scraper.scrape import FIELDS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

VARIETIES = ["あまおう", "とちおとめ", "ベリーツ", "紅ほっぺ", "さがほのか", "いちごさん",
             "スカイベリー", "ゆめのか", "やよいひめ", "淡雪", "古都華", "恋みのり"]
PREFS = ["福岡県", "栃木県", "大分県", "静岡県", "佐賀県", "熊本県", "奈良県", "群馬県", "長崎県", "愛知県"]
WEIGHTS = [(500, "約250g×2パック"), (1000, "約250g×4パック"), (1080, "約270g×4パック"),
           (600, "約300g×2パック"), (800, "約400g×2パック"), (1000, "1kg"), (2000, "2kg")]


def poisson(rng, lam):
    if lam <= 0:
        return 0
    l, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= l:
            return k
        k += 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=os.path.join(ROOT, "data", "demo_snapshots"))
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--products", type=int, default=70)
    ap.add_argument("--end", default=None, help="最終日 YYYY-MM-DD（省略時は今日）")
    args = ap.parse_args()

    rng = random.Random(42)
    end = date.fromisoformat(args.end) if args.end else date.today()
    start = end - timedelta(days=args.days - 1)

    items = []
    for i in range(args.products):
        variety = rng.choice(VARIETIES)
        pref = "大分県" if variety == "ベリーツ" else rng.choice(PREFS)
        grams, label = rng.choice(WEIGHTS)
        ship = rng.random() < 0.35
        premium = 1.35 if variety in ("あまおう", "古都華", "淡雪", "スカイベリー") else 1.0
        ppk = rng.gauss(3600, 900) * premium + (500 if ship else 0)
        ppk = min(max(ppk, 1800), 9000)
        items.append({
            "id": str(1000000 + i * 137),
            "title": f"{'【送料込】' if ship else ''}{pref[:-1]}産 {variety} {label}",
            "producer": f"デモ農園{i + 1:02d}",
            "pref": pref,
            "variety": variety,
            "grams": grams,
            "ship": ship,
            "premium": premium,
            "price": int(round(ppk * grams / 1000, -1)),
            "pop": rng.lognormvariate(0, 0.6),
            "reviews": rng.randint(0, 400),
            "rating": round(rng.uniform(4.3, 5.0), 2),
            "stock": rng.randint(20, 80) if rng.random() < 0.3 else None,
            "start": start + timedelta(days=rng.randint(0, args.days // 3) if rng.random() < 0.3 else 0),
            "soldout_until": None,
        })

    os.makedirs(args.out_dir, exist_ok=True)
    for n in range(args.days):
        d = start + timedelta(days=n)
        season = 0.6 + 0.4 * n / args.days
        rows = []
        for it in items:
            if d < it["start"]:
                continue
            if rng.random() < 0.03:  # 時々価格改定
                it["price"] = int(round(it["price"] * rng.choice([0.85, 0.9, 1.1, 1.15]), -1))
            ppk = it["price"] / it["grams"] * 1000
            adj_ppk = ppk / it["premium"] - (500 if it["ship"] else 0)
            # 1kgあたり約4,200円を超えると需要が急落する、という仮定のデモ需要曲線
            demand = it["pop"] * season * 3.2 / (1 + math.exp((adj_ppk - 4200) / 350))
            sold_out = bool(it["soldout_until"] and d <= it["soldout_until"])
            if not sold_out and rng.random() < 0.01:
                it["soldout_until"] = d + timedelta(days=rng.randint(1, 5))
                sold_out = True
            sales = 0 if sold_out else poisson(rng, demand)
            if it["stock"] is not None and not sold_out:
                sales = min(sales, it["stock"])
                it["stock"] -= sales
                if it["stock"] == 0:
                    it["stock"] = rng.randint(30, 80)
            it["reviews"] += sum(1 for _ in range(sales) if rng.random() < 0.1)
            rows.append({
                "date": d.isoformat(),
                "product_id": it["id"],
                "url": f"https://www.tabechoku.com/products/{it['id']}",
                "title": it["title"],
                "producer": it["producer"],
                "prefecture": it["pref"],
                "variety": it["variety"],
                "price": it["price"],
                "shipping_included": int(it["ship"]),
                "weight_g": it["grams"],
                "weight_estimated": 0,
                "price_per_kg": round(ppk),
                "review_count": it["reviews"],
                "rating": it["rating"],
                "stock": "" if it["stock"] is None else it["stock"],
                "sold_out": int(sold_out),
                "image": "",
            })
        with open(os.path.join(args.out_dir, f"{d.isoformat()}.csv"), "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader()
            w.writerows(rows)
    print(f"wrote {args.days} demo snapshots to {args.out_dir}")


if __name__ == "__main__":
    main()
