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
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup

GITHUB_USER = "parshant65-lang"
ARTICLES_PER_RUN = 1000
ARTICLES_PER_FILE = 250
WORKER_THREADS = 10

VAULT_MAP = [
    {"name": "moneycontrol-vault-1", "start": 2011, "end": 2018},
    {"name": "moneycontrol-vault-2", "start": 2019, "end": 2026}
]

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

def safe_git(cmd, cwd):
    for attempt in range(3):
        try:
            return subprocess.check_output(cmd, cwd=cwd, stderr=subprocess.STDOUT).decode().strip()
        except subprocess.CalledProcessError as e:
            err = e.output.decode() if e.output else str(e)
            print(f"[GIT-WARN] Attempt {attempt+1} failed: {err}")
            time.sleep(3)
    raise RuntimeError(f"Git failed: {' '.join(cmd)}")

def fetch_sitemap_urls(year, month):
    url = f"https://www.moneycontrol.com/news/sitemap/sitemap-post-{year}-{month:02d}.xml"
    req = urllib.request.Request(url, headers=HEADERS)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                content = resp.read().decode("utf-8", errors="ignore")
                return re.findall(r"<loc>(.*?)</loc>", content)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return []
            time.sleep(2)
        except Exception:
            time.sleep(2)
    return []

def extract_article(url):
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=12) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
                
            scripts = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL)
            for s in scripts:
                try:
                    d = json.loads(s, strict=False)
                    items = d if isinstance(d, list) else [d]
                    for item in items:
                        if isinstance(item, dict) and item.get("@type") in ["NewsArticle", "Article"]:
                            body = item.get("articleBody", "")
                            if body and len(body.strip()) > 50:
                                art_id = re.search(r"-(\d+)\.html", url)
                                return {
                                    "id": art_id.group(1) if art_id else "",
                                    "title": item.get("headline", "").strip(),
                                    "date": item.get("datePublished", ""),
                                    "description": item.get("description", "").strip(),
                                    "body": body.strip(),
                                    "url": url
                                }
                except Exception:
                    pass
            # HTML Fallback
            soup = BeautifulSoup(html, "html.parser")
            body_div = soup.find("div", class_=re.compile(r"content_wrapper|article_desc"))
            if body_div:
                text = "\n".join([p.get_text().strip() for p in body_div.find_all("p") if p.get_text().strip()])
                title_tag = soup.find("h1")
                if text and len(text) > 100:
                    art_id = re.search(r"-(\d+)\.html", url)
                    return {
                        "id": art_id.group(1) if art_id else "",
                        "title": title_tag.get_text().strip() if title_tag else "",
                        "date": "",
                        "description": "",
                        "body": text,
                        "url": url
                    }
        except Exception:
            time.sleep(1)
    return None

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
            
        cur_year = ckpt.get("current_year", v_info["start"])
        if cur_year <= v_info["end"]:
            return v_info, temp_dir, ckpt
            
        subprocess.run(["rm", "-rf", temp_dir])
        
    return None, None, None

def main():
    pat = os.environ.get("VAULT_PAT")
    if not pat:
        print("[ERROR] VAULT_PAT not set!")
        sys.exit(1)
        
    print("[INIT] Detecting active Moneycontrol vault...")
    v_info, vault_dir, ckpt = find_active_vault(pat)
    
    if not v_info:
        print("[COMPLETE] All Moneycontrol vaults (2011-2026) are fully harvested!")
        return

    v_name = v_info["name"]
    safe_git(["git", "config", "user.name", "MCBot"], cwd=vault_dir)
    safe_git(["git", "config", "user.email", "bot@intelligence.internal"], cwd=vault_dir)

    cur_year = ckpt.get("current_year", v_info["start"])
    cur_month = ckpt.get("current_month", 1)
    cur_offset = ckpt.get("current_offset", 0)
    total_articles = ckpt.get("articles_collected", 0)
    
    print(f"[ACTIVE] Vault: {v_name} | Year: {cur_year} | Month: {cur_month:02d} | Offset: {cur_offset} | Total: {total_articles:,}")

    collected_in_run = 0
    
    while collected_in_run < ARTICLES_PER_RUN and cur_year <= v_info["end"]:
        print(f"\n[FETCH] Sitemaps for {cur_year}-{cur_month:02d}...")
        urls = fetch_sitemap_urls(cur_year, cur_month)
        
        if not urls:
            print(f"  • {cur_year}-{cur_month:02d}: 0 URLs found. Advancing month.")
            cur_month += 1
            cur_offset = 0
            if cur_month > 12:
                cur_year += 1
                cur_month = 1
            ckpt["current_year"] = cur_year
            ckpt["current_month"] = cur_month
            ckpt["current_offset"] = 0
            continue
            
        remaining = urls[cur_offset:]
        if not remaining:
            print(f"[DONE] Finished {cur_year}-{cur_month:02d} ({len(urls)} articles).")
            cur_month += 1
            cur_offset = 0
            if cur_month > 12:
                cur_year += 1
                cur_month = 1
            ckpt["current_year"] = cur_year
            ckpt["current_month"] = cur_month
            ckpt["current_offset"] = 0
            continue
            
        needed = ARTICLES_PER_RUN - collected_in_run
        batch_urls = remaining[:needed]
        
        print(f"[EXTRACT] Processing {len(batch_urls)} articles ({WORKER_THREADS} threads)...")
        t0 = time.time()
        
        extracted_batch = []
        with ThreadPoolExecutor(max_workers=WORKER_THREADS) as executor:
            future_to_url = {executor.submit(extract_article, u): u for u in batch_urls}
            for future in as_completed(future_to_url):
                res = future.result()
                if res and res.get("body"):
                    extracted_batch.append(res)
                    
        dt = time.time() - t0
        valid_cnt = len(extracted_batch)
        collected_in_run += valid_cnt
        total_articles += valid_cnt
        cur_offset += len(batch_urls)
        
        print(f"  ✓ {valid_cnt}/{len(batch_urls)} extracted in {dt:.2f}s | Vault Total: {total_articles:,}")
        
        if extracted_batch:
            year_dir = os.path.join(vault_dir, "data", str(cur_year))
            os.makedirs(year_dir, exist_ok=True)
            
            for i in range(0, len(extracted_batch), ARTICLES_PER_FILE):
                sub_chunk = extracted_batch[i:i+ARTICLES_PER_FILE]
                file_name = f"month_{cur_month:02d}_part_{cur_offset - len(batch_urls) + i:06d}.json.gz"
                file_path = os.path.join(year_dir, file_name)
                comp = gzip.compress(json.dumps(sub_chunk, ensure_ascii=False).encode("utf-8"))
                with open(file_path, "wb") as f:
                    f.write(comp)
                    
        if cur_offset >= len(urls):
            cur_month += 1
            cur_offset = 0
            if cur_month > 12:
                cur_year += 1
                cur_month = 1
                
        ckpt["current_year"] = cur_year
        ckpt["current_month"] = cur_month
        ckpt["current_offset"] = cur_offset
        ckpt["articles_collected"] = total_articles
        ckpt["updated_at"] = datetime.utcnow().isoformat() + "Z"

    ckpt_path = os.path.join(vault_dir, "checkpoint.json")
    with open(ckpt_path, "w", encoding="utf-8") as f:
        json.dump(ckpt, f, indent=2)

    if collected_in_run > 0:
        safe_git(["git", "add", "-A"], cwd=vault_dir)
        commit_msg = f"[MC-CLOUD] Ingest {cur_year}-{cur_month:02d} (+{collected_in_run:,} articles, Total Vault: {total_articles:,}) [skip ci]"
        safe_git(["git", "commit", "-m", commit_msg], cwd=vault_dir)
        print(f"[PUSH] Pushing to {v_name}...")
        safe_git(["git", "push", "origin", "main"], cwd=vault_dir)
        print(f"[SUCCESS] Pushed batch: {commit_msg}")
    else:
        print("[INFO] No articles collected in this cycle.")

    subprocess.run(["rm", "-rf", vault_dir])

if __name__ == "__main__":
    main()
