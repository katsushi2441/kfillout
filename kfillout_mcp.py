#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kurage 申請書記入アシスト — MCPサーバー（stdio・1ファイル）

Claude Code / Codex / Claude Desktop から、申請書のファイルのパスを渡して
「空欄はどこか」「何が埋まるか」を調べ、埋めたファイルを書き出すための橋。

  claude mcp add kfillout -- /home/kojima/work/kfillout/.venv/bin/python \
      /home/kojima/work/kfillout/kfillout_mcp.py

Codex は ~/.codex/config.toml に:
  [mcp_servers.kfillout]
  command = "/home/kojima/work/kfillout/.venv/bin/python"
  args = ["/home/kojima/work/kfillout/kfillout_mcp.py"]

設計（kdbagent・kaimom・klcrm・kjishin と同じ約束）:
  - **製品本体の関数をそのまま呼ぶ薄い橋**。ここで別の判定を作らない。
  - **AIに申請書の文章を作らせない。** 入る文字は「今日の日付」「保存した会社情報」
    「呼び出し側が明示した値」の3つだけ。当てはまらない欄は空のまま返す。
    この約束が破られると、事実と違う内容の申請書が出来上がる。
  - 画像PDFのように埋められない様式は「埋められない」と返す。当て推量をしない。
  - notes を必ず一緒に返し、AIが数字や値だけ抜いて断言しないようにする。
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

VERSION = "1.0.0"

try:
    from app import fill, legacy, profile
    from app.forms import apply_docx, apply_xlsx, find_blanks_docx, find_blanks_xlsx
    from app.pdfform import apply_pdf, find_blanks_pdf
except Exception as e:  # 依存が入っていない場合にJSON-RPCを壊さない
    sys.stderr.write(f"kfillout を読み込めませんでした: {e}\n")
    raise SystemExit(1)

OFFICE = (".docx", ".xlsx")
ACCEPT = OFFICE + (".pdf",) + tuple(legacy.LEGACY)
NOTES = [
    "埋めた内容は下書きです。提出の前に必ず人が全体を確かめてください。",
    "AIに文章は作らせていません。入っているのは日付・保存した会社情報・指定された値だけです。",
    "空欄のまま残っている項目は、機械では決められなかった所です。",
]


def j(v) -> str:
    return json.dumps(v, ensure_ascii=False, indent=1)


def err(msg: str):
    return False, j({"error": msg})


def _ext(path: str) -> str:
    return os.path.splitext(path)[1].lower()


def _open(path: str, work: str):
    """様式を読む。旧形式は LibreOffice で往復させる。"""
    ext = _ext(path)
    src = path
    if ext in legacy.LEGACY:
        if not legacy.available():
            raise RuntimeError("旧形式（.doc/.xls）には LibreOffice が要ります")
        src = legacy.convert(path, legacy.LEGACY[ext], os.path.join(work, "conv"))
        ext = legacy.LEGACY[ext]
    if ext == ".pdf":
        b, kind = find_blanks_pdf(src)
        return b, src, ext, kind
    if ext == ".docx":
        b, h = find_blanks_docx(src)
        return b, h, ext, ""
    b, h = find_blanks_xlsx(src)
    return b, h, ext, ""


def _as_dict(b) -> dict:
    return {"id": b.id, "label": b.label or None, "見た目": b.raw,
            "行": b.line[:160], "値": b.value or None,
            "どこから": {"date": "今日の日付", "profile": "保存した会社情報",
                        "user": "指定された値"}.get(b.source),
            "備考": b.note or None}


def t_inspect(a: dict):
    path = (a.get("path") or "").strip()
    if not path or not os.path.exists(path):
        return err(f"ファイルが見つかりません: {path}")
    if _ext(path) not in ACCEPT:
        return err(f"扱えない形式です（{_ext(path)}）。対応: {'・'.join(ACCEPT)}")
    work = os.path.join(ROOT, "outputs", "mcp")
    os.makedirs(work, exist_ok=True)
    blanks, _h, _ei, kind = _open(path, work)
    blanks = fill.plan(blanks, use_llm=bool(a.get("use_llm", True)))
    notes = list(NOTES)
    if kind == "image":
        notes.insert(0, "この様式は画像のPDFです。文字が入っていないので空欄を見つけられません。"
                        "当て推量で書くと事故になるので埋めません。Word/Excel版か記入できるPDFを探してください。")
    elif kind == "flat":
        notes.insert(0, "記入欄を持たないPDFなので、紙面の上に文字を重ねて書きます。位置がずれることがあります。")
    if _ext(path) in legacy.LEGACY:
        notes.insert(0, f"{_ext(path)} は古い形式なので、一度 {legacy.LEGACY[_ext(path)]} に直して埋め、"
                        f"{_ext(path)} に戻して書き出します。")
    return True, j({"path": path, "形式": _ext(path), "PDFの型": kind or None,
                    "空欄": len(blanks), "埋まる": sum(1 for b in blanks if b.value),
                    "内訳": fill.summary(blanks), "欄": [_as_dict(b) for b in blanks],
                    "notes": notes})


def t_fill(a: dict):
    path = (a.get("path") or "").strip()
    out_path = (a.get("out") or "").strip()
    values = a.get("values") or {}
    if not path or not os.path.exists(path):
        return err(f"ファイルが見つかりません: {path}")
    if _ext(path) not in ACCEPT:
        return err(f"扱えない形式です（{_ext(path)}）")
    if not isinstance(values, dict):
        return err("values は {空欄のid: 入れる文字} の形で渡してください")
    work = os.path.join(ROOT, "outputs", "mcp")
    os.makedirs(work, exist_ok=True)
    blanks, handle, ext_in, kind = _open(path, work)
    if kind == "image":
        return err("この様式は画像のPDFなので埋められません。Word/Excel版か記入できるPDFを探してください。")
    # use_llm=False。書き出す時点で判定が変わると、確かめた内容と違うものが出てしまう
    blanks = fill.plan(blanks, answers={str(k): str(v) for k, v in values.items()}, use_llm=False)
    if not out_path:
        stem, ext = os.path.splitext(path)
        out_path = f"{stem}_記入済み{ext}"
    tmp = os.path.join(work, "filled" + ext_in)
    if ext_in == ".pdf":
        apply_pdf(handle, tmp, blanks, kind)
    elif ext_in == ".docx":
        apply_docx(handle, blanks)
        handle.save(tmp)
    else:
        apply_xlsx(handle, blanks)
        handle.save(tmp)
    if _ext(path) in legacy.LEGACY:
        tmp = legacy.convert(tmp, _ext(path), os.path.join(work, "back"))
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    import shutil
    shutil.copyfile(tmp, out_path)
    todo = [_as_dict(b) for b in blanks if not b.value]
    return True, j({"書き出し": out_path, "埋めた数": sum(1 for b in blanks if b.value),
                    "空のまま": len(todo), "空のまま残した欄": todo,
                    "notes": NOTES + (["空のまま残っている欄があります。人が書いてください。"] if todo else [])})


def t_profile(a: dict):
    set_ = a.get("set")
    if set_:
        if not isinstance(set_, dict):
            return err("set は {キー: 値} の形で渡してください")
        unknown = [k for k in set_ if k not in profile.KEYS]
        if unknown:
            return err(f"知らないキーです: {unknown} / 使えるキー: {profile.KEYS}")
        profile.save(set_)
    cur = profile.load()
    return True, j({"項目": [{"キー": k, "見出し": l, "値": cur.get(k) or None}
                            for k, l, _ in profile.FIELDS],
                    "notes": ["この内容はこのサーバーの中だけに保存し、外部へ送りません。",
                              "ここに入れておくと、どの様式が来ても同じ値が入ります。"]})


TOOLS = [
    {"name": "kfillout_inspect",
     "description": "申請書のファイル（.docx/.xlsx/.pdf/.doc/.xls）を読み、空欄の一覧と、"
                    "そのうち何が自動で埋まるかを返す。**文章は作らない。** "
                    "画像PDFのように埋められない様式はその旨を返す。",
     "inputSchema": {"type": "object", "properties": {
         "path": {"type": "string", "description": "申請書ファイルの絶対パス"},
         "use_llm": {"type": "boolean", "description": "空欄の項目名をローカルLLMで見分ける（既定true）"}},
         "required": ["path"]}},
    {"name": "kfillout_fill",
     "description": "空欄を埋めたファイルを書き出す。**元の書式のまま**（PDFへ変換しない、"
                    "旧形式は元の形式へ戻す）。values に渡した値と、保存済みの会社情報、"
                    "今日の日付だけが入る。渡していない欄は空のまま残す。",
     "inputSchema": {"type": "object", "properties": {
         "path": {"type": "string", "description": "申請書ファイルの絶対パス"},
         "out": {"type": "string", "description": "書き出し先（省略時は元の名前＋_記入済み）"},
         "values": {"type": "object", "description": "{空欄のid: 入れる文字}。idは kfillout_inspect が返す"}},
         "required": ["path"]}},
    {"name": "kfillout_profile",
     "description": "よく使う情報（会社名・所在地・代表者など）を見る・入れる。"
                    "一度入れると、どの様式が来ても同じ値が入る。",
     "inputSchema": {"type": "object", "properties": {
         "set": {"type": "object", "description": "{キー: 値}。省略すると現在の内容を返すだけ"}},
         "required": []}},
]


def out(m) -> None:
    sys.stdout.write(json.dumps(m, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        rid = req.get("id")
        method = req.get("method") or ""
        params = req.get("params") or {}
        if rid is None and method.startswith("notifications/"):
            continue
        if method == "initialize":
            out({"jsonrpc": "2.0", "id": rid, "result": {
                "protocolVersion": str(params.get("protocolVersion") or "2024-11-05"),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "kfillout", "version": VERSION},
                "instructions":
                    "申請書のWord・Excel・PDFを読んで、空欄を見つけ、分かるところだけを埋めて"
                    "元の書式のまま書き出す窓口です。"
                    "**申請書の文章をあなたが作ってはいけません。** 入れてよいのは、利用者が明示した値、"
                    "保存済みの会社情報、今日の日付だけです。分からない欄は空のまま残し、"
                    "利用者に何を書くべきか尋ねてください。"
                    "画像PDFは埋められません。その旨をそのまま伝えてください。"
                    "書き出したファイルは下書きなので、提出前に人が確かめるよう必ず添えてください。"}})
        elif method == "ping":
            out({"jsonrpc": "2.0", "id": rid, "result": {}})
        elif method == "tools/list":
            out({"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}})
        elif method == "tools/call":
            name = params.get("name") or ""
            a = params.get("arguments") or {}
            try:
                if name == "kfillout_inspect":
                    ok, text = t_inspect(a)
                elif name == "kfillout_fill":
                    ok, text = t_fill(a)
                elif name == "kfillout_profile":
                    ok, text = t_profile(a)
                else:
                    ok, text = err(f"使えないツールです: {name}")
            except Exception as e:  # noqa: BLE001
                ok, text = err(str(e))
            out({"jsonrpc": "2.0", "id": rid,
                 "result": {"content": [{"type": "text", "text": text}], "isError": not ok}})
        elif rid is not None:
            out({"jsonrpc": "2.0", "id": rid,
                 "error": {"code": -32601, "message": f"未対応のメソッド: {method}"}})


if __name__ == "__main__":
    main()
