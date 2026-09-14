# -*- coding: utf-8 -*-
"""Kurage 申請書記入アシスト（内部の略称 kfillout）

申請書のファイル（Word・Excel・PDF／旧形式の .doc / .xls も）を上げると、空欄を見つけて、
**分かるところだけ**を埋めて、**元の書式のまま**返す。

なぜ作るか（2026-09-14 実測）:
  名古屋市が配っている申請様式は 4,024 件。その内訳は Word 41.1%・PDF 30.6%・Excel 9.1% で、
  ダウンロードして書くオフィス文書が 80.8%。オンラインで完結できるのは 26.9% しかない。
  しかも障害福祉 18.8%・介護保険 25.4%・高齢者福祉 28.2% と、
  **窓口へ行くのがいちばん大変な人の手続きほどオンライン化されていない。**

海外には似たサービスがある（Instafill・pdfFiller・Filly AI 等）が、多くは PDF に変換してから
埋めるので**様式が変わる**。日本の行政・研究機関は「この様式で」と指定するので、それでは出せない。
ここは .docx / .xlsx の**文字だけ**を差し替え、旧形式（.doc/.xls）は LibreOffice で往復させて
**元の形式へ戻し**、PDFは記入欄があれば欄に入れ、無ければ紙面の上に重ねる。様式をそのまま保つのが要件。
文字が1字も入っていない画像PDFは、当て推量になるので**埋めずに理由を返す**。

埋めない、という設計:
  AI に文章を作らせない。入る文字は「今日の日付」「保存したプロフィールの値」「利用者が書いた値」
  の3つだけ。AI がやるのは「この空欄はどの項目か」の対応づけだけで、
  当てはまらない欄は**空欄のまま残して画面に出す**。申請書で作文されると事故になる。
"""
from __future__ import annotations

import json
import os
import shutil
import uuid

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import (FileResponse, HTMLResponse, JSONResponse, PlainTextResponse,
                               Response)

from app import fill, legacy, llm, profile
from app.forms import apply_docx, apply_xlsx, find_blanks_docx, find_blanks_xlsx
from app.pdfform import apply_pdf, find_blanks_pdf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(ROOT, "outputs", "jobs")
PORT = int(os.environ.get("KFILLOUT_PORT", "18354"))
SITE = "Kurage 申請書記入アシスト"
PUBLIC_BASE = os.environ.get("KFILLOUT_PUBLIC_BASE", "https://kurage.exbridge.jp/kfillout.php").rstrip("/")
MAX_MB = 20
# 受け取れる形式。旧形式(.doc/.xls/.rtf/.odt/.ods)は LibreOffice で往復させる
OFFICE = (".docx", ".xlsx")
ACCEPT = OFFICE + (".pdf",) + tuple(legacy.LEGACY)

app = FastAPI(title=SITE)
os.makedirs(WORK, exist_ok=True)

CSS = """<style>
:root{color-scheme:light}
*{box-sizing:border-box}
body{margin:0;background:#f7f9fc;color:#12202f;font-family:-apple-system,"Segoe UI","Hiragino Sans","Noto Sans JP",sans-serif;line-height:1.75}
.wrap{max-width:860px;margin:0 auto;padding:28px 16px 70px}
h1{font-size:22px;margin:0 0 6px}h2{font-size:17px;margin:26px 0 8px}
a{color:#0a7d75}
.lead{color:#5b6b7a;font-size:14.5px;margin:0 0 18px}
.card{background:#fff;border:1px solid #e5ebf1;border-radius:14px;padding:20px;box-shadow:0 1px 3px rgba(16,24,40,.05);margin-bottom:16px}
.btn{display:inline-block;padding:11px 20px;font-size:15px;font-weight:800;color:#fff;background:#0a9a8f;border:0;border-radius:10px;cursor:pointer;text-decoration:none}
.btn.ghost{background:#fff;color:#0a7d75;border:2px solid #0a9a8f}
input[type=text],input[type=file],textarea{width:100%;min-width:0;padding:10px 12px;font-size:16px;border:2px solid #cfdae4;border-radius:9px;background:#fff}
input:focus,textarea:focus{outline:none;border-color:#0a9a8f}
label{display:block;font-size:12.5px;color:#5b6b76;margin:10px 0 3px}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{border:1px solid #e3e9ec;padding:8px;text-align:left;vertical-align:top}
th{background:#f5f8f9;white-space:nowrap}
.scroll{overflow-x:auto}
.tag{display:inline-block;font-size:11px;padding:2px 8px;border-radius:99px;font-weight:700}
.t-date{background:#eaf4ff;color:#1d5b9e}.t-profile{background:#eaf7f5;color:#08776e}
.t-user{background:#f3eaff;color:#5a3a9e}.t-todo{background:#fff4e5;color:#8a5a00}
.src{font-size:12.5px;color:#6b7a86}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,230px),1fr));gap:0 16px}
.note{background:#fffdf5;border:1px solid #e6d3a3;border-radius:10px;padding:12px;font-size:13.5px;margin:12px 0}
.line{font-family:ui-monospace,monospace;font-size:12.5px;color:#42505c;word-break:break-all}
</style>"""


def head(title: str) -> str:
    return (f'<!doctype html><html lang="ja"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>{title} | {SITE}</title>"
            f'<meta name="description" content="申請書のWord・Excelを上げると、空欄を見つけて分かるところだけを埋め、'
            f'元の書式のまま返します。AIに文章は作らせません。">'
            f'<link rel="canonical" href="{PUBLIC_BASE}/">' + CSS + "</head><body><div class=\"wrap\">")


KAPPSTORE = "https://kappstore.exbridge.jp/app.php?id=6ae90e27bf778a42&ref=kfillout"

FOOT = ('<p class="src" style="margin-top:30px">'
        '<a href="./">最初から</a> ・ <a href="./profile">よく使う情報</a> ・ '
        '<a href="./about">この道具について</a> ・ '
        f'<a href="{KAPPSTORE}" target="_blank" rel="noopener"><b>買い切り版（ソース同梱・MCP同梱）</b></a><br>'
        '© 株式会社エクスブリッジ　ファイルはこのサーバーの中だけで処理し、外部のAIサービスへは送りません。</p>'
        "</div></body></html>")


def esc(t) -> str:
    return (str(t or "")).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


@app.get("/healthz")
def healthz():
    return {"ok": True, "service": "kfillout", "port": PORT, "llm": llm.health().get("ok")}


@app.get("/", response_class=HTMLResponse)
def index():
    p = profile.filled()
    warn = ""
    if not p:
        warn = ('<div class="note">まだ<b>よく使う情報</b>が空です。会社名・所在地・代表者を入れておくと、'
                'どの様式が来ても同じ値が入ります。<a href="./profile">いま入れる</a></div>')
    return HTMLResponse(head("申請書を上げる") + f"""
<h1>{SITE}</h1>
<p class="lead">申請書の <b>Word・Excel・PDF</b>（旧形式の .doc / .xls も）を上げると、空欄を見つけて<b>分かるところだけ</b>を埋め、
<b>元の書式のまま</b>お返しします。分からない欄は勝手に書かずに残します。</p>
{warn}
<div class="card">
<form method="post" action="./analyze" enctype="multipart/form-data">
<label>申請書のファイル（Word・Excel・PDF／旧形式の .doc .xls も可・{MAX_MB}MBまで）</label>
<input type="file" name="f" accept=".docx,.xlsx,.pdf,.doc,.xls,.rtf,.odt,.ods" required>
<p style="margin:14px 0 0"><button class="btn" type="submit">空欄を調べる</button></p>
</form>
</div>
<h2>この道具がしないこと</h2>
<div class="card">
<p style="margin:0">AIに<b>申請書の文章を作らせません</b>。入る文字は次の3つだけです。</p>
<ul style="margin:8px 0 0">
<li><span class="tag t-date">日付</span> 申請日は今日の日付（和暦の様式なら和暦で）</li>
<li><span class="tag t-profile">よく使う情報</span> 会社名・所在地・代表者など、一度入れた値</li>
<li><span class="tag t-user">あなたの入力</span> その申請だけの値（サービス名・用途など）</li>
</ul>
<p class="src" style="margin:10px 0 0">AIがするのは「この空欄はどの項目か」の見分けだけです。
当てはまらない欄は<span class="tag t-todo">人が書く欄</span>として残します。</p>
</div>""" + FOOT)


@app.get("/profile", response_class=HTMLResponse)
def profile_get(saved: str = ""):
    cur = profile.load()
    rows = "".join(
        f'<div><label for="{k}">{esc(l)}</label>'
        f'<input type="text" id="{k}" name="{k}" value="{esc(cur.get(k,""))}" placeholder="{esc(ex)}"></div>'
        for k, l, ex in profile.FIELDS)
    msg = '<div class="note">保存しました。</div>' if saved else ""
    return HTMLResponse(head("よく使う情報") + f"""
<h1><a href="./" style="text-decoration:none;color:inherit">よく使う情報</a></h1>
<p class="lead">申請書のつらさの半分は、会社名・所在地・代表者を様式ごとに書き写すことです。
一度入れておけば、どの様式が来ても同じ値が入ります。</p>{msg}
<div class="card"><form method="post" action="./profile">
<div class="grid2">{rows}</div>
<p style="margin:16px 0 0"><button class="btn" type="submit">保存する</button>
<a class="btn ghost" href="./" style="margin-left:6px">申請書を上げる</a></p>
</form></div>
<p class="src">この内容はこのサーバーの中（data/profile.json）にだけ保存します。外部へ送りません。</p>""" + FOOT)


@app.post("/profile", response_class=HTMLResponse)
async def profile_post(request: Request):
    form = await request.form()
    profile.save({k: form.get(k, "") for k in profile.KEYS})
    return HTMLResponse('<meta http-equiv="refresh" content="0;url=./profile?saved=1">')


def _open_form(src: str, ext: str, work: str):
    """様式を読む。旧形式は LibreOffice で .docx/.xlsx へ往復させる。

    返り値 (blanks, handle, ext_in, pdf_kind)
      ext_in … 実際に読んだ形式（旧形式のときは変換後）
      pdf_kind … acroform / flat / image（PDF以外は "")
    """
    if ext in legacy.LEGACY:
        if not legacy.available():
            raise RuntimeError("旧形式（.doc/.xls）を扱うには LibreOffice が要ります")
        src = legacy.convert(src, legacy.LEGACY[ext], os.path.join(work, "conv"))
        ext = legacy.LEGACY[ext]
    if ext == ".pdf":
        blanks, kind = find_blanks_pdf(src)
        return blanks, src, ext, kind
    if ext == ".docx":
        b, h = find_blanks_docx(src)
        return b, h, ext, ""
    b, h = find_blanks_xlsx(src)
    return b, h, ext, ""


def _save_form(handle, blanks, ext_in: str, pdf_kind: str, src: str, out: str) -> None:
    if ext_in == ".pdf":
        apply_pdf(src, out, blanks, pdf_kind)
    elif ext_in == ".docx":
        apply_docx(handle, blanks)
        handle.save(out)
    else:
        apply_xlsx(handle, blanks)
        handle.save(out)


def _job_dir(job: str) -> str:
    d = os.path.join(WORK, job)
    if not os.path.isdir(d) or ".." in job or "/" in job:
        raise ValueError("job")
    return d


def _blanks_table(blanks, job: str) -> str:
    rows = []
    for b in blanks:
        if b.source == "date":
            tag = '<span class="tag t-date">日付</span>'
        elif b.source == "profile":
            tag = '<span class="tag t-profile">よく使う情報</span>'
        elif b.source == "user":
            tag = '<span class="tag t-user">あなたの入力</span>'
        else:
            tag = '<span class="tag t-todo">人が書く欄</span>'
        rows.append(
            f'<tr><td>{tag}<br><b>{esc(b.label or "？")}</b>'
            f'<div class="src">{esc(b.note)}</div></td>'
            f'<td><div class="line">{esc(b.line[:120])}</div>'
            f'<div class="src">空欄の見た目: {esc(b.raw)}</div></td>'
            f'<td><input type="text" name="v:{esc(b.id)}" value="{esc(b.value)}" '
            f'placeholder="ここに書くと入ります"></td></tr>')
    return ('<div class="scroll"><table><tr><th>何の欄か</th><th>様式のどこか</th>'
            '<th>入れる文字</th></tr>' + "".join(rows) + "</table></div>")


@app.post("/analyze", response_class=HTMLResponse)
async def analyze(f: UploadFile = File(...)):
    name = os.path.basename(f.filename or "form")
    ext = os.path.splitext(name)[1].lower()
    if ext not in ACCEPT:
        return HTMLResponse(head("使えない形式") +
                            "<h1>この形式は読めません</h1><p class=\"lead\">対応しているのは "
                            + "・".join(ACCEPT) + " です。</p>"
                            '<p><a class="btn" href="./">戻る</a></p>' + FOOT, status_code=400)
    data = await f.read()
    if len(data) > MAX_MB * 1024 * 1024:
        return HTMLResponse(head("大きすぎます") + f"<h1>{MAX_MB}MBまでです</h1>"
                            '<p><a class="btn" href="./">戻る</a></p>' + FOOT, status_code=400)
    job = uuid.uuid4().hex[:12]
    d = os.path.join(WORK, job)
    os.makedirs(d, exist_ok=True)
    src = os.path.join(d, "original" + ext)
    open(src, "wb").write(data)
    json.dump({"name": name, "ext": ext}, open(os.path.join(d, "meta.json"), "w", encoding="utf-8"),
              ensure_ascii=False)

    try:
        blanks, _h, ext_in, pdf_kind = _open_form(src, ext, d)
    except Exception as e:  # noqa: BLE001
        return HTMLResponse(head("読めませんでした") + f"<h1>この様式は読めませんでした</h1>"
                            f'<p class="lead">{esc(e)}</p>'
                            '<p><a class="btn" href="./">戻る</a></p>' + FOOT, status_code=400)
    json.dump({"name": name, "ext": ext, "ext_in": ext_in, "pdf_kind": pdf_kind},
              open(os.path.join(d, "meta.json"), "w", encoding="utf-8"), ensure_ascii=False)
    blanks = fill.plan(blanks)
    s = fill.summary(blanks)
    notes = []
    if pdf_kind == "image":
        notes.append('<div class="note"><b>この様式は画像のPDFです。</b>'
                     '文字が1文字も入っていないので、どこが空欄かを機械で見つけられません。'
                     '当て推量で書くと事故になるので埋めません。'
                     '可能なら Word / Excel 版か、記入できるPDFをお探しください。</div>')
    elif pdf_kind == "flat":
        notes.append('<div class="note">記入欄を持たないPDFなので、<b>元の紙面の上に文字を重ねて</b>書きます。'
                     '位置がずれることがあるので、出てきたファイルを必ず目で確かめてください。</div>')
    if ext in legacy.LEGACY:
        notes.append(f'<div class="note">{esc(ext)} は古い形式なので、'
                     f'一度 {esc(legacy.LEGACY[ext])} に直して埋め、<b>{esc(ext)} に戻して</b>お返しします。'
                     '往復で見た目が完全に同じになる保証はないので、目で確かめてください。</div>')
    if not blanks:
        body = "".join(notes) + ('<div class="note">空欄が見つかりませんでした。'
                '〇〇・＿＿・（　）のような印が無い様式かもしれません。</div>')
    else:
        body = "".join(notes) + _blanks_table(blanks, job)
    return HTMLResponse(head("空欄を確かめる") + f"""
<h1>{esc(name)}</h1>
<p class="lead">空欄 <b>{s['total']}</b> か所のうち <b>{s['filled']}</b> か所を埋めました
（日付 {s['by_source']['date']}・よく使う情報 {s['by_source']['profile']}）。
残り <b>{s['todo']}</b> か所は<b>人が書く欄</b>です。下の欄に書くと一緒に入ります。</p>
<div class="card"><form method="post" action="./download">
<input type="hidden" name="job" value="{job}">
{body}
<p style="margin:16px 0 0"><button class="btn" type="submit">この内容で埋めてダウンロード</button>
<a class="btn ghost" href="./" style="margin-left:6px">別の様式にする</a></p>
</form></div>
<p class="src">埋めるのは文字だけです。表・余白・ページの形はそのまま残ります。
提出の前に、必ずご自身で全体を確かめてください。</p>""" + FOOT)


@app.post("/download")
async def download(request: Request):
    form = await request.form()
    job = str(form.get("job") or "")
    try:
        d = _job_dir(job)
    except ValueError:
        return JSONResponse({"error": "その作業は見つかりません"}, status_code=404)
    meta = json.load(open(os.path.join(d, "meta.json"), encoding="utf-8"))
    ext, name = meta["ext"], meta["name"]
    src = os.path.join(d, "original" + ext)
    answers = {k[2:]: str(v) for k, v in form.items() if k.startswith("v:")}

    blanks, handle, ext_in, pdf_kind = _open_form(src, ext, d)
    # 画面で確定した値だけを使う（ここでLLMは呼ばない。押すたびに変わるのを防ぐ）。
    # plan() が answers を取り込み、商号の位置合わせまでやるので、あとから value を上書きしない
    blanks = fill.plan(blanks, answers=answers, use_llm=False)
    read_src = handle if ext_in == ".pdf" else src
    out = os.path.join(d, "filled" + ext_in)
    _save_form(handle, blanks, ext_in, pdf_kind, read_src, out)
    # 旧形式は元の形式へ戻す（指定様式のまま出せるようにするのが要件）
    if ext in legacy.LEGACY:
        out = legacy.convert(out, ext, os.path.join(d, "back"))
    stem = os.path.splitext(name)[0]
    return FileResponse(out, filename=f"{stem}_記入済み{ext}",
                        media_type="application/octet-stream")


@app.get("/about", response_class=HTMLResponse)
def about():
    return HTMLResponse(head("この道具について") + """
<h1>この道具について</h1>
<h2>何をするか</h2>
<p>申請書の <b>Word・Excel・PDF</b>（旧形式の .doc / .xls / .rtf / .odt / .ods も）を上げると、
〇〇・＿＿・（　）のような空欄を見つけて、分かるところだけを埋め、<b>元の書式のまま</b>返します。</p>
<div class="scroll"><table>
<tr><th>形式</th><th>どう扱うか</th></tr>
<tr><td>Word（.docx）・Excel（.xlsx）</td><td>文字だけを差し替え</td></tr>
<tr><td>旧形式（.doc / .xls / .rtf / .odt / .ods）</td><td>一度いまの形式に直して埋め、<b>元の形式に戻して</b>お返しします</td></tr>
<tr><td>PDF（記入できるもの）</td><td>入力欄に値を入れます</td></tr>
<tr><td>PDF（記入欄が無いもの）</td><td>紙面の上に文字を重ねます。位置がずれることがあります</td></tr>
<tr><td>PDF（画像）</td><td><b>埋めません。</b>文字が入っていないので当て推量になり、事故のもとです</td></tr>
</table></div>
<h2>なぜ作ったか</h2>
<p>名古屋市が配っている申請様式を数えると <b>4,024件</b>、その <b>80.8%</b> が
Word・PDF・Excel のダウンロード様式で、オンラインで完結できるのは <b>26.9%</b> でした
（2026年9月14日・市の「申請・手続き検索」の公開データを集計）。
しかも <b>障害福祉 18.8%・介護保険 25.4%・高齢者福祉 28.2%</b> と、
窓口へ行くのがいちばん大変な人の手続きほど、オンライン化されていません。</p>
<h2>AIに文章は作らせません</h2>
<p>入る文字は「今日の日付」「保存したよく使う情報」「あなたが書いた値」の3つだけです。
AIがするのは「この空欄はどの項目か」を見分けることだけで、当てはまらない欄は空のまま残します。
申請書で作文されると事故になるためです。判定に使うAIもこのサーバーの中（ローカルのLLM）で動きます。</p>
<h2>気をつけていること</h2>
<ul>
<li>様式を PDF に変換しません。指定様式のまま出せます</li>
<li>ファイルと入力内容は、このサーバーの外へ出しません</li>
<li>「〇〇株式会社」の欄に「株式会社◯◯」を丸ごと入れて重複させないようにしています</li>
</ul>
<p class="src">提出の前に、必ずご自身で全体を確かめてください。この道具の出力は下書きです。</p>""" + FOOT)


@app.get("/robots.txt", response_class=PlainTextResponse)
def robots():
    # /analyze と /download は POST の受け口。クロールさせない
    return (f"User-agent: *\nAllow: /\nDisallow: /analyze\nDisallow: /download\n\n"
            f"Sitemap: {PUBLIC_BASE}/sitemap.xml\n")


@app.get("/sitemap.xml")
def sitemap():
    urls = ["/", "/profile", "/about"]
    xml = ('<?xml version="1.0" encoding="UTF-8"?>'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
           + "".join(f"<url><loc>{PUBLIC_BASE}{u}</loc><changefreq>monthly</changefreq></url>"
                     for u in urls)
           + "</urlset>")
    return Response(content=xml, media_type="application/xml")


@app.get("/llms.txt", response_class=PlainTextResponse)
def llms():
    return f"""# {SITE}

> 申請書の Word・Excel・PDF（旧形式の .doc / .xls も）を上げると、空欄を見つけて
> 分かるところだけを埋め、元の書式のまま返す道具。

## 特徴
- **様式が変わらない。** .docx / .xlsx は文字だけを差し替え、旧形式は元の形式へ戻して返す。
  海外の同種サービスの多くはPDFへ変換するので様式が変わり、指定様式として提出できない
- PDFは3つの型を見分ける: 記入できるPDF＝欄に入れる／記入欄が無いPDF＝紙面に重ねる／
  **画像PDF＝埋めずに理由を返す**（当て推量で書くと申請書として事故になる）
- AIに文章を作らせない。入る文字は「今日の日付」「保存した会社情報」「利用者の入力」だけ
- 判定はローカルのLLM。ファイルも入力も外部のAIサービスへ送らない

## 背景（実測）
名古屋市の申請様式 4,024件のうち 80.8% がダウンロード様式（Word 41.1%・PDF 30.6%・Excel 9.1%）。
オンラインで完結できるのは 26.9%。障害福祉 18.8%・介護保険 25.4%・高齢者福祉 28.2% と、
移動が困難な人の手続きほどオンライン化が遅れている（2026-09-14 市の公開データを集計）。

## 使い方
- 申請書を上げる: {PUBLIC_BASE}/
- よく使う情報: {PUBLIC_BASE}/profile
- この道具について: {PUBLIC_BASE}/about

## 買い切り版
- 商品ページ: https://kappstore.exbridge.jp/app.php?id=6ae90e27bf778a42
- 税込55,000円。ソースコード（MIT）・設置手順書・MCPサーバーを同梱。自社サーバーで動かせる。

運営: 株式会社エクスブリッジ https://exbridge.jp/
"""
