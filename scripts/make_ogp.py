#!/usr/bin/env python3
"""デモサイトのOGP画像（1200x630）を作る。

kappstore の商品カード（scripts/make_card.py）と同じ配色で、Kurageシリーズとして揃える。
成長する数字は焼き込まない（あとで嘘になる）。実測値は「4,024件」のように
出典と時点が言えるものだけ入れる。

  .venv/bin/python scripts/make_ogp.py  →  app/static/ogp.png
"""
import os

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_B = "/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc"
FONT_R = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
W, H = 1200, 630
# note の見出し画像は 1280x670 が推奨。同じ絵をそのサイズでも書き出す
NOTE_W, NOTE_H = 1280, 670
FOAM, PANEL, TEAL, NAVY, MUTED = "#f5fbfb", "#e7f3f2", "#0a9a8f", "#12202f", "#5b6b76"


def f(p, s):
    return ImageFont.truetype(p, s)


def main():
    img = Image.new("RGB", (W, H), FOAM)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 14], fill=TEAL)

    d.text((78, 96), "申請書記入アシスト", font=f(FONT_B, 72), fill=NAVY)
    d.text((80, 196), "Word・Excel・PDF の様式を、書式そのままで埋める",
           font=f(FONT_R, 31), fill=MUTED)

    # 3つの約束（この製品の輪郭）
    items = [("様式を変えない", "PDFに変換しない。旧形式は元の形式へ戻す"),
             ("AIに文章を作らせない", "日付・保存した会社情報・あなたの入力だけ"),
             ("外へ出さない", "判定もローカルLLM。ファイルはサーバーの中だけ")]
    y = 276
    for t, s in items:
        d.rounded_rectangle([78, y, 1122, y + 86], 14, fill="#ffffff", outline="#dce9e8", width=2)
        d.ellipse([100, y + 30, 126, y + 56], fill=TEAL)
        d.text((104, y + 32), "✓", font=f(FONT_B, 18), fill="#ffffff")
        d.text((146, y + 16), t, font=f(FONT_B, 30), fill=NAVY)
        d.text((146, y + 52), s, font=f(FONT_R, 22), fill=MUTED)
        y += 100

    d.text((78, H - 56), "kurage.exbridge.jp/kfillout.php/　｜　株式会社エクスブリッジ",
           font=f(FONT_R, 22), fill=MUTED)
    out = os.path.join(ROOT, "app", "static", "ogp.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    img.save(out)
    print(out, img.size)
    # note の見出し画像用（1280x670）。note_set_eyecatch 系はこのサイズを前提にしている
    note = img.resize((NOTE_W, NOTE_H), Image.LANCZOS)
    out2 = os.path.join(ROOT, "outputs", "listing", "note_eyecatch.png")
    os.makedirs(os.path.dirname(out2), exist_ok=True)
    note.save(out2)
    print(out2, note.size)


if __name__ == "__main__":
    main()
