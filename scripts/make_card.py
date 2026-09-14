#!/usr/bin/env python3
"""kappstore の商品カード画像（1200x630）を作る。

Kurageシリーズのカードと並んだときに揃うよう、配色は kappstore/scripts/make_ogp.py に合わせる。
成長する数字（出品本数など）は焼き込まない（あとで嘘になるため）。

  .venv/bin/python scripts/make_card.py  →  outputs/listing/card.png
"""
import os

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_B = "/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc"
FONT_R = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
W, H = 1200, 630
FOAM, PANEL, TEAL, NAVY, MUTED = "#f5fbfb", "#e7f3f2", "#0a9a8f", "#12202f", "#5b6b76"


def f(path, size):
    return ImageFont.truetype(path, size)


def main():
    img = Image.new("RGB", (W, H), FOAM)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 14], fill=TEAL)
    # 様式の紙を模した面
    d.rounded_rectangle([70, 120, 560, 540], 18, fill="#ffffff", outline="#d9e6e5", width=2)
    y = 165
    for w, filled in ((300, False), (420, True), (250, False), (380, True), (200, False), (410, True)):
        d.rounded_rectangle([110, y, 110 + w, y + 20], 6,
                            fill=("#d7f0ec" if filled else "#eef4f4"),
                            outline=(TEAL if filled else "#dfe8e8"), width=(2 if filled else 1))
        if filled:
            d.text((118, y + 1), "✓", font=f(FONT_B, 17), fill=TEAL)
        y += 58
    d.text((640, 140), "申請書", font=f(FONT_B, 76), fill=NAVY)
    d.text((640, 228), "記入アシスト", font=f(FONT_B, 62), fill=TEAL)
    lines = ["Word・Excel・PDF を上げるだけ",
             "空欄を見つけて、分かるところだけ埋める",
             "様式はそのまま。AIに文章は作らせない"]
    yy = 330
    for t in lines:
        d.text((642, yy), "・" + t, font=f(FONT_R, 27), fill=MUTED)
        yy += 46
    # 文字がはみ出さないよう、幅を測ってから帯を引く
    label = "買い切り・ソース同梱（MIT）・MCP同梱"
    fnt = f(FONT_B, 26)
    tw = d.textlength(label, font=fnt)
    x0, pad = 640, 24
    d.rounded_rectangle([x0, 486, min(x0 + tw + pad * 2, W - 40), 556], 12, fill=PANEL)
    d.text((x0 + pad, 505), label, font=fnt, fill=NAVY)
    out = os.path.join(ROOT, "outputs", "listing", "card.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    img.save(out)
    print(out, img.size)


if __name__ == "__main__":
    main()
