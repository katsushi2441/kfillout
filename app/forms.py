# -*- coding: utf-8 -*-
"""申請書の「空欄」を見つけて、書式を壊さずに埋める。

なぜ書式を壊してはいけないか:
  行政・研究機関の申請は「この様式で出してください」と指定されることが多い。
  PDFに変換してから埋める海外サービス（Instafill・pdfFiller 等）だと様式が変わるので、
  そのまま出せない。ここでは .docx / .xlsx の中身の**文字だけ**を差し替える。

docx の落とし穴:
  Word は1つの段落を複数の <w:r>（ラン）に割る。「〇〇株式会社」が
  「〇」「〇株式会社」のように分かれていることがあり、ランを単体で見ると空欄が見つからない。
  そこで**段落単位で文字列を組み立てて探し、書き戻すときはランに配り直す**。
  書式（フォント・サイズ・下線）はランの属性なので、この方法なら保たれる。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# 空欄の書かれ方。実際の様式から拾ったもの（J-SHIS利用申請の例では 〇〇 と ○月○日）
BLANK_PATTERNS = [
    (re.compile(r'[〇○]{2,}'), "〇〇"),
    (re.compile(r'[＿_]{3,}'), "＿＿"),
    (re.compile(r'[･・]{4,}'), "・・"),
    (re.compile(r'【\s{2,}】'), "【　】"),
    (re.compile(r'［\s{2,}］|\[\s{2,}\]'), "［　］"),
    (re.compile(r'（\s{2,}）|\(\s{2,}\)'), "（　）"),
    (re.compile(r'「\s{2,}」'), "「　」"),
]
# 「○年○月○日」のように記号1文字が単位に挟まれる形。
# **長いものから先に当てる**。「令和○年」だけを拾うと、置き換えたあとに「○月○日」が残る
# （実測で「令和8年9月14日○月○日」になった）。
DATE_PATTERN = re.compile(
    r'(?:令和|平成|昭和)\s*[〇○]\s*年\s*[〇○]\s*月\s*[〇○]\s*日'
    r'|[0-9]{4}\s*年\s*[〇○]\s*月\s*[〇○]\s*日'
    r'|[〇○]\s*年\s*[〇○]\s*月\s*[〇○]\s*日'
    r'|(?:令和|平成|昭和)\s*[〇○]\s*年\s*[〇○]\s*月'
    r'|(?:令和|平成|昭和)\s*[〇○]\s*年'
    r'|[0-9]{4}\s*年\s*[〇○]\s*月')


@dataclass
class Blank:
    """1つの空欄。どこにあり、周りに何が書いてあるか。"""
    id: str
    kind: str            # docx-para / docx-cell / xlsx-cell
    locator: str         # 段落番号やセル番地
    raw: str             # 空欄の見た目（〇〇 など）
    line: str            # その空欄を含む行の全文
    context: str = ""    # 前後の行（何を書く欄かの手がかり）
    label: str = ""      # 推定した項目名
    value: str = ""      # 埋める値
    source: str = ""     # profile / llm / user / (空=埋めない)
    note: str = ""


def _para_text(p) -> str:
    return "".join(r.text for r in p.runs)


def _set_para_text(p, text: str) -> None:
    """段落の文字を書き換える。書式はランの属性なので、先頭ランに寄せて残りを空にする。

    先頭ランの書式を全体に適用することになるので、段落内でフォントが変わる様式では
    見た目が変わりうる。**変わるのは文字だけで、様式（表・余白・ページ）は保たれる**。
    """
    if not p.runs:
        p.add_run(text)
        return
    p.runs[0].text = text
    for r in p.runs[1:]:
        r.text = ""


def find_blanks_docx(path: str):
    """.docx の空欄を、段落と表のセルから探す。"""
    import docx  # 遅延import（起動を軽くする）
    doc = docx.Document(path)
    blanks, lines = [], []

    def scan(text, kind, locator, idx):
        found = []
        for rx, disp in BLANK_PATTERNS:
            for m in rx.finditer(text):
                found.append((m.start(), m.group(0), disp))
        for m in DATE_PATTERN.finditer(text):
            found.append((m.start(), m.group(0), "日付"))
        out = []
        for pos, raw, disp in sorted(found):
            out.append(Blank(id=f"{kind}:{locator}:{pos}", kind=kind, locator=locator,
                             raw=raw, line=text))
        return out

    for i, p in enumerate(doc.paragraphs):
        t = _para_text(p)
        lines.append(t)
        blanks += scan(t, "docx-para", str(i), i)
    for ti, tbl in enumerate(doc.tables):
        for ri, row in enumerate(tbl.rows):
            for ci, cell in enumerate(row.cells):
                t = cell.text
                loc = f"{ti}/{ri}/{ci}"
                lines.append(t)
                blanks += scan(t, "docx-cell", loc, 0)
                # 表の空セルも「埋める場所」。左または上の見出しが項目名になる
                if not t.strip() and ci > 0:
                    head = row.cells[ci - 1].text.strip()
                    if head:
                        blanks.append(Blank(id=f"docx-cell:{loc}:empty", kind="docx-cell",
                                            locator=loc, raw="（空セル）", line=head,
                                            label=head))
    # 前後2行を手がかりとして添える
    for b in blanks:
        try:
            i = lines.index(b.line)
            b.context = " / ".join(x for x in lines[max(0, i - 2):i + 3] if x.strip())
        except ValueError:
            b.context = b.line
    return blanks, doc


def find_blanks_xlsx(path: str):
    import openpyxl
    wb = openpyxl.load_workbook(path)
    blanks = []
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                if c.value is None:
                    continue
                t = str(c.value)
                for rx, disp in BLANK_PATTERNS:
                    for m in rx.finditer(t):
                        loc = f"{ws.title}!{c.coordinate}"
                        blanks.append(Blank(id=f"xlsx-cell:{loc}:{m.start()}", kind="xlsx-cell",
                                            locator=loc, raw=m.group(0), line=t))
                if DATE_PATTERN.search(t):
                    loc = f"{ws.title}!{c.coordinate}"
                    blanks.append(Blank(id=f"xlsx-cell:{loc}:date", kind="xlsx-cell",
                                        locator=loc, raw=DATE_PATTERN.search(t).group(0), line=t))
    return blanks, wb


def apply_docx(doc, blanks) -> None:
    """埋める値が決まった空欄だけを差し替える。決まっていないものは触らない。"""
    by_para, by_cell = {}, {}
    for b in blanks:
        if not b.value:
            continue
        (by_para if b.kind == "docx-para" else by_cell).setdefault(b.locator, []).append(b)
    for i, p in enumerate(doc.paragraphs):
        bs = by_para.get(str(i))
        if not bs:
            continue
        t = _para_text(p)
        for b in bs:
            t = t.replace(b.raw, b.value, 1)
        _set_para_text(p, t)
    for ti, tbl in enumerate(doc.tables):
        for ri, row in enumerate(tbl.rows):
            for ci, cell in enumerate(row.cells):
                bs = by_cell.get(f"{ti}/{ri}/{ci}")
                if not bs:
                    continue
                if bs[0].raw == "（空セル）":
                    if cell.paragraphs:
                        _set_para_text(cell.paragraphs[0], bs[0].value)
                    continue
                for p in cell.paragraphs:
                    t = _para_text(p)
                    new = t
                    for b in bs:
                        new = new.replace(b.raw, b.value, 1)
                    if new != t:
                        _set_para_text(p, new)


def apply_xlsx(wb, blanks) -> None:
    for b in blanks:
        if not b.value or "!" not in b.locator:
            continue
        sheet, coord = b.locator.split("!", 1)
        c = wb[sheet][coord]
        c.value = str(c.value).replace(b.raw, b.value, 1)
