# -*- coding: utf-8 -*-
"""PDF様式を埋める。3つの型を見分けて、できないものは「できない」と返す。

行政のPDF様式には3つある（2026-09-14 実測）:
  1. 記入可能PDF（AcroForm）… 入力欄がPDFの機能として入っている。pypdf で値を入れれば確実
  2. 平らなPDF（文字はある）  … 名古屋市の戸籍申請書がこれ。AcroFormのフィールドは0個で、
                                罫線とラベルで作った紙の様式。〇〇・＿＿ の位置を探して上に書く
  3. 画像のPDF               … 文字が1文字も取れない。名古屋市のハザードマップがこれ
                                （千種区の洪水図は5.5MB・1ページでテキスト0文字）。**埋められない**

3 を黙って諦めるのではなく「これは画像なので埋められません」と返すのが大事。
申請書で当て推量をすると事故になる。
"""
from __future__ import annotations

import io
import os

import pdfplumber
import pypdf
from reportlab.lib.colors import black
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas

from app.forms import BLANK_PATTERNS, Blank, DATE_PATTERN

# 日本語は reportlab 同梱のCIDフォントで出す（フォントファイルを持ち歩かなくてよい）
JP_FONT = "HeiseiKakuGo-W5"
_font_ready = False


def _font():
    global _font_ready
    if not _font_ready:
        pdfmetrics.registerFont(UnicodeCIDFont(JP_FONT))
        _font_ready = True
    return JP_FONT


def kind_of(path: str) -> str:
    """acroform / flat / image を返す。"""
    r = pypdf.PdfReader(path)
    if r.get_fields():
        return "acroform"
    with pdfplumber.open(path) as pdf:
        chars = sum(len(p.chars) for p in pdf.pages[:5])
    # 画像PDFは文字が取れない。名古屋市のハザードマップ（千種区・洪水）は 5.5MB・1ページで
    # 抽出できた文字が 1 文字だった（実測）。10文字を境にする。
    return "flat" if chars >= 10 else "image"


def find_blanks_pdf(path: str):
    """空欄と、その型を返す。flat のときは書き込む座標まで持たせる。"""
    k = kind_of(path)
    blanks = []
    if k == "acroform":
        r = pypdf.PdfReader(path)
        for name, f in (r.get_fields() or {}).items():
            ft = str(f.get("/FT") or "")
            if ft not in ("/Tx", "/Ch"):     # テキストと選択肢だけ扱う（チェックボックスは今後）
                continue
            blanks.append(Blank(id=f"pdf-field:{name}", kind="pdf-field", locator=name,
                                raw="（入力欄）", line=str(f.get("/TU") or name),
                                label=str(f.get("/TU") or name)))
        return blanks, k
    if k == "image":
        return [], k
    # flat: 〇〇 や ＿＿ の位置を文字単位で探す
    with pdfplumber.open(path) as pdf:
        for pno, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            words = page.extract_words(use_text_flow=True, keep_blank_chars=True)
            lines = [l for l in text.split("\n") if l.strip()]
            for rx, disp in BLANK_PATTERNS + [(DATE_PATTERN, "日付")]:
                for line in lines:
                    for m in rx.finditer(line):
                        # その文字列を含む語の座標を取る（無ければ座標なしで報告だけする）
                        box = next((w for w in words if m.group(0)[:2] in w["text"]), None)
                        b = Blank(id=f"pdf-flat:{pno}:{line[:12]}:{m.start()}", kind="pdf-flat",
                                  locator=f"{pno}", raw=m.group(0), line=line)
                        if box:
                            b.note = f"x={box['x0']:.0f} y={box['top']:.0f}"
                            b.context = f"{pno}|{box['x0']}|{box['top']}|{box['bottom']}|{box['x1']}"
                        blanks.append(b)
    # 同じ行の同じ位置を二重に拾わない
    seen, out = set(), []
    for b in blanks:
        key = (b.locator, b.line, b.raw)
        if key in seen:
            continue
        seen.add(key)
        out.append(b)
    return out, k


def apply_pdf(src: str, out: str, blanks, kind: str) -> None:
    if kind == "acroform":
        r = pypdf.PdfReader(src)
        w = pypdf.PdfWriter(clone_from=src)
        vals = {b.locator: b.value for b in blanks if b.value}
        for page in w.pages:
            try:
                # auto_regenerate=False が要る。True だと pypdf が自前で見た目を作ろうとして、
                # 欄のフォントが日本語を持たないPDFで文字化けする（実測で警告が出た）。
                # False にして NeedAppearances を立てると、**開いたビューア側が描く**ので化けない。
                w.update_page_form_field_values(page, vals, auto_regenerate=False)
            except Exception:  # noqa: BLE001  フィールドが無いページは飛ばす
                pass
        w.set_need_appearances_writer(True)   # 値を画面に出させる
        with open(out, "wb") as f:
            w.write(f)
        return
    # flat: 元のPDFの上に文字だけの層を重ねる（元のページは一切書き換えない）
    r = pypdf.PdfReader(src)
    by_page = {}
    for b in blanks:
        if not b.value or not b.context or "|" not in b.context:
            continue
        pno, x0, top, bottom, x1 = b.context.split("|")
        by_page.setdefault(int(pno), []).append((float(x0), float(top), float(bottom), b.value))
    w = pypdf.PdfWriter()
    for i, page in enumerate(r.pages):
        items = by_page.get(i)
        if items:
            ph = float(page.mediabox.height)
            pw = float(page.mediabox.width)
            buf = io.BytesIO()
            c = canvas.Canvas(buf, pagesize=(pw, ph))
            c.setFont(_font(), 10)
            c.setFillColor(black)
            for x0, top, bottom, val in items:
                # pdfplumber は上からの座標、PDFは下からの座標
                c.drawString(x0, ph - bottom + 1, val)
            c.save()
            buf.seek(0)
            page.merge_page(pypdf.PdfReader(buf).pages[0])
        w.add_page(page)
    with open(out, "wb") as f:
        w.write(f)
