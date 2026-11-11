"""회사 PC에서 게시물 1개 만들기 → GitHub 대기열(queue/)에 올리기.

사용법:
  python pc/run.py --slot 08:00          예약 실행(그 시간에 GitHub가 게시)
  python pc/run.py --slot now --test     테스트: GitHub에 올리지 않고 out_test 폴더에 카드만 만듦

글쓰기는 이 PC의 Claude Code(claude -p, 구독 로그인)로 한다 → Claude API 요금 0원.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from buzz import collect, commons, pexels, poster  # noqa: E402
from pc import ghup, prompts  # noqa: E402

KST = timezone(timedelta(hours=9))
SLOTS = {"08:00": "국내 유행·생활·밈", "12:30": "영화·드라마·음악·연예", "18:30": "스포츠·해외 유행",
         "21:30": "광고·마케팅·테크·브랜드"}
HISTORY = os.path.join(ROOT, "history.json")
LOG = os.path.join(ROOT, "logs")


# ---------- 설정 ----------
def load_config():
    path = os.path.join(ROOT, "config.txt")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def log(msg):
    os.makedirs(LOG, exist_ok=True)
    line = f"[{datetime.now(KST):%m-%d %H:%M:%S}] {msg}"
    print(line, flush=True)
    with open(os.path.join(LOG, f"{datetime.now(KST):%Y-%m}.log"), "a", encoding="utf-8") as f:
        f.write(line + "\n")


def telegram(msg):
    tok, chat = os.getenv("TELEGRAM_BOT_TOKEN", ""), os.getenv("TELEGRAM_CHAT_ID", "")
    if not tok or not chat:
        return
    try:
        import requests
        requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", timeout=20,
                      data={"chat_id": chat, "text": f"[핫토픽] {msg}"[:3900]})
    except Exception:
        pass


# ---------- Claude Code 호출 (구독 사용량, API 요금 없음) ----------
def claude(prompt: str, tools: str, max_turns: int = 40, timeout: int = 1500) -> str:
    exe = shutil.which("claude") or shutil.which("claude.cmd")
    if not exe:
        raise RuntimeError("claude 명령을 찾을 수 없어요. Claude Code가 설치·로그인돼 있는지 확인하세요.")
    env = dict(os.environ)
    for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):   # API 키가 있으면 API 요금이 나가므로 무조건 제거
        env.pop(k, None)
    cmd = [exe, "-p", "--output-format", "json", "--model", os.getenv("CLAUDE_MODEL", "sonnet"),
           "--allowedTools", tools, "--max-turns", str(max_turns)]
    r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8",
                       env=env, cwd=ROOT, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"claude 실행 실패({r.returncode}): {(r.stderr or r.stdout)[-800:]}")
    out = json.loads(r.stdout)
    if out.get("is_error"):
        raise RuntimeError(f"claude 오류: {str(out)[:800]}")
    return out.get("result", "")


def parse_json(text: str) -> dict:
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    s, e = text.find("{"), text.rfind("}")
    return json.loads(text[s:e + 1])


def claude_json(prompt: str, tools: str, **kw) -> dict:
    """Claude 답을 JSON으로 읽기. 따옴표 실수 등으로 깨졌으면 '고쳐서 다시 출력'을 한 번 더 요청(검색 없이, 빠름)."""
    text = claude(prompt, tools=tools, **kw)
    try:
        return parse_json(text)
    except json.JSONDecodeError as e:
        log(f"JSON 형식 오류({e}) → 형식만 고쳐 달라고 다시 요청")
        fixed = claude("아래 텍스트는 JSON인데 문법 오류가 있습니다(" + str(e) + "). 내용은 그대로 두고, "
                       "문자열 안의 큰따옴표(\")는 ‘ ’ 로 바꾸는 식으로 문법만 고쳐서 올바른 JSON 하나만 출력하세요. "
                       "설명 없이 JSON만.\n\n" + text, tools="Read", max_turns=3, timeout=600)
        return parse_json(fixed)


# ---------- 단계 ----------
def history(days=7):
    h = json.load(open(HISTORY, encoding="utf-8")) if os.path.exists(HISTORY) else []
    cut = (datetime.now(KST) - timedelta(days=days)).strftime("%Y-%m-%d")
    return [x for x in h if x["date"] >= cut]


def candidates_text():
    data = collect.collect()
    lines = []
    for it in data["items"]:
        if it["blocked"]:
            continue
        news = " / ".join(n["title"][:60] for n in it.get("news", [])[:2])
        lines.append(f"- [{it['src']}] {it['keyword']} ({it.get('traffic') or it.get('views', '')}) {news}")
    for r in data["netflix_kr"][:10]:
        lines.append(f"- [netflix_kr {r['week']}] {r['category']} {r['rank']}위 {r['title']} ({r['weeks']}주째)")
    return "\n".join(lines[:80]) or "(후보 수집 실패 — 직접 검색해서 최근 화제를 찾을 것)"


def example_text():
    ex = json.load(open(os.path.join(ROOT, "examples", "punch.json"), encoding="utf-8"))
    for c in ex["cards"]:
        c.pop("photo", None)
        c["photo_query"] = "Punch-kun" if c["type"] != "numbers" else "Ichikawa City Zoo"
    return json.dumps({"topic": "일본 아기 원숭이 펀치", "code": ex["code"], "category": "해외 유행",
                       "cards": ex["cards"], "caption": "…", "hashtags": ["#…"]}, ensure_ascii=False)


def validate(post):
    cards = [c for c in post["cards"] if isinstance(c, dict) and c.get("type")]
    # 순서가 조금 어긋나도 고쳐서 쓰기: 표지는 맨 앞, 마무리는 맨 뒤
    covers = [c for c in cards if c["type"] == "cover"]
    outros = [c for c in cards if c["type"] == "outro"]
    middle = [c for c in cards if c["type"] not in ("cover", "outro")]
    if not covers or not outros or len(middle) < 3:
        raise ValueError(f"카드 구성이 맞지 않음: {[c.get('type') for c in cards]}")
    if len(middle) > 6:                      # 너무 길면 뒤쪽 본문 카드를 덜어냄(인스타 최대 10장, 8장까지만)
        middle = middle[:6]
    post["cards"] = [covers[0]] + middle + [outros[-1]]
    if len(cards) != 7:
        log(f"카드 {len(cards)}장 → {len(post['cards'])}장으로 맞춤")
    if re.search(r"[一-鿿]", json.dumps(cards, ensure_ascii=False)):
        log("경고: 한자가 섞여 있음(글꼴에 없음) → 그대로 진행하되 깨질 수 있음")
    post["code"] = re.sub(r"[^A-Z0-9]", "", post.get("code", "TOPIC").upper())[:10] or "TOPIC"


def gather_photos(post, work):
    """카드별 검색어로 실물 사진(위키미디어) 후보 → 부족하면 Pexels."""
    queries = []
    for c in post["cards"]:
        q = c.get("photo_query")
        if q and q not in queries:
            queries.append(q)
    cands, seen = [], set()
    for q in queries[:6]:
        for c in commons.search(q, limit=5)[:4]:
            if c["title"] in seen or len(cands) >= 20:
                continue
            seen.add(c["title"])
            path = commons.download(c)
            if path:
                c["path"] = path
                cands.append(c)
        time.sleep(1)
    if len(cands) < 4:
        for q in queries[:2]:
            for c in pexels.search(q, 3):
                path = pexels.download(c)
                if path:
                    c["path"] = path
                    cands.append(c)
    log(f"사진 후보 {len(cands)}장 (실물 {len([c for c in cands if not c.get('stock')])}장)")
    return cands


def contact_sheet(cands, path):
    cols, tw, th = 4, 420, 420
    rows = (len(cands) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * tw, rows * (th + 40)), "white")
    d = ImageDraw.Draw(sheet)
    f = ImageFont.truetype(os.path.join(ROOT, "fonts", "Pretendard-ExtraBold.otf"), 34)
    for i, c in enumerate(cands, 1):
        im = Image.open(c["path"]).convert("RGB")
        im.thumbnail((tw - 10, th - 10))
        x, y = ((i - 1) % cols) * tw, ((i - 1) // cols) * (th + 40)
        sheet.paste(im, (x + 5, y + 5))
        d.rectangle((x + 5, y + 5, x + 70, y + 50), fill="red")
        d.text((x + 14, y + 8), str(i), font=f, fill="white")
        d.text((x + 8, y + th + 2), ("stock " if c.get("stock") else "") + c["title"][5:40], font=ImageFont.truetype(
            os.path.join(ROOT, "fonts", "Pretendard-Medium.otf"), 20), fill="black")
    sheet.save(path, quality=85)


def pick_photos(post, cands, work):
    if not cands:
        return {}
    sheet = os.path.join(work, "photo_candidates.jpg")
    contact_sheet(cands, sheet)
    cards = "\n".join(f"{i}. [{c['type']}] {c.get('title') if isinstance(c.get('title'), str) else ' '.join(c.get('title', []))}"
                      f" — 사진 검색어: {c.get('photo_query')}" for i, c in enumerate(post["cards"], 1))
    cand = "\n".join(f"{i}: {'stock(Pexels)' if c.get('stock') else 'wikimedia'} / {c['title'][:70]} / {c.get('desc', '')[:80]}"
                     for i, c in enumerate(cands, 1))
    res = claude_json(prompts.PICK.format(sheet=sheet, topic=post["topic"], cards=cards, cand=cand),
                      tools="Read", max_turns=6, timeout=600)
    return {int(k): int(v) for k, v in res.items() if v}


def attach(post, cands, picks):
    used_sa = False
    credits = []
    taken = set()
    for i, card in enumerate(post["cards"], 1):
        n = picks.get(i)
        if not n or n > len(cands) or n in taken:   # 같은 사진 두 번 쓰지 않기
            continue
        taken.add(n)
        c = cands[n - 1]
        card["photo"] = {"path": c["path"], "credit": c["credit"], "mode": "duo" if c.get("stock") else "color",
                         "cy": 0.4}
        if c.get("stock"):
            card["photo"]["caption"] = "자료사진"
        used_sa |= c.get("share_alike", False)
        if c["credit"] not in credits:
            credits.append(c["credit"])
    return credits, used_sa


def caption_text(post, credits, used_sa):
    cap = post["caption"].strip()
    if credits:
        cap += "\n\n📷 " + " · ".join(credits)
        if used_sa:
            cap += "\n(사진이 CC BY-SA 라이선스라 이 게시물 이미지도 같은 조건으로 공유할 수 있어요.)"
    srcs = []
    for c in post["cards"]:
        for s in c.get("sources", []):
            if s not in srcs:
                srcs.append(s)
    if srcs:
        cap += "\n출처: " + ", ".join(srcs[:8])
    cap += "\n\n" + " ".join(post.get("hashtags", [])[:12])
    return cap[:2150]


def next_publish_time(slot):
    now = datetime.now(KST)
    if slot == "now":
        return now
    h, m = map(int, slot.split(":"))
    t = now.replace(hour=h, minute=m, second=0, microsecond=0)
    return t if t > now - timedelta(minutes=30) else t + timedelta(days=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slot", default="now")
    ap.add_argument("--test", action="store_true", help="GitHub에 올리지 않고 out_test 폴더에만 만듦")
    ap.add_argument("--category", default=None, help="이번 게시물 선호 분야(지정하면 시간대 기본값 대신 사용)")
    a = ap.parse_args()
    load_config()
    pub = next_publish_time(a.slot)
    pid = pub.strftime("%Y%m%d-%H%M%S") if a.slot == "now" else pub.strftime("%Y%m%d-%H%M")
    work = os.path.join(ROOT, "out_test" if a.test else "work", pid)
    os.makedirs(work, exist_ok=True)
    log(f"=== 시작 {pid} (슬롯 {a.slot}{', 테스트' if a.test else ''})")
    try:
        hist = history()
        prompt = prompts.WRITE.format(
            now=datetime.now(KST).strftime("%Y-%m-%d %H:%M"), category=a.category or SLOTS.get(a.slot, "아무 분야"),
            history="\n".join(f"- {h['date']} {h['topic']}" for h in hist) or "(없음)",
            candidates=candidates_text(), guide=prompts.CARD_GUIDE, example=example_text())
        t0 = time.time()
        post = claude_json(prompt, tools="WebSearch,WebFetch")
        validate(post)
        log(f"주제: {post['topic']} ({time.time() - t0:.0f}초)")
        # 사실 확인(두 번째 Claude): 숫자·날짜를 다시 검색해서 틀리거나 오래된 내용을 고침
        t1 = time.time()
        try:
            checked = claude_json(prompts.FACT.format(now=datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
                                                      draft=json.dumps(post, ensure_ascii=False)),
                                  tools="WebSearch,WebFetch", max_turns=40)
            validate(checked)
            log(f"사실 확인 완료({time.time() - t1:.0f}초): {checked.get('fact_notes', [])}")
            post = checked
        except Exception as e:
            raise RuntimeError(f"사실 확인 단계 실패 → 이번 게시물은 건너뜀: {e}")
        if any(h["topic"] == post["topic"] for h in hist):
            raise RuntimeError(f"최근에 올린 주제와 같음: {post['topic']}")

        cands = gather_photos(post, work)
        picks = pick_photos(post, cands, work)
        credits, used_sa = attach(post, cands, picks)
        log(f"사진 배정: {picks}")

        # 카드 그리기
        post_dir = os.path.join(work, "post")
        os.makedirs(post_dir, exist_ok=True)
        json.dump({"date": pub.strftime("%Y-%m-%d"), "code": post["code"], "cards": post["cards"]},
                  open(os.path.join(post_dir, "content.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        images = poster.render(post_dir, "C")
        caption = caption_text(post, credits, used_sa)
        open(os.path.join(post_dir, "caption.txt"), "w", encoding="utf-8").write(caption)
        meta = {"id": pid, "publish_at": pub.isoformat(), "topic": post["topic"], "category": post.get("category")}
        json.dump(meta, open(os.path.join(post_dir, "meta.json"), "w", encoding="utf-8"), ensure_ascii=False)

        if a.test:
            log(f"테스트 완료 → {post_dir}")
            if os.name == "nt":
                subprocess.Popen(["explorer", os.path.abspath(post_dir)])
            return
        files = {f"queue/{pid}/{os.path.basename(p)}": open(p, "rb").read() for p in images}
        for n in ("caption.txt", "meta.json", "content.json"):
            files[f"queue/{pid}/{n}"] = open(os.path.join(post_dir, n), "rb").read()
        ghup.commit_files(files, f"queue {pid} {post['code']}")
        h = json.load(open(HISTORY, encoding="utf-8")) if os.path.exists(HISTORY) else []
        h.append({"date": pub.strftime("%Y-%m-%d"), "slot": a.slot, "topic": post["topic"], "id": pid})
        json.dump(h[-200:], open(HISTORY, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        log(f"GitHub 대기열에 올림 → {pub:%H:%M} 게시 예정")
    except Exception as e:
        log("실패: " + "".join(traceback.format_exception(e))[-1500:])
        telegram(f"{pid} 게시물 만들기 실패: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
