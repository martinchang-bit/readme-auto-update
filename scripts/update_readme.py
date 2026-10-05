import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

REPO = os.environ["GITHUB_REPOSITORY"]
TOKEN = os.environ["REPO_TOKEN"]
START = "<!-- RECENT_ACTIVITY:START -->"
END = "<!-- RECENT_ACTIVITY:END -->"
LIMIT = 10
BOT_PREFIX = "chore(readme)"  # 過濾 bot 自己的 commit，確保冪等


def api(path, retries=4):
    """呼叫 GitHub API；遇到 rate limit / 5xx 時退避重試。不印出回應內容。"""
    url = f"https://api.github.com{path}"
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "readme-updater",
    }
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code in (403, 429, 500, 502, 503) and attempt < retries - 1:
                reset = e.headers.get("X-RateLimit-Reset")
                if e.headers.get("X-RateLimit-Remaining") == "0" and reset:
                    wait = min(max(int(reset) - int(time.time()), 1), 60)
                else:
                    wait = 2 ** (attempt + 1)
                print(f"HTTP {e.code}, retry in {wait}s")  # 不印 body
                time.sleep(wait)
                continue
            print(f"API request failed: HTTP {e.code}")
            sys.exit(1)


def build_section():
    commits = api(f"/repos/{REPO}/commits?per_page=30")
    lines = []
    for c in commits:
        msg = c["commit"]["message"].splitlines()[0].strip()
        if msg.startswith(BOT_PREFIX):
            continue
        sha = c["sha"][:7]
        date = c["commit"]["author"]["date"][:10]
        author = (c.get("author") or {}).get("login") or c["commit"]["author"]["name"]
        lines.append(f"- [`{sha}`]({c['html_url']}) {msg} — @{author} ({date})")
        if len(lines) >= LIMIT:
            break
    return "\n".join(lines) if lines else "_No activity yet._"


def main():
    with open("README.md", encoding="utf-8") as f:
        text = f.read()
    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END), re.DOTALL)
    if not pattern.search(text):
        print("ERROR: README markers not found")
        sys.exit(1)
    new_block = f"{START}\n{build_section()}\n{END}"
    new_text = pattern.sub(lambda _: new_block, text)
    if new_text != text:
        with open("README.md", "w", encoding="utf-8") as f:
            f.write(new_text)
        print("README updated")
    else:
        print("README already up to date")


if __name__ == "__main__":
    main()