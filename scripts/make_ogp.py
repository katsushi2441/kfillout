#!/usr/bin/env python3
"""OGP / kappstore 商品画像 1200×630。

**kjishin/scripts/make_ogp.py と同じ型で作る。** Kurageシリーズの商品カードが並んだときに
揃って見えるよう、配色・余白・マスコットの位置・帯の形を合わせている。
（ライトテーマ・中央寄せ・文字大きく・マスコット入り・成長する数字は焼き込まない）

  .venv/bin/python scripts/make_ogp.py
    → app/static/ogp.png            デモサイトのOGP
    → outputs/listing/card.png      kappstore の商品画像（同じ絵）
"""
import os

from PIL import Image, ImageDraw, ImageFont

W, H = 1200, 630
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MASCOT = "/home/kojima/work/kurage_web/images/kurage-mascot-cutout.png"
FB = "/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc"
FM = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
FR = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"


def build() -> Image.Image:
    img = Image.new("RGB", (W, H), "#ffffff")
    dr = ImageDraw.Draw(img, "RGBA")
    dr.ellipse([-180, -240, 480, 380], fill=(230, 244, 242, 255))
    dr.ellipse([W - 460, H - 330, W + 220, H + 240], fill=(240, 246, 246, 255))

    mascot = None
    if os.path.exists(MASCOT):
        mascot = Image.open(MASCOT).convert("RGBA")
        mh = 300
        mascot = mascot.resize((int(mascot.width * mh / mascot.height), mh))
    cx = 520 if mascot else W // 2

    f_badge = ImageFont.truetype(FM, 26)
    f_h = ImageFont.truetype(FB, 62)
    f_h2 = ImageFont.truetype(FB, 46)
    f_s = ImageFont.truetype(FR, 28)
    f_pill = ImageFont.truetype(FM, 24)
    f_brand = ImageFont.truetype(FM, 30)

    badge = "申請書のWord・Excel・PDFを、書式そのままで埋める"
    bw = dr.textlength(badge, font=f_badge) + 40
    dr.rounded_rectangle([cx - bw / 2, 92, cx + bw / 2, 140], radius=24,
                         fill="#e6f4f2", outline="#bfe3de")
    dr.text((cx, 116), badge, font=f_badge, fill="#0a726b", anchor="mm")

    dr.text((cx, 220), "また、おなじことを", font=f_h, fill="#12202f", anchor="mm")
    dr.text((cx, 300), "書いていませんか。", font=f_h2, fill="#0a9a8f", anchor="mm")
    dr.text((cx, 372), "会社名・所在地・代表者を、様式のたびに書き写す。", font=f_s, fill="#5d6b7a", anchor="mm")
    dr.text((cx, 412), "空欄を見つけて、分かるところだけ埋めます。", font=f_s, fill="#5d6b7a", anchor="mm")

    # 3つの約束。中央寄せで等間隔に置く
    pills = ["様式を変えない", "AIに文章を作らせない", "MCP同梱"]
    gap = 14
    widths = [dr.textlength(p, font=f_pill) + 34 for p in pills]
    total = sum(widths) + gap * (len(pills) - 1)
    x = cx - total / 2
    for p, w in zip(pills, widths):
        dr.rounded_rectangle([x, 446, x + w, 490], radius=22, fill="#ffffff", outline="#bfe3de")
        dr.text((x + w / 2, 468), p, font=f_pill, fill="#0a726b", anchor="mm")
        x += w + gap

    dr.rounded_rectangle([cx - 230, 512, cx + 230, 572], radius=16, fill="#0a9a8f")
    dr.text((cx, 542), "Kurage 申請書記入アシスト", font=f_brand, fill="#ffffff", anchor="mm")

    if mascot:
        img.paste(mascot, (W - mascot.width - 40, H - mascot.height - 30), mascot)
    dr.text((40, H - 40), "kurage.exbridge.jp/kfillout.php/",
            font=ImageFont.truetype(FR, 22), fill="#5d6b7a", anchor="lm")
    return img


def main():
    img = build()
    for path in (os.path.join(ROOT, "app", "static", "ogp.png"),
                 os.path.join(ROOT, "outputs", "listing", "card.png")):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        img.save(path, optimize=True)
        print(path, img.size)


if __name__ == "__main__":
    main()
