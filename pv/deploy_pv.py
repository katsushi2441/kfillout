#!/usr/bin/env python3
"""Kurage 申請書記入アシストのPVを公開する（kpvgen のビルド完了後に実行）。

  /home/kojima/work/kfillout/.venv/bin/python deploy_pv.py <pv.mp4> <poster.jpg>

置き場所は他のPVと同じ https://kurage.exbridge.jp/pv/（heteml）。
kpv 台帳にも登録して、kpv のレール（tags）から引けるようにする。
"""
import datetime
import ftplib
import io
import json
import os
import sys
import urllib.request

PV, POSTER = sys.argv[1], sys.argv[2]
BASE = "https://kurage.exbridge.jp/pv/"
VID = BASE + "kfillout-pv-30s.mp4"
POS = BASE + "kfillout-pv-poster.jpg"


def env():
    for line in open("/home/kojima/work/aixec/.env", encoding="utf-8"):
        if "=" in line and not line.startswith("#"):
            k, v = line.rstrip("\n").split("=", 1)
            os.environ.setdefault(k, v.strip().strip('"').strip("'"))


def main():
    env()
    f = ftplib.FTP(os.environ["FTP_HOST"], timeout=300)
    f.login(os.environ["FTP_USER"], os.environ["FTP_PASS"])
    f.cwd("/web/kurage_exbridge_jp/pv")
    f.storbinary("STOR kfillout-pv-30s.mp4", open(PV, "rb"))
    f.storbinary("STOR kfillout-pv-poster.jpg", open(POSTER, "rb"))
    print("  pv/ に配置")
    f.cwd("/web/kurage_exbridge_jp/kpv_data")
    b = io.BytesIO()
    f.retrbinary("RETR videos.json", b.write)
    k = json.loads(b.getvalue())
    vs = k["videos"] if isinstance(k, dict) else k
    if not any(v.get("id") == "kfillout" for v in vs):
        vs.append({"id": "kfillout",
                   "title": "Kurage 申請書記入アシスト — 申請書のWord・Excel・PDFを、書式そのままで埋める（買い切り110,000円）",
                   "video": VID, "poster": POS,
                   "page": "https://kurage.exbridge.jp/kfillout.php/",
                   "seconds": 30,
                   "tags": ["kfillout", "shinseisho", "kappstore", "kurage", "gyosei", "vibe"],
                   "hidden": 0, "created_at": datetime.datetime.now().isoformat()})
        f.storbinary("STOR videos.json",
                     io.BytesIO(json.dumps(k, ensure_ascii=False, indent=1).encode("utf-8")))
        print("  kpv 台帳: kfillout 追加")
    else:
        print("  kpv 台帳: 登録済み")
    f.quit()
    for u in (VID, POS):
        r = urllib.request.urlopen(urllib.request.Request(u, method="HEAD"), timeout=60)
        print(f"  {r.status} {r.headers.get('Content-Type')} {r.headers.get('Content-Length')}B {u}")


if __name__ == "__main__":
    main()
