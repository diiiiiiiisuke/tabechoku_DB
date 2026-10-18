import unittest

from scraper.parse import (classify, is_shipping_included, parse_prefecture, parse_price,
                           parse_variety, parse_weight)


class ParseWeightTest(unittest.TestCase):
    def check(self, text, grams, estimated=False):
        self.assertEqual(parse_weight(text), (grams, estimated), text)

    def test_simple(self):
        self.check("【送料込】あまおう 1kg", 1000.0)
        self.check("ベリーツ 約500g", 500.0)
        self.check("さがほのか １．５ｋｇ", 1500.0)
        self.check("とちおとめ 2キロ", 2000.0)

    def test_multiplier(self):
        self.check("紅ほっぺ 約270g×4パック", 1080.0)
        self.check("いちご 250g x 2P", 500.0)

    def test_per_pack(self):
        self.check("いちご 4パック（1パックあたり約300g）", 1200.0)

    def test_estimated(self):
        self.check("完熟いちご 2パック", 540.0, True)
        self.check("大粒いちご 15粒", 300.0, True)

    def test_none(self):
        self.check("朝摘みいちご", None)


class ParseMiscTest(unittest.TestCase):
    def test_variety(self):
        self.assertEqual(parse_variety("大分県産 ベリーツ 1kg"), "ベリーツ")
        self.assertEqual(parse_variety("佐賀 いちごさん"), "いちごさん")
        self.assertEqual(parse_variety("完熟いちご"), "")

    def test_prefecture(self):
        self.assertEqual(parse_prefecture("大分県 宇佐市 ○○農園"), "大分県")

    def test_price(self):
        self.assertEqual(parse_price("3,980円(税込)"), 3980)
        self.assertEqual(parse_price("¥2,480"), 2480)

    def test_classify(self):
        self.assertEqual(classify("完熟やよいひめ 約400g"), "生果")
        self.assertEqual(classify("急速冷凍いちご 1kg"), "冷凍")
        self.assertEqual(classify("いちごの無添加ドライフルーツ 10g×5包"), "加工品")
        self.assertEqual(classify("超巨大粒 天狼 種なし 1房450g"), "いちご以外")
        self.assertEqual(classify("和歌山県産 甘夏みかん 家庭用 10kg"), "いちご以外")
        self.assertEqual(classify("ブルーベリー 500g"), "いちご以外")
        self.assertEqual(classify("【千葉県限定生産】チーバベリー 400g×1トレー"), "生果")
        self.assertEqual(classify("【希少あまりん】小粒たっぷり1Kg"), "生果")

    def test_shipping(self):
        self.assertTrue(is_shipping_included("【送料込】あまおう"))
        self.assertFalse(is_shipping_included("あまおう 1kg"))


if __name__ == "__main__":
    unittest.main()
