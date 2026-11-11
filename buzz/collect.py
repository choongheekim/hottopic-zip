"""오늘의 화제 후보 수집 (전부 무료·키 없음).

- 구글 트렌드 급상승 RSS (한국·미국·일본)
- 위키백과 일간 조회수 TOP (한국어, 어제 기준)
- 넷플릭스 한국 TOP10 (주간 공식 파일)

결과는 candidates.json 으로 저장. 정치·사건사고는 여기서 1차로 거르고,
최종 선정은 PC의 Claude Code(claude -p)가 한다.
"""
import csv
import io
import json
import re
from datetime import date, datetime, timedelta, timezone
from html import unescape

import requests

UA = {"User-Agent": "daily-buzz/1.0 (https://github.com/choongheekim/daily-buzz)"}
KST = timezone(timedelta(hours=9))

# 정치·사건사고·선정적 주제 1차 차단 (최종 판단은 Claude가 한 번 더)
BLOCK = re.compile(
    r"대통령|국회|의원|장관|총리|정당|민주당|국민의힘|선거|개표|특검|검찰|기소|재판|판결|탄핵|"
    r"사망|숨져|사고|추돌|화재|살해|폭행|성범죄|마약|음주운전|자살|실종|체포|구속|"
    r"대구교도소|교도소"
)


def _get(url, **kw):
    r = requests.get(url, headers=UA, timeout=30, **kw)
    r.raise_for_status()
    return r


def google_trends(geo: str) -> list[dict]:
    x = _get(f"https://trends.google.com/trending/rss?geo={geo}").text
    out = []
    for it in re.findall(r"<item>(.*?)</item>", x, re.S):
        g = lambda tag: (m := re.search(fr"<{tag}>(.*?)</{tag}>", it, re.S)) and unescape(m.group(1)).strip()
        news = [
            {"title": unescape(t), "url": unescape(u), "source": unescape(s)}
            for t, u, s in re.findall(
                r"<ht:news_item_title>(.*?)</ht:news_item_title>.*?<ht:news_item_url>(.*?)</ht:news_item_url>.*?<ht:news_item_source>(.*?)</ht:news_item_source>",
                it, re.S)
        ]
        out.append({"src": f"google_trends_{geo}", "keyword": g("title"),
                    "traffic": g("ht:approx_traffic"), "news": news[:3]})
    return out


def wikipedia_top(lang="ko", n=40) -> list[dict]:
    d = datetime.now(KST).date() - timedelta(days=1)
    url = f"https://wikimedia.org/api/rest_v1/metrics/pageviews/top/{lang}.wikipedia/all-access/{d:%Y/%m/%d}"
    arts = _get(url).json()["items"][0]["articles"]
    skip = re.compile(r"^(위키백과|특수|파일|틀|분류|포털|Wikipedia|Special|File):|대문|Main_Page")
    out = []
    for a in arts:
        t = a["article"]
        if skip.search(t):
            continue
        out.append({"src": f"wikipedia_{lang}", "keyword": t.replace("_", " "), "views": a["views"]})
        if len(out) >= n:
            break
    return out


def netflix_kr() -> list[dict]:
    tsv = _get("https://www.netflix.com/tudum/top10/data/all-weeks-countries.tsv").text
    rows = list(csv.DictReader(io.StringIO(tsv), delimiter="\t"))
    kr = [r for r in rows if r["country_iso2"] == "KR"]
    last = max(r["week"] for r in kr)
    return [{"src": "netflix_kr", "week": last, "category": r["category"], "rank": int(r["weekly_rank"]),
             "title": r["show_title"], "season": r["season_title"], "weeks": int(r["cumulative_weeks_in_top_10"])}
            for r in kr if r["week"] == last]


def collect() -> dict:
    res = {"date": datetime.now(KST).strftime("%Y-%m-%d"), "items": [], "netflix_kr": [], "errors": []}
    for name, fn in [("trends_KR", lambda: google_trends("KR")), ("trends_US", lambda: google_trends("US")),
                     ("trends_JP", lambda: google_trends("JP")), ("wiki_ko", wikipedia_top)]:
        try:
            res["items"] += fn()
        except Exception as e:  # 소스 하나가 죽어도 나머지로 진행
            res["errors"].append(f"{name}: {e}")
    try:
        res["netflix_kr"] = netflix_kr()
    except Exception as e:
        res["errors"].append(f"netflix: {e}")
    for it in res["items"]:
        text = it["keyword"] + " " + " ".join(n["title"] for n in it.get("news", []))
        it["blocked"] = bool(BLOCK.search(text))
    return res


if __name__ == "__main__":
    data = collect()
    json.dump(data, open("candidates.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    ok = [i for i in data["items"] if not i["blocked"]]
    print(f"후보 {len(data['items'])}개 (차단 후 {len(ok)}개), 넷플릭스 {len(data['netflix_kr'])}개, 오류 {data['errors']}")
