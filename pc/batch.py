"""오늘 게시물 여러 개를 한 번에 만들기 → GitHub 대기열에 차례로 올림.

GitHub는 대기열에서 1시간에 1개씩 게시한다(매시 47분 자동 실행) → 새 계정이 한꺼번에 올려 스팸으로 보이는 걸 피함.
사용법: python pc/batch.py 5
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATS = ["영화·드라마·OTT", "음악·K팝·공연", "스포츠", "해외 유행·밈", "광고·마케팅·브랜드·테크", "국내 유행·생활"]

n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
ok = 0
for i in range(n):
    cat = CATS[i % len(CATS)]
    print(f"\n===== {i + 1}/{n} 번째 게시물 ({cat}) =====", flush=True)
    r = subprocess.run([sys.executable, os.path.join(ROOT, "pc", "run.py"), "--slot", "now", "--category", cat], cwd=ROOT)
    ok += r.returncode == 0
print(f"\n완료: {ok}/{n}개를 대기열에 올렸어요. GitHub가 1시간에 1개씩 게시해요.")
