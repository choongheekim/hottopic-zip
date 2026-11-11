"""GitHub에 파일 여러 개를 커밋 1번으로 올리기(git 설치 없이 API로).

config.txt 의 GITHUB_TOKEN(이 저장소만 Contents 읽기·쓰기 권한), GITHUB_REPO=choongheekim/hottopic-zip
"""
import base64
import os
import time

import requests

API = "https://api.github.com"


def _h():
    return {"Authorization": f"Bearer {os.environ['GITHUB_TOKEN'].strip()}",
            "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}


def _req(method, path, **kw):
    r = requests.request(method, f"{API}/repos/{os.environ['GITHUB_REPO']}{path}", headers=_h(), timeout=120, **kw)
    if r.status_code >= 300:
        raise RuntimeError(f"GitHub {method} {path} 실패 {r.status_code}: {r.text[:300]}")
    return r.json()


def commit_files(files: dict[str, bytes], message: str, branch="main", tries=4):
    blobs = []
    for path, data in files.items():
        b = _req("POST", "/git/blobs", json={"content": base64.b64encode(data).decode(), "encoding": "base64"})
        blobs.append({"path": path, "mode": "100644", "type": "blob", "sha": b["sha"]})
    for i in range(tries):           # 그사이 GitHub 쪽 커밋(게시 기록)이 생기면 다시 시도
        head = _req("GET", f"/git/ref/heads/{branch}")["object"]["sha"]
        base_tree = _req("GET", f"/git/commits/{head}")["tree"]["sha"]
        tree = _req("POST", "/git/trees", json={"base_tree": base_tree, "tree": blobs})["sha"]
        commit = _req("POST", "/git/commits", json={"message": message, "tree": tree, "parents": [head]})["sha"]
        try:
            _req("PATCH", f"/git/refs/heads/{branch}", json={"sha": commit})
            return commit
        except RuntimeError as e:
            if i == tries - 1:
                raise
            print("[ghup] 다시 시도:", e)
            time.sleep(5)


def check():
    """설정 점검용: 저장소 접근 가능한지."""
    info = _req("GET", "")
    return info["full_name"], info["permissions"]
