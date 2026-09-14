# -*- coding: utf-8 -*-
"""商号の位置合わせと空欄検出の回帰テスト。

ここが壊れると**申請書の商号が別の法人名になる**（実際に踏んだ）。
  様式「〇〇株式会社」＋ 商号「株式会社エクスブリッジ」を、空欄だけ埋めると
  「エクスブリッジ株式会社」という存在しない会社名になる。

  /usr/bin/python3 -m pytest tests/ -q   （または .venv/bin/python -m pytest）
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.fill import _company_for, _today_for   # noqa: E402
from app.forms import find_blanks_docx          # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE = os.path.join(ROOT, "samples", "J-SHIS利用申請（参考例）.docx")


def _apply(line, raw, value):
    target, v = _company_for(line, raw, value)
    return line.replace(target, v, 1)


def test_company_position():
    # 様式が後置き（〇〇株式会社）
    assert _apply("〇〇株式会社", "〇〇", "株式会社エクスブリッジ") == "株式会社エクスブリッジ"
    assert _apply("〇〇株式会社", "〇〇", "エクスブリッジ株式会社") == "エクスブリッジ株式会社"
    assert _apply("〇〇株式会社", "〇〇", "エクスブリッジ") == "エクスブリッジ株式会社"
    # 様式が前置き（株式会社〇〇）
    assert _apply("株式会社〇〇", "〇〇", "株式会社エクスブリッジ") == "株式会社エクスブリッジ"
    assert _apply("株式会社〇〇", "〇〇", "エクスブリッジ株式会社") == "エクスブリッジ株式会社"
    # 法人格が無い様式
    assert _apply("申請者 〇〇", "〇〇", "株式会社エクスブリッジ") == "申請者 株式会社エクスブリッジ"
    # 一般社団法人なども同じ扱い
    assert _apply("〇〇一般社団法人", "〇〇", "一般社団法人あいち") == "一般社団法人あいち"


def test_today_format():
    assert _today_for("2026年○月○日").endswith("日")
    assert _today_for("令和○年○月○日").startswith("令和")


def test_find_blanks_sample():
    blanks, _ = find_blanks_docx(SAMPLE)
    raws = [b.raw for b in blanks]
    assert len(blanks) == 5, raws
    assert any("年" in r for r in raws), "申請日の欄が取れていない"
    assert sum(1 for r in raws if r in ("〇〇", "○○")) == 4, raws
