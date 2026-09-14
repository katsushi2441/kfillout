# -*- coding: utf-8 -*-
"""旧形式（.doc / .xls）を LibreOffice で往復させて扱う。

行政の様式は Word 97-2003 形式（.doc）のままのものが今も多い。python-docx は .doc を読めないので、
LibreOffice（headless）で .docx へ変換し、埋めてから**元の形式へ戻して**返す。
「指定様式のまま出す」のが要件なので、戻す所まで含めて往復にする。

実測（2026-09-14・LibreOffice 7.3.7.2）:
  .docx → .doc → .docx の往復で、段落数19・文字の変化0。実用に耐える。
  ただし**往復で完全に同一になる保証は無い**ので、画面に注意書きを出す。

同時実行の注意:
  soffice はプロファイルを排他ロックする。仕事ごとに -env:UserInstallation を分けて
  ぶつからないようにする（分けないと2つ目が黙って失敗する）。
"""
from __future__ import annotations

import glob
import os
import shutil
import subprocess
import uuid

SOFFICE = shutil.which("soffice") or shutil.which("libreoffice")
TIMEOUT = int(os.environ.get("KFILLOUT_SOFFICE_TIMEOUT", "180"))
# 変換できる組み合わせ。左が受け取る形式、右が中で扱う形式
LEGACY = {".doc": ".docx", ".xls": ".xlsx", ".rtf": ".docx", ".odt": ".docx", ".ods": ".xlsx"}


def available() -> bool:
    return bool(SOFFICE)


def convert(src: str, to_ext: str, outdir: str) -> str:
    """src を to_ext へ変換して、できたファイルのパスを返す。"""
    if not SOFFICE:
        raise RuntimeError("LibreOffice が入っていません（sudo apt install libreoffice-writer libreoffice-calc）")
    os.makedirs(outdir, exist_ok=True)
    prof = os.path.join(outdir, ".lo-" + uuid.uuid4().hex[:8])
    cmd = [SOFFICE, "--headless", "--norestore",
           f"-env:UserInstallation=file://{prof}",
           "--convert-to", to_ext.lstrip("."), "--outdir", outdir, src]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
    shutil.rmtree(prof, ignore_errors=True)
    stem = os.path.splitext(os.path.basename(src))[0]
    out = os.path.join(outdir, stem + to_ext)
    if not os.path.exists(out):
        # LibreOffice は失敗しても終了コード0を返すことがある。実物の有無で判定する
        hits = glob.glob(os.path.join(outdir, stem + ".*"))
        raise RuntimeError(f"変換できませんでした（{to_ext}）: {(r.stderr or r.stdout or '')[:200]} / {hits}")
    return out
