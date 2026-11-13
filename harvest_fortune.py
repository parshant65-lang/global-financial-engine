#!/usr/bin/env python3
import os
import sys
import json
import gzip
import time
import subprocess
import urllib.request
import urllib.error
import re
from datetime import datetime
from bs4 import BeautifulSoup

GITHUB_USER = "parshant65-lang"
PAGES_PER_RUN = 10         # 10 pages * 100 posts = 1,000 articles per run
POSTS_PER_PAGE = 100
ARTICLES_PER_FILE = 250

VAULT_MAP = [
    {"name": "fortune-vault-1", "start_page": 1, "end_page": 1200},
    {"name": "fortune-vault-2", "start_page": 1201, "end_page": 2500}
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json"
}

def safe_git(cmd, cwd):
    for attempt in range(3):
        try:
            return subprocess.check_output(cmd, cwd=cwd, stderr=subprocess.STDOUT).decode().strip()
        except subprocess.CalledProcessError as e:
            err = e.output.decode() if e.output else str(e)
            print(f"[GIT-WARN] Attempt {attempt+1} failed: {err}")
            time.sleep(3)
    raise RuntimeError(f"Git failed: {' '.join(cmd)}")

def fetch_fortune_page(page):
    url = f"https://fortune.com/wp-json/wp/v2/posts?per_page={POSTS_PER_PAGE}&page={page}"
    req = urllib.request.Request(url, headers=HEADERS)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="ignore"))
                return data
        except urllib.error.HTTPError as e:
            if e.code == 400: # Exceeded total pages
                return []
            print(f"  [WARN] Page {page} HTTP {e.code}, retry {attempt+1}...")
            time.sleep(3)
        except Exception as e:
            print(f"  [WARN] Page {page} Error {e}, retry {attempt+1}...")
            time.sleep(3)
    return []

def clean_html(raw_html):
    if not raw_html:
        return ""
    soup = BeautifulSoup(raw_html, "html.parser")
    paras = [p.get_text().strip() for p in soup.find_all("p") if p.get_text().strip()]
    return "\n\n".join(paras)

def find_active_vault(pat):
    for v_info in VAULT_MAP:
        v_name = v_info["name"]
        remote = f"https://x-access-token:{pat}@github.com/{GITHUB_USER}/{v_name}.git"
        temp_dir = f"temp_{v_name}"
        if os.path.exists(temp_dir):
            subprocess.run(["rm", "-rf", temp_dir])
            
        safe_git(["git", "clone", "--depth", "1", remote, temp_dir], cwd=".")
        ckpt_path = os.path.join(temp_dir, "checkpoint.json")
        with open(ckpt_path, "r", encoding="utf-8") as f:
            ckpt = json.load(f)
            
        cur_page = ckpt.get("current_page", v_info["start_page"])
        if cur_page <= v_info["end_page"]:
            return v_info, temp_dir, ckpt
            
        subprocess.run(["rm", "-rf", temp_dir])
        
    return None, None, None

def main():
    pat = os.environ.get("VAULT_PAT")
    if not pat:
        print("[ERROR] VAULT_PAT not set!")
        sys.exit(1)
        
    print("[INIT] Detecting active Fortune vault...")
    v_info, vault_dir, ckpt = find_active_vault(pat)
    
    if not v_info:
        print("[COMPLETE] All Fortune vaults (Pages 1-2500) are fully harvested!")
        return

    v_name = v_info["name"]
    safe_git(["git", "config", "user.name", "FortuneBot"], cwd=vault_dir)
    safe_git(["git", "config", "user.email", "bot@intelligence.internal"], cwd=vault_dir)

    cur_page = ckpt.get("current_page", v_info["start_page"])
    total_articles = ckpt.get("articles_collected", 0)
    
    print(f"[ACTIVE] Vault: {v_name} | Start Page: {cur_page} | End Page: {v_info['end_page']} | Total Collected: {total_articles:,}")

    pages_done = 0
    collected_in_run = []

    while pages_done < PAGES_PER_RUN and cur_page <= v_info["end_page"]:
        print(f"[FETCH] Fortune API Page {cur_page}...")
        t0 = time.time()
        posts = fetch_fortune_page(cur_page)
        dt = time.time() - t0
        
        if not posts:
            print(f"  • Page {cur_page} returned empty. Advancing or complete.")
            cur_page += 1
            pages_done += 1
            ckpt["current_page"] = cur_page
            continue
            
        for p in posts:
            rendered_content = p.get("content", {}).get("rendered", "")
            body_text = clean_html(rendered_content)
            
            if len(body_text) > 100:
                soup_title = BeautifulSoup(p.get("title", {}).get("rendered", ""), "html.parser")
                clean_title = soup_title.get_text().strip()
                
                art = {
                    "id": str(p.get("id", "")),
                    "title": clean_title,
                    "date": p.get("date", ""),
                    "modified": p.get("modified", ""),
                    "url": p.get("link", ""),
                    "body": body_text
                }
                collected_in_run.append(art)
                
        print(f"  ✓ Fetched {len(posts)} posts ({dt:.2f}s) | Valid added: {len(posts)} | Run total: {len(collected_in_run)}")
        cur_page += 1
        pages_done += 1
        time.sleep(1.0)

    # Save to vault
    if collected_in_run:
        data_dir = os.path.join(vault_dir, "data")
        os.makedirs(data_dir, exist_ok=True)
        
        for i in range(0, len(collected_in_run), ARTICLES_PER_FILE):
            sub_chunk = collected_in_run[i:i+ARTICLES_PER_FILE]
            file_name = f"fortune_page_{cur_page - pages_done + (i // POSTS_PER_PAGE):05d}_chunk_{i:04d}.json.gz"
            file_path = os.path.join(data_dir, file_name)
            comp = gzip.compress(json.dumps(sub_chunk, ensure_ascii=False).encode("utf-8"))
            with open(file_path, "wb") as f:
                f.write(comp)
                
        total_articles += len(collected_in_run)
        print(f"[DISK] Saved {len(collected_in_run):,} articles to {data_dir} (Gzip compressed)")

    ckpt["current_page"] = cur_page
    ckpt["articles_collected"] = total_articles
    ckpt["updated_at"] = datetime.utcnow().isoformat() + "Z"

    ckpt_path = os.path.join(vault_dir, "checkpoint.json")
    with open(ckpt_path, "w", encoding="utf-8") as f:
        json.dump(ckpt, f, indent=2)

    if collected_in_run:
        safe_git(["git", "add", "-A"], cwd=vault_dir)
        commit_msg = f"[FORTUNE-CLOUD] Ingest Pages {cur_page - pages_done}..{cur_page - 1} (+{len(collected_in_run):,} articles, Total: {total_articles:,}) [skip ci]"
        safe_git(["git", "commit", "-m", commit_msg], cwd=vault_dir)
        print(f"[PUSH] Pushing to {v_name}...")
        safe_git(["git", "push", "origin", "main"], cwd=vault_dir)
        print(f"[SUCCESS] Pushed batch: {commit_msg}")
    else:
        print("[INFO] No articles collected in this cycle.")

    subprocess.run(["rm", "-rf", vault_dir])

if __name__ == "__main__":
    main()
