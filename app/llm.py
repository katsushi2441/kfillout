# -*- coding: utf-8 -*-
"""空欄が「何を書く欄か」をローカルLLMに判定させる。

大事なのは**埋めさせないこと**。
行政・研究機関への申請書でAIが作文すると、事実と違う内容を出すことになる。
ここでLLMにやらせるのは「この空欄はプロフィールのどの項目か」の対応づけだけで、
入る文字はプロフィールの値をそのまま使う。当てはまるものが無ければ空欄のまま返す。

モデルはローカルの gemma4（192.168.0.3）。gemma4 は思考型なので "think": false が要る
（指定しないと隠れ推論がnum_predictを食い潰して応答が空になる）。
会社情報を外部APIへ出さない意味もある。
"""
from __future__ import annotations

import json
import os
import re

import requests

OLLAMA = os.environ.get("KFILLOUT_OLLAMA", "http://192.168.0.3:11434")
MODEL = os.environ.get("KFILLOUT_MODEL", "gemma4:12b-it-qat")
TIMEOUT = int(os.environ.get("KFILLOUT_LLM_TIMEOUT", "120"))

PROMPT = """あなたは日本の申請書の書き方に詳しい事務担当者です。
申請書の空欄が「何を書く欄か」を判定してください。**文章を作ってはいけません。**

使える項目（この中から選ぶ。当てはまらなければ null）:
{fields}

空欄の情報:
- 空欄の見た目: {raw}
- その行: {line}
- 前後の行: {context}

次のJSONだけを返してください（説明は不要）:
{{"label": "この欄の項目名（日本語・15字以内）", "field": "上の一覧のキー または null", "reason": "20字以内"}}
"""


def classify(blank, fields: dict):
    """1つの空欄について {label, field, reason} を返す。失敗しても落とさない。"""
    listing = "\n".join(f"- {k}: {v}" for k, v in fields.items()) or "- （なし）"
    body = {
        "model": MODEL,
        "prompt": PROMPT.format(fields=listing, raw=blank.raw,
                                line=blank.line[:200], context=blank.context[:400]),
        "stream": False,
        "think": False,                 # gemma4 は思考型。指定しないと応答が空になる
        "options": {"temperature": 0, "num_predict": 200},
    }
    try:
        r = requests.post(f"{OLLAMA}/api/generate", json=body, timeout=TIMEOUT)
        r.raise_for_status()
        text = (r.json() or {}).get("response", "")
    except Exception as e:  # noqa: BLE001
        return {"label": "", "field": None, "reason": f"判定できず({e.__class__.__name__})"}
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return {"label": "", "field": None, "reason": "判定できず"}
    try:
        d = json.loads(m.group(0))
    except Exception:  # noqa: BLE001
        return {"label": "", "field": None, "reason": "判定できず"}
    f = d.get("field")
    if f in ("null", "None", ""):
        f = None
    return {"label": str(d.get("label") or "")[:20], "field": f,
            "reason": str(d.get("reason") or "")[:40]}


def health() -> dict:
    try:
        r = requests.get(f"{OLLAMA}/api/tags", timeout=10)
        names = [m["name"] for m in r.json().get("models", [])]
        return {"ok": MODEL in names, "model": MODEL, "models": names}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "model": MODEL, "error": str(e)}
