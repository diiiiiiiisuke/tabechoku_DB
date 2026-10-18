"""食べチョクのいちご商品一覧と各商品ページを取得し、日次スナップショットCSVを保存する。

使い方:
    python -m scraper.scrape                # data/snapshots/YYYY-MM-DD.csv を作成
    python -m scraper.scrape --debug-dump   # 取得HTMLの一部を data/debug/ に保存（パーサ調整用）
"""
import argparse
import csv
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

from scraper.parse import (is_shipping_included, normalize, parse_prefecture, parse_price,
                           parse_variety, parse_weight)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = "https://www.tabechoku.com"
JST = timezone(timedelta(hours=9))

FIELDS = [
    "date", "product_id", "url", "title", "producer", "prefecture", "variety",
    "price", "shipping_included", "weight_g", "weight_estimated", "price_per_kg",
    "review_count", "rating", "stock", "sold_out", "image",
]

PRODUCT_HREF_RE = re.compile(r"^(?:https://www\.tabechoku\.com)?/products/(\d+)(?:[/?#]|$)")
SOLD_OUT_RE = re.compile(r"売り切れ|売切れ|在庫切れ|在庫なし|SOLD\s*OUT|販売終了|受付終了", re.I)


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
                if r.status_code == 404:
                    return None
            except requests.RequestException as e:
                print(f"  error {e}: {url}", file=sys.stderr)
            time.sleep(2 ** (attempt + 1))
        return None


def with_page(url, page):
    u = urlparse(url)
    q = dict(parse_qsl(u.query))
    q["page"] = str(page)
    return urlunparse(u._replace(query=urlencode(q)))


def collect_product_ids(fetcher, cfg, dump_dir=None):
    ids = []
    seen = set()
    for page in range(1, cfg["max_pages"] + 1):
        html = fetcher.get(with_page(cfg["search_url"], page))
        if not html:
            break
        if dump_dir and page == 1:
            _dump(dump_dir, "list_page1.html", html)
        soup = BeautifulSoup(html, "html.parser")
        new = 0
        for a in soup.find_all("a", href=True):
            m = PRODUCT_HREF_RE.match(a["href"])
            if m and m.group(1) not in seen:
                seen.add(m.group(1))
                ids.append(m.group(1))
                new += 1
        print(f"page {page}: +{new} products (total {len(ids)})")
        if new == 0:
            break
    return ids


def _iter_jsonld(soup):
    for s in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(s.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        stack = [data]
        while stack:
            d = stack.pop()
            if isinstance(d, list):
                stack.extend(d)
            elif isinstance(d, dict):
                yield d
                if "@graph" in d:
                    stack.append(d["@graph"])


def _jsonld_product(soup):
    for d in _iter_jsonld(soup):
        t = d.get("@type")
        if t == "Product" or (isinstance(t, list) and "Product" in t):
            return d
    return None


def _meta(soup, prop):
    tag = soup.find("meta", attrs={"property": prop}) or soup.find("meta", attrs={"name": prop})
    return tag.get("content", "").strip() if tag else ""


def _first_number(v):
    if v is None:
        return None
    m = re.search(r"\d+(?:\.\d+)?", str(v).replace(",", ""))
    return float(m.group()) if m else None


def _label_value(text, label, length=80):
    m = re.search(label + r"\s*[:：]?\s*(.{1," + str(length) + r"})", text)
    return m.group(1) if m else ""


def parse_product(html, product_id, cfg):
    soup = BeautifulSoup(html, "html.parser")
    ld = _jsonld_product(soup) or {}
    page_text = normalize(soup.get_text(" ", strip=True))

    title = (ld.get("name") or _meta(soup, "og:title") or (soup.title.string if soup.title else "")).strip()
    title = re.sub(r"\s*[|｜-]\s*食べチョク.*$", "", title)
    description = ld.get("description") or _meta(soup, "og:description") or ""

    offers = ld.get("offers") or {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    price = _first_number(offers.get("price") or offers.get("lowPrice"))
    if price is None:
        price_el = soup.select_one("[class*='price'], [class*='Price']")
        price = parse_price(price_el.get_text(" ", strip=True)) if price_el else parse_price(page_text)

    availability = str(offers.get("availability", ""))
    if availability:
        sold_out = "OutOfStock" in availability or "SoldOut" in availability or "Discontinued" in availability
    else:
        # ページ下部のおすすめ商品の「売り切れ」を拾わないよう、購入ボタン周辺だけを見る
        buttons = " ".join(b.get_text(" ", strip=True) for b in soup.find_all(["button", "input"]))
        buttons += " ".join(b.get("value", "") for b in soup.find_all("input"))
        sold_out = bool(SOLD_OUT_RE.search(buttons))

    rating = ld.get("aggregateRating") or {}
    review_count = _first_number(rating.get("reviewCount") or rating.get("ratingCount"))
    if review_count is None:
        m = re.search(r"(?:レビュー|口コミ|みんなの声)\s*[(（]?\s*(\d+)\s*件?", page_text) or \
            re.search(r"(\d+)\s*件の(?:レビュー|口コミ)", page_text)
        review_count = float(m.group(1)) if m else 0.0
    rating_value = _first_number(rating.get("ratingValue"))

    stock = None
    m = re.search(r"残り\s*(\d+)\s*(?:個|点|セット|箱|件)?", page_text)
    if m:
        stock = int(m.group(1))

    producer = ""
    brand = ld.get("brand")
    if isinstance(brand, dict):
        producer = brand.get("name", "")
    elif isinstance(brand, str):
        producer = brand
    producer_link = soup.find("a", href=re.compile(r"/producers/\d+"))
    if not producer and producer_link:
        producer = producer_link.get_text(" ", strip=True)
    pref_scope = ""
    if producer_link:
        parent = producer_link
        for _ in range(4):
            parent = parent.parent or parent
        pref_scope = parent.get_text(" ", strip=True)
    prefecture = parse_prefecture(pref_scope) or parse_prefecture(description) or parse_prefecture(title)

    content = _label_value(page_text, "内容量")
    weight, estimated = None, False
    for source in (content, title, description):
        weight, estimated = parse_weight(source, cfg["default_pack_grams"], cfg["default_berry_grams"])
        if weight:
            break

    image = ld.get("image") or _meta(soup, "og:image")
    if isinstance(image, list):
        image = image[0] if image else ""

    ppk = round(price / weight * 1000) if price and weight else None
    return {
        "product_id": product_id,
        "url": f"{BASE}/products/{product_id}",
        "title": title,
        "producer": producer.strip(),
        "prefecture": prefecture,
        "variety": parse_variety(title) or parse_variety(description),
        "price": int(price) if price else "",
        "shipping_included": int(is_shipping_included(title + " " + content)),
        "weight_g": int(weight) if weight else "",
        "weight_estimated": int(estimated),
        "price_per_kg": ppk if ppk else "",
        "review_count": int(review_count or 0),
        "rating": rating_value if rating_value is not None else "",
        "stock": stock if stock is not None else "",
        "sold_out": int(sold_out),
        "image": image if isinstance(image, str) else "",
    }


def _dump(dump_dir, name, html):
    os.makedirs(dump_dir, exist_ok=True)
    with open(os.path.join(dump_dir, name), "w", encoding="utf-8") as f:
        f.write(html)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=os.path.join(ROOT, "data", "snapshots"))
    ap.add_argument("--limit", type=int, default=0, help="取得する商品数の上限（動作確認用）")
    ap.add_argument("--debug-dump", action="store_true")
    ap.add_argument("--max-minutes", type=float, default=0, help="この時間を超えたら取得を打ち切って保存する")
    args = ap.parse_args()

    cfg = load_config()
    fetcher = Fetcher(cfg)
    dump_dir = os.path.join(ROOT, "data", "debug") if args.debug_dump else None
    today = datetime.now(JST).strftime("%Y-%m-%d")

    started = time.time()
    ids = collect_product_ids(fetcher, cfg, dump_dir)
    if args.limit:
        ids = ids[:args.limit]
    rows = []
    for i, pid in enumerate(ids):
        if args.max_minutes and time.time() - started > args.max_minutes * 60:
            print(f"時間上限に達したため {i}/{len(ids)} 件で打ち切ります", file=sys.stderr)
            break
        html = fetcher.get(f"{BASE}/products/{pid}")
        if not html:
            continue
        if dump_dir and i < 3:
            _dump(dump_dir, f"product_{pid}.html", html)
        try:
            row = parse_product(html, pid, cfg)
        except Exception as e:  # 1商品のパース失敗で全体を止めない
            print(f"  parse error {pid}: {e}", file=sys.stderr)
            continue
        row["date"] = today
        rows.append(row)
        print(f"[{i + 1}/{len(ids)}] {pid} {row['price']}円 {row['weight_g']}g {row['title'][:40]}")

    if not rows:
        print("商品を1件も取得できませんでした。サイト構造の変更やアクセス制限を確認してください。", file=sys.stderr)
        sys.exit(1)

    os.makedirs(args.out_dir, exist_ok=True)
    path = os.path.join(args.out_dir, f"{today}.csv")
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    with_price = sum(1 for r in rows if r["price"])
    with_weight = sum(1 for r in rows if r["weight_g"])
    print(f"saved {path}: {len(rows)} products (価格取得 {with_price}, 内容量取得 {with_weight})")


if __name__ == "__main__":
    main()
