"""가장 최근 테스트 게시물(out_test)을 '지금 게시'로 GitHub 대기열에 올린다.

content.json 을 메모장으로 고친 뒤 실행하면, 고친 내용으로 카드를 다시 그려서 올린다.
"""
import glob
import json
import os
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from buzz import poster  # noqa: E402
from pc import ghup  # noqa: E402
from pc.run import HISTORY, KST, load_config, log  # noqa: E402

load_config()
posts = sorted(glob.glob(os.path.join(ROOT, "out_test", "*", "post")), key=os.path.getmtime)
if not posts:
    sys.exit("out_test 폴더에 테스트 게시물이 없어요. 먼저 2_테스트_지금만들기.bat 을 실행하세요.")
post_dir = posts[-1]
content = json.load(open(os.path.join(post_dir, "content.json"), encoding="utf-8"))
old_meta = json.load(open(os.path.join(post_dir, "meta.json"), encoding="utf-8"))
print(f"올릴 게시물: {old_meta['topic']}  ({post_dir})")

images = poster.render(post_dir, "C")                     # content.json 고친 내용 반영
now = datetime.now(KST)
pid = now.strftime("%Y%m%d-%H%M")
meta = {**old_meta, "id": pid, "publish_at": now.isoformat()}
json.dump(meta, open(os.path.join(post_dir, "meta.json"), "w", encoding="utf-8"), ensure_ascii=False)

files = {f"queue/{pid}/{os.path.basename(p)}": open(p, "rb").read() for p in images}
for n in ("caption.txt", "meta.json", "content.json"):
    files[f"queue/{pid}/{n}"] = open(os.path.join(post_dir, n), "rb").read()
ghup.commit_files(files, f"queue {pid} {content.get('code', '')} (manual)")

h = json.load(open(HISTORY, encoding="utf-8")) if os.path.exists(HISTORY) else []
h.append({"date": now.strftime("%Y-%m-%d"), "slot": "manual", "topic": meta["topic"], "id": pid})
json.dump(h[-200:], open(HISTORY, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
log(f"수동 업로드 완료 → queue/{pid} ({meta['topic']})")
print("\nGitHub 대기열에 올렸어요. 이제 Actions 에서 hottopic-publish 를 Run workflow 하세요.")
