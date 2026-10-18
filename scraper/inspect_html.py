"""パーサ調整用: 一覧ページ1枚と商品ページ1枚だけ取得し、HTML構造の要点をログに出す。

    python -m scraper.inspect_html
"""
import json
import re
import sys

from bs4 import BeautifulSoup

from scraper.scrape import BASE, PRODUCT_HREF_RE, Fetcher, load_config


def summarize(html, label):
    soup = BeautifulSoup(html, "html.parser")
    print(f"===== {label}: {len(html)} bytes, title={soup.title.string if soup.title else ''!r}")
    for s in soup.find_all("script", type="application/ld+json"):
        print("JSON-LD:", (s.string or "")[:1500])
    for s in soup.find_all("script"):
        src = s.get("src", "")
        body = s.string or ""
        if s.get("id") or re.search(r"price|product", body[:5000], re.I):
            print(f"SCRIPT id={s.get('id')!r} type={s.get('type')!r} src={src!r} len={len(body)}: {body[:600]!r}")
    for tag in soup.find_all(attrs={"data-react-props": True})[:3]:
        print("REACT-PROPS:", tag["data-react-props"][:1500])
    links = [a for a in soup.find_all("a", href=True) if PRODUCT_HREF_RE.match(a["href"])]
    print(f"product links: {len(links)}")
    for a in links[:4]:
        card = a
        for _ in range(3):
            if card.parent and len(card.parent.get_text(" ", strip=True)) < 400:
                card = card.parent
        print("--- CARD HTML:", str(card)[:2500])
        print("--- CARD TEXT:", card.get_text(" | ", strip=True)[:400])
    pag = [a["href"] for a in soup.find_all("a", href=True) if "page=" in a["href"]]
    print("pagination hrefs:", pag[:10])
    text = soup.get_text(" ", strip=True)
    for kw in ["件", "円", "送料", "レビュー", "内容量", "売り切れ", "残り", "評価"]:
        i = text.find(kw)
        print(f"ctx[{kw}]:", text[max(0, i - 80): i + 80] if i >= 0 else None)
    return links


def main():
    cfg = load_config()
    f = Fetcher(cfg)
    f.interval = 10
    html = f.get(cfg["search_url"])
    if not html:
        sys.exit("一覧ページを取得できませんでした")
    links = summarize(html, "LIST")
    if links:
        pid = PRODUCT_HREF_RE.match(links[0]["href"]).group(1)
        ph = f.get(f"{BASE}/products/{pid}")
        if ph:
            summarize(ph, f"PRODUCT {pid}")


if __name__ == "__main__":
    main()
