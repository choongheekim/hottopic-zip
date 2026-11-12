"""GitHub Actions: 게시 시간이 된 대기열(queue/) 게시물을 인스타에 올린다. (Claude 호출 없음 → 0원)

- queue/<id>/meta.json 의 publish_at 이 지났고 published.json 이 없는 것 중 가장 오래된 1개만 게시
- 게시 후 published.json 기록, 5일 지난 게시 완료 폴더는 삭제(저장소 용량 관리)
"""
import glob
import json
import os
import shutil
import sys
from datetime import datetime, timedelta, timezone

from buzz.publish import publish_carousel, publish_reel

KST = timezone(timedelta(hours=9))


def reel_caption(cap: str) -> str:
    """인스타 해시태그 5개 제한에 맞추고 예전 문구를 정리."""
    import re
    lines = cap.replace("매일 3~4번", "매일 2번").split("\n")
    tags = [t for t in re.findall(r"#\S+", lines[-1])] if lines and lines[-1].startswith("#") else []
    if tags:
        lines[-1] = " ".join(tags[:5])
    return "\n".join(lines)
now = datetime.now(KST)
repo = os.environ["GITHUB_REPOSITORY"]
branch = os.getenv("GITHUB_REF_NAME", "main")
dry = os.getenv("DRY_RUN", "false") == "true"

pending = []
for d in sorted(glob.glob("queue/*/")):
    meta_p = os.path.join(d, "meta.json")
    if not os.path.exists(meta_p) or os.path.exists(os.path.join(d, "published.json")):
        continue
    meta = json.load(open(meta_p, encoding="utf-8"))
    if datetime.fromisoformat(meta["publish_at"]) <= now + timedelta(minutes=15):
        pending.append((d, meta))

changed = False
# 카드는 이미 올라갔는데 릴스(reel.mp4)만 나중에 넣은 경우 → 릴스만 올림(1개)
reel_only = None
for d in sorted(glob.glob("queue/*/")):
    pj, rp = os.path.join(d, "published.json"), os.path.join(d, "reel.mp4")
    if os.path.exists(pj) and os.path.exists(rp):
        rec = json.load(open(pj, encoding="utf-8"))
        if "reel_id" not in rec and "reel_error" not in rec:
            reel_only = (d, rec)
            break
if reel_only and not pending:
    d, rec = reel_only
    cap = open(os.path.join(d, "caption.txt"), encoding="utf-8").read()
    print(f"릴스만 게시: {d}")
    if not dry:
        try:
            rec["reel_id"] = publish_reel(os.path.join(d, "reel.mp4"), reel_caption(cap), share_to_feed=False)
        except Exception as e:
            print(f"릴스 게시 실패: {e}")
            rec["reel_error"] = str(e)[:300]
        json.dump(rec, open(os.path.join(d, "published.json"), "w", encoding="utf-8"))
        changed = True
elif not pending:
    print("게시할 대기열 없음")
else:
    d, meta = pending[0]
    images = sorted(glob.glob(os.path.join(d, "[0-9][0-9].jpg")))
    urls = [f"https://raw.githubusercontent.com/{repo}/{branch}/{p.replace(os.sep, '/')}" for p in images]
    caption = open(os.path.join(d, "caption.txt"), encoding="utf-8").read()
    print(f"게시: {meta['id']} {meta['topic']} ({len(urls)}장)")
    if dry:
        print("DRY_RUN — 실제 게시 안 함", urls[:2])
    else:
        media_id = publish_carousel(urls, caption)
        rec = {"media_id": media_id, "published_at": now.isoformat()}
        json.dump(rec, open(os.path.join(d, "published.json"), "w", encoding="utf-8"))
        changed = True
        # 같은 주제의 릴스(새로운 사람에게 닿는 통로). 피드 격자에는 안 겹치게 릴스 탭에만.
        reel_p = os.path.join(d, "reel.mp4")
        if os.path.exists(reel_p):
            try:
                rec["reel_id"] = publish_reel(reel_p, reel_caption(caption), share_to_feed=False)
            except Exception as e:
                print(f"릴스 게시 실패(카드 게시물은 정상): {e}")
                rec["reel_error"] = str(e)[:300]
            json.dump(rec, open(os.path.join(d, "published.json"), "w", encoding="utf-8"))
    if len(pending) > 1:
        print(f"남은 대기 {len(pending) - 1}개 → 다음 실행 때 게시")

# 용량 관리: 게시 끝난 지 5일 넘은 폴더 삭제
for d in glob.glob("queue/*/"):
    pj = os.path.join(d, "published.json")
    if os.path.exists(pj):
        t = datetime.fromisoformat(json.load(open(pj))["published_at"])
        if now - t > timedelta(days=5):
            shutil.rmtree(d)
            changed = True
open(os.environ.get("GITHUB_OUTPUT", os.devnull), "a").write(f"changed={'true' if changed else 'false'}\n")
sys.exit(0)
