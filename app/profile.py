# -*- coding: utf-8 -*-
"""「毎回おなじことを書かされる」情報の置き場。

申請書のつらさの半分は、会社名・所在地・代表者・電話を様式ごとに書き写すこと。
ここに一度入れておけば、どの様式が来ても同じ値が入る。

保存先は data/profile.json（ローカル）。**外へ送らない**。
判定に使う LLM もローカルの Ollama なので、会社情報が外部APIへ出ない。
"""
from __future__ import annotations

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "data", "profile.json")

# (キー, 画面の見出し, 例). 行政様式でよく求められる順に並べる。
FIELDS = [
    ("company", "会社名・団体名", "株式会社エクスブリッジ"),
    ("company_kana", "会社名（カナ）", "カブシキガイシャエクスブリッジ"),
    ("zip", "郵便番号", "460-0008"),
    ("address", "所在地", "愛知県名古屋市中区栄…"),
    ("representative_title", "代表者の役職", "代表取締役"),
    ("representative", "代表者名", "小嶋 篤"),
    ("tel", "電話番号", "052-…"),
    ("fax", "FAX番号", ""),
    ("email", "メールアドレス", "info@exbridge.jp"),
    ("website", "Webサイト", "https://exbridge.jp/"),
    ("corporate_number", "法人番号", ""),
    ("invoice_number", "インボイス登録番号", ""),
    ("established", "設立年月日", ""),
    ("capital", "資本金", ""),
    ("business", "事業内容", "システム開発"),
    ("contact_name", "担当者名", ""),
    ("contact_dept", "担当部署", ""),
    ("contact_tel", "担当者の電話", ""),
    ("contact_email", "担当者のメール", ""),
]
KEYS = [k for k, _, _ in FIELDS]
LABELS = {k: l for k, l, _ in FIELDS}


def load() -> dict:
    try:
        return json.load(open(PATH, encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def save(d: dict) -> dict:
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    cur = load()
    cur.update({k: (v or "").strip() for k, v in d.items() if k in KEYS})
    json.dump(cur, open(PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return cur


def filled() -> dict:
    """値が入っている項目だけ。"""
    return {k: v for k, v in load().items() if v}
