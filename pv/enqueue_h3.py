#!/usr/bin/env python3
"""申請書記入アシストPV用のH3実写クリップ（8秒）を rqdb4ai の h3 キューに投入する。

kpvgen/h3_workflow_template.json（1344×768×192f）を土台に、prompt / filename_prefix / seed だけ差し替える。
題材は「同じ会社情報を様式ごとに手で書き写している」場面。製品が消す手間そのものを映す。

  /home/kojima/work/kfillout/.venv/bin/python enqueue_h3.py  → job id を h3_job_ids.txt に保存
"""
import copy
import json
import os

from redis import Redis
from rq import Queue

HERE = os.path.dirname(os.path.abspath(__file__))
TPL = "/home/kojima/work/kpvgen/h3_workflow_template.json"
CLIPS = [("a", 20260914)]

base = json.load(open(TPL))
q = Queue("h3-192-168-0-14", connection=Redis.from_url("redis://127.0.0.1:6379/0"))
ids = []
for tag, seed in CLIPS:
    wf = copy.deepcopy(base)
    wf["6"]["inputs"]["prompt"] = open(os.path.join(HERE, "h3_kfillout_prompt.txt"), encoding="utf-8").read().strip()
    wf["10"]["inputs"]["noise_seed"] = seed
    wf["15"]["inputs"]["filename_prefix"] = f"h3_kfillout_{tag}"
    json.dump(wf, open(os.path.join(HERE, f"h3_kfillout_{tag}_workflow.json"), "w"), ensure_ascii=False, indent=1)
    job = q.enqueue("rqdb4ai_h3_job.h3_generate_job", workflow=wf,
                    output_filename=f"h3-kfillout-{tag}-8s.mp4",
                    job_timeout=5400, result_ttl=86400, failure_ttl=86400)
    ids.append(f"{tag} {job.id}")
    print("enqueued", tag, job.id)
open(os.path.join(HERE, "h3_job_ids.txt"), "w").write("\n".join(ids) + "\n")
print("queue count:", q.count)
