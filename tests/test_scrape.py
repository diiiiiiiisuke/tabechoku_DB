import unittest

from scraper.scrape import parse_list_page

CFG = {"default_pack_grams": 270, "default_berry_grams": 20}

# 2026-10 時点の検索結果カードの構造（実ページから要素を抜粋）
LIST_HTML = """
<div class="p-productTilingCard tbck-view-tracking js-product-card" data-product-id="177161">
<a class="p-productTilingCard__productLink ga-select-item" data-product-id="177161" href="/products/177161">
<figure class="p-productTilingCard__productImg u-aspectThumb">
<img alt="x" src="https://image-cdn.tabechoku.com/a.jpg"/>
<div class="p-productTilingCard__municipalityCampaignLabel is-hidden">自治体連携商品</div>
<div class="c-productStock c-productStock--reservation"></div>
</figure>
<div class="p-productTilingCard__productInfo">
<h4 class="p-productTilingCard__productName u-line-clamp-3">【いちごグランプリ2024最高金賞】新鮮完熟やよいひめ シングル×1箱｜2027年1月発送開始</h4>
<div class="p-productTilingCard__suppls">
<div class="p-productTilingCard__quantity"> 約400g </div>
<div class="p-productTilingCard__review">
<div class="p-productTilingCard__reviewItem"><span class="p-productTilingCard__reviewScore">4.8</span></div>
<div class="p-productTilingCard__reviewItem"><span class="p-productTilingCard__reviewCount">(95件)</span></div>
</div></div>
<p class="p-productTilingCard__price"><span class="productCardCampaignDiscount"></span> ¥2,780 </p>
<span class="p-productTilingCard__shippingPrice">送料 ¥605</span>
</div></a>
<a class="p-productTilingCard__producerLink" href="/producers/27800">
<div class="p-productTilingCard__producerInfo">
<p class="p-productTilingCard__producerArea u-ellipsis"> 群馬県伊勢崎市 </p>
<p class="p-productTilingCard__producerName u-ellipsis"> かがやきいちご園 </p>
</div></a></div>

<div class="p-productTilingCard js-product-card" data-product-id="247106">
<a class="p-productTilingCard__productLink" href="/products/247106">
<figure class="p-productTilingCard__productImg"><div class="c-quickShipLabel">すぐに出荷</div></figure>
<h4 class="p-productTilingCard__productName">【送料込】大分県産 ベリーツ 2パック</h4>
<span class="p-productTilingCard__reviewCount">(30件)</span>
<p class="p-productTilingCard__price">¥4,599</p>
</a>
<p class="p-productTilingCard__producerArea">大分県宇佐市</p>
</div>

<div class="p-productTilingCard" data-product-id="9">
<a class="p-productTilingCard__productLink" data-item-list="recommend_same_producer" href="/products/9"></a>
</div>
"""


class ParseListPageTest(unittest.TestCase):
    def test_cards(self):
        rows = parse_list_page(LIST_HTML, CFG)
        self.assertEqual([r["product_id"] for r in rows], ["177161", "247106"])

        a = rows[0]
        self.assertEqual(a["price"], 2780)
        self.assertEqual(a["shipping_fee"], 605)
        self.assertEqual(a["shipping_included"], 0)
        self.assertEqual(a["weight_g"], 400)
        self.assertEqual(a["price_per_kg"], 6950)
        self.assertEqual(a["review_count"], 95)
        self.assertEqual(a["rating"], 4.8)
        self.assertEqual(a["prefecture"], "群馬県")
        self.assertEqual(a["producer"], "かがやきいちご園")
        self.assertEqual(a["variety"], "やよいひめ")
        self.assertEqual(a["status"], "reservation")
        self.assertEqual(a["sold_out"], 0)

        b = rows[1]
        self.assertEqual(b["shipping_fee"], "")
        self.assertEqual(b["shipping_included"], 1)
        self.assertEqual(b["weight_g"], 540)
        self.assertEqual(b["weight_estimated"], 1)
        self.assertEqual(b["prefecture"], "大分県")
        self.assertEqual(b["variety"], "ベリーツ")


if __name__ == "__main__":
    unittest.main()
