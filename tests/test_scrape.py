import unittest

from scraper.scrape import parse_product

CFG = {"default_pack_grams": 270, "default_berry_grams": 20}

JSONLD_HTML = """
<html><head>
<meta property="og:title" content="【送料込】大分県産ベリーツ 約270g×4パック | 食べチョク">
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Product","name":"【送料込】大分県産ベリーツ 約270g×4パック",
 "brand":{"@type":"Brand","name":"テスト農園"},
 "offers":{"@type":"Offer","price":"4980","priceCurrency":"JPY","availability":"https://schema.org/InStock"},
 "aggregateRating":{"@type":"AggregateRating","ratingValue":"4.9","reviewCount":"123"}}
</script></head>
<body><div><a href="/producers/1">テスト農園</a><span>大分県 宇佐市</span></div>
<p>残り5個</p></body></html>
"""

FALLBACK_HTML = """
<html><head><title>朝摘みいちご 2パック | 食べチョク</title></head>
<body><div class="price">2,480円(税込)</div><a href="/producers/9">山田農園</a> 福岡県
<span>レビュー(12)</span><button>売り切れ</button></body></html>
"""


class ParseProductTest(unittest.TestCase):
    def test_jsonld(self):
        r = parse_product(JSONLD_HTML, "1", CFG)
        self.assertEqual(r["price"], 4980)
        self.assertEqual(r["weight_g"], 1080)
        self.assertEqual(r["price_per_kg"], 4611)
        self.assertEqual(r["review_count"], 123)
        self.assertEqual(r["producer"], "テスト農園")
        self.assertEqual(r["prefecture"], "大分県")
        self.assertEqual(r["variety"], "ベリーツ")
        self.assertEqual(r["stock"], 5)
        self.assertEqual(r["sold_out"], 0)
        self.assertEqual(r["shipping_included"], 1)

    def test_html_fallback(self):
        r = parse_product(FALLBACK_HTML, "2", CFG)
        self.assertEqual(r["title"], "朝摘みいちご 2パック")
        self.assertEqual(r["price"], 2480)
        self.assertEqual(r["weight_g"], 540)
        self.assertEqual(r["weight_estimated"], 1)
        self.assertEqual(r["review_count"], 12)
        self.assertEqual(r["sold_out"], 1)
        self.assertEqual(r["prefecture"], "福岡県")


if __name__ == "__main__":
    unittest.main()
