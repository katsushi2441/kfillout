# -*- coding: utf-8 -*-
"""空欄 → 埋める値、を決める。埋められないものは埋めない。

ここが製品の肝。AIに文章を作らせず、次の3つだけで埋める:
  1) 日付      … 申請日は今日。様式が「令和○年」なら和暦、「2026年○月○日」なら西暦に合わせる
  2) プロフィール … 会社名・所在地・代表者など、毎回おなじ値
  3) 利用者の入力 … その申請だけの値（サービス名・用途など）

実測で分かった罠（2026-09-14・J-SHIS利用申請の様式）:
  ・様式に「〇〇株式会社」と書いてある所へ「株式会社エクスブリッジ」を丸ごと入れると
    「株式会社エクスブリッジ株式会社」になる。**様式側に既にある法人格は取り除いて入れる。**
  ・「リスク管理システム〇〇」のような欄は会社情報では決まらない。
    ここはAIに書かせず、利用者に聞く欄として画面に出す。
"""
from __future__ import annotations

import datetime
import re

from concurrent.futures import ThreadPoolExecutor

from app import llm, profile

# 法人格。様式側に既にあるときは、プロフィールの値から取り除いて入れる
CORP = ("株式会社", "有限会社", "合同会社", "合資会社", "合名会社", "一般社団法人",
        "一般財団法人", "公益社団法人", "公益財団法人", "特定非営利活動法人")
JP_ERA_RE = re.compile(r'令和\s*[〇○]\s*年')
WAREKI_START = 2018   # 令和元年 = 2019年


def _today_for(raw: str) -> str:
    """空欄の**見た目に合わせた**今日の日付を作る。

    「令和○年」だけの欄に「令和8年9月14日」を入れると、後ろの「○月○日」が残って
    「令和8年9月14日○月○日」になる（実測で踏んだ）。
    月・日を含むかどうかを見て、同じ形のものを返す。
    """
    d = datetime.date.today()
    era = bool(re.search(r'令和|平成|昭和', raw))
    head = f"令和{d.year - WAREKI_START}年" if era else f"{d.year}年"
    if "日" in raw:
        return f"{head}{d.month}月{d.day}日"
    if "月" in raw:
        return f"{head}{d.month}月"
    return head


def _company_for(line: str, raw: str, value: str):
    """法人格の位置を合わせる。返すのは (置き換える対象, 入れる文字)。

    様式は「〇〇株式会社」（後置き）を想定していても、会社が「株式会社エクスブリッジ」（前置き）
    だと、空欄だけを埋めると **「エクスブリッジ株式会社」という別の法人名**になる。
    申請書で商号を間違えるのは致命的なので、位置が違うときは
    **様式の法人格ごと置き換えて**正しい商号をそのまま入れる。
    """
    i = line.find(raw)
    after = line[i + len(raw):] if i >= 0 else ""
    before = line[:i] if i >= 0 else ""
    for c in CORP:
        form_suffix = after.startswith(c)      # 様式が 〇〇株式会社
        form_prefix = before.endswith(c)       # 様式が 株式会社〇〇
        if not (form_suffix or form_prefix):
            continue
        val_prefix = value.startswith(c)       # 商号が 株式会社エクスブリッジ
        val_suffix = value.endswith(c)         # 商号が エクスブリッジ株式会社
        if not (val_prefix or val_suffix):
            # 商号に法人格が無い（略称で登録している／市や団体など）。
            # 様式の「株式会社」は残したまま空欄だけ埋める。ただし合っているかは分からないので
            # 呼び出し側で注意書きを出す（NEEDS_CORP_CHECK）。
            return raw, value
        if (form_suffix and val_suffix) or (form_prefix and val_prefix):
            # 位置が同じ。空欄には法人格を除いた部分だけを入れる
            return raw, value.replace(c, "", 1).strip()
        # 位置が違う。様式の法人格ごと置き換えて、正しい商号をそのまま入れる
        return (raw + c) if form_suffix else (c + raw), value
    return raw, value


def plan(blanks, answers: dict | None = None, use_llm: bool = True):
    """各空欄に value と source を入れて返す。決まらないものは value='' のまま。"""
    answers = answers or {}
    prof = profile.filled()
    fields = {k: profile.LABELS[k] for k in prof}      # 値が入っている項目だけ候補に出す

    # 1) 日付はLLMを待たずに決まる
    rest = []
    for b in blanks:
        if b.id in answers and answers[b.id].strip():
            b.value, b.source, b.label = answers[b.id].strip(), "user", b.label or "入力済み"
            continue
        if re.search(r'[〇○]\s*[年月日]', b.raw):
            b.value, b.source, b.label = _today_for(b.raw), "date", "申請日"
            b.note = "今日の日付を入れています。提出日が違うときは直してください。"
            continue
        rest.append(b)

    # 2) 残りはLLMに「どの項目か」だけ聞く（並列。1件10秒前後かかるため）
    if use_llm and rest and fields:
        with ThreadPoolExecutor(max_workers=6) as ex:
            for b, r in zip(rest, ex.map(lambda x: llm.classify(x, fields), rest)):
                b.label = r["label"] or b.label
                b.note = r["reason"]
                f = r["field"]
                if f and f in prof:
                    b.value, b.source = prof[f], "profile"
    elif rest:
        for b in rest:
            b.note = "プロフィールが空です" if not fields else ""
    # 3) 商号の位置合わせ。**LLMを使う経路でも使わない経路でも同じ結果になるよう最後にやる**
    #    （ダウンロード時は use_llm=False で呼ぶので、LLM分岐の中でやると効かない。実測で判明）
    for b in blanks:
        if not b.value or not any(c in b.value for c in CORP):
            if b.value and any(c in b.line for c in CORP):
                c = next(c for c in CORP if c in b.line)
                b.note = f"様式は「{c}」を前提にしています。違うときは直してください"
            continue
        target, v = _company_for(b.line, b.raw, b.value)
        b.raw, b.value = target, v
    return blanks


def summary(blanks):
    filled = [b for b in blanks if b.value]
    todo = [b for b in blanks if not b.value]
    return {"total": len(blanks), "filled": len(filled), "todo": len(todo),
            "by_source": {s: sum(1 for b in filled if b.source == s)
                          for s in ("date", "profile", "user")}}
