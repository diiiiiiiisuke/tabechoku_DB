"""食べチョクの「いちご」検索結果を取得し、日次スナップショットCSVを保存する。

検索結果の商品カードに価格・送料・内容量・レビュー数・産地が載っているため、
商品ページは開かず一覧ページ（50件/ページ）だけを取得する。1日あたり約20リクエスト。

使い方:
    python -m scraper.scrape                # data/snapshots/YYYY-MM-DD.csv を作成
    python -m scraper.scrape --debug-dump   # 1ページ目のHTMLを data/debug/ に保存
"""
import argparse
import csv
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

from scraper.parse import (is_shipping_included, normalize, parse_prefecture, parse_variety,
                           parse_weight)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = "https://www.tabechoku.com"
JST = timezone(timedelta(hours=9))

FIELDS = [
    "date", "product_id", "url", "title", "producer", "prefecture", "area", "variety",
    "price", "shipping_fee", "shipping_included", "weight_g", "weight_estimated", "price_per_kg",
    "review_count", "rating", "stock", "sold_out", "status", "rank", "image",
]

PRODUCT_HREF_RE = re.compile(r"^(?:https://www\.tabechoku\.com)?/products/(\d+)(?:[/?#]|$)")
SOLD_OUT_RE = re.compile(r"売り切れ|売切れ|在庫切れ|在庫なし|SOLD\s*OUT|販売終了|受付終了", re.I)
# アクセス制限（WAF）を示すステータス。リトライせずに打ち切る
BLOCKED_STATUSES = {403, 405, 429}


def load_config():
    with open(os.path.join(ROOT, "config.json"), encoding="utf-8") as f:
        return json.load(f)


class Fetcher:
    def __init__(self, cfg):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": cfg["user_agent"],
            "Accept-Language": "ja,en;q=0.8",
        })
        self.interval = cfg["request_interval_sec"]
        self.blocked = False
        self._last = 0.0

    def get(self, url):
        wait = self.interval - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        for attempt in range(3):
            try:
                self._last = time.time()
                r = self.session.get(url, timeout=30)
                if r.status_code == 200:
                    return r.text
                print(f"  HTTP {r.status_code}: {url}", file=sys.stderr)
                if r.status_code in BLOCKED_STATUSES:
                    self.blocked = True
                    return None
                if r.status_code == 404:
                    return None
            except requests.RequestException as e:
                print(f"  error {e}: {url}", file=sys.stderr)
            time.sleep(10 * (attempt + 1))
        return None


def with_page(url, page):
    u = urlparse(url)
    q = dict(parse_qsl(u.query))
    q["page"] = str(page)
    return urlunparse(u._replace(query=urlencode(q)))


def _text(el):
    return el.get_text(" ", strip=True) if el else ""


def _int(text):
    m = re.search(r"\d+", normalize(text))
    return int(m.group()) if m else None


def parse_card(card, cfg):
    """検索結果の商品カード（div.p-productTilingCard）を1行に変換する。"""
    pid = card.get("data-product-id")
    title = _text(card.select_one(".p-productTilingCard__productName"))
    quantity = _text(card.select_one(".p-productTilingCard__quantity"))
    price = _int(_text(card.select_one(".p-productTilingCard__price")))
    fee_text = _text(card.select_one(".p-productTilingCard__shippingPrice"))
    shipping_fee = _int(fee_text) if fee_text else None
    review_count = _int(_text(card.select_one(".p-productTilingCard__reviewCount"))) or 0
    score = _text(card.select_one(".p-productTilingCard__reviewScore"))
    area = _text(card.select_one(".p-productTilingCard__producerArea"))
    producer = _text(card.select_one(".p-productTilingCard__producerName"))
    img = card.select_one(".p-productTilingCard__productImg img")

    # 在庫ラベル: <div class="c-productStock c-productStock--reservation"> など
    status = ""
    stock_el = card.select_one("[class*='c-productStock']")
    if stock_el:
        mods = [c.split("--", 1)[1] for c in stock_el.get("class", []) if "--" in c]
        status = ",".join(mods) or _text(stock_el)
    labels = " ".join(_text(el) for el in card.select("figure div"))
    sold_out = bool(re.search(r"sold|soldout|out_of_stock", status, re.I)) or bool(SOLD_OUT_RE.search(labels))
    stock = None
    m = re.search(r"残り\s*(\d+)", normalize(labels))
    if m:
        stock = int(m.group(1))

    weight, estimated = None, False
    for source in (quantity, title):
        weight, estimated = parse_weight(source, cfg["default_pack_grams"], cfg["default_berry_grams"])
        if weight:
            break
    ship_incl = shipping_fee == 0 or (shipping_fee is None and is_shipping_included(title))
    return {
        "product_id": pid,
        "url": f"{BASE}/products/{pid}",
        "title": title,
        "producer": producer,
        "prefecture": parse_prefecture(area),
        "area": area,
        "variety": parse_variety(title),
        "price": price or "",
        "shipping_fee": "" if shipping_fee is None else shipping_fee,
        "shipping_included": int(ship_incl),
        "weight_g": int(weight) if weight else "",
        "weight_estimated": int(estimated),
        "price_per_kg": round(price / weight * 1000) if price and weight else "",
        "review_count": review_count,
        "rating": float(score) if re.fullmatch(r"\d+(\.\d+)?", score) else "",
        "stock": "" if stock is None else stock,
        "sold_out": int(sold_out),
        "status": status,
        "image": img.get("src", "") if img else "",
    }


def parse_list_page(html, cfg):
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for card in soup.select("div.p-productTilingCard[data-product-id]"):
        # おすすめ枠などのカードは data-item-list が付くので除外する
        link = card.select_one("a.p-productTilingCard__productLink")
        if link is not None and link.get("data-item-list"):
            continue
        rows.append(parse_card(card, cfg))
    return rows


def _dump(dump_dir, name, html):
    os.makedirs(dump_dir, exist_ok=True)
    with open(os.path.join(dump_dir, name), "w", encoding="utf-8") as f:
        f.write(html)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=os.path.join(ROOT, "data", "snapshots"))
    ap.add_argument("--max-pages", type=int, default=0, help="取得ページ数の上限（動作確認用）")
    ap.add_argument("--debug-dump", action="store_true")
    args = ap.parse_args()

    cfg = load_config()
    fetcher = Fetcher(cfg)
    dump_dir = os.path.join(ROOT, "data", "debug") if args.debug_dump else None
    today = datetime.now(JST).strftime("%Y-%m-%d")
    max_pages = args.max_pages or cfg["max_pages"]

    rows, seen = [], set()
    for page in range(1, max_pages + 1):
        html = fetcher.get(with_page(cfg["search_url"], page))
        if not html:
            break
        if dump_dir and page == 1:
            _dump(dump_dir, "list_page1.html", html)
        new = 0
        for row in parse_list_page(html, cfg):
            if row["product_id"] in seen:
                continue
            seen.add(row["product_id"])
            row["date"] = today
            row["rank"] = len(rows) + 1
            rows.append(row)
            new += 1
        print(f"page {page}: +{new} products (total {len(rows)})")
        if new == 0:
            break

    if fetcher.blocked:
        print(f"アクセス制限により途中で打ち切りました（{len(rows)} 件取得）", file=sys.stderr)
    if not rows:
        print("商品を1件も取得できませんでした。サイト構造の変更やアクセス制限を確認してください。", file=sys.stderr)
        sys.exit(1)

    os.makedirs(args.out_dir, exist_ok=True)
    path = os.path.join(args.out_dir, f"{today}.csv")
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    with_weight = sum(1 for r in rows if r["weight_g"])
    print(f"saved {path}: {len(rows)} products (内容量取得 {with_weight})")


if __name__ == "__main__":
    main()
