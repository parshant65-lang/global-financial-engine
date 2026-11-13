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
    {"name": "cnbc-vault-1", "start_vol": 1, "end_vol": 7},
    {"name": "cnbc-vault-2", "start_vol": 8, "end_vol": 13}
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

def fetch_sitemap_urls(vol):
    url = f"https://www.cnbc.com/CNBCsitemapAll{vol}.xml"
    req = urllib.request.Request(url, headers=HEADERS)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                content = resp.read().decode("utf-8", errors="ignore")
                all_locs = re.findall(r"<loc>(.*?)</loc>", content)
                # Filter only date-based news articles
                return [l for l in all_locs if re.search(r"/\d{4}/\d{2}/\d{2}/", l)]
        except Exception as e:
            time.sleep(3)
    return []

def extract_article(url):
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=12) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
                
            soup = BeautifulSoup(html, "html.parser")
            title_tag = soup.find("h1") or soup.find("title")
            title = title_tag.get_text().strip() if title_tag else ""
            
            # Paragraph extraction
            all_p = [p.get_text().strip() for p in soup.find_all("p") if len(p.get_text().strip()) > 30]
            # Exclude menu boilerplate
            filtered_p = [p for p in all_p if not any(x in p.lower() for x in ["livestreammenu", "sign up for", "privacy policy", "terms of service", "skip navigation"])]
            text = "\n".join(filtered_p)
            
            if text and len(text) > 100:
                date_match = re.search(r"/(\d{4}/\d{2}/\d{2})/", url)
                return {
                    "title": title,
                    "date": date_match.group(1) if date_match else "",
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
            
        cur_vol = ckpt.get("current_vol", v_info["start_vol"])
        if cur_vol <= v_info["end_vol"]:
            return v_info, temp_dir, ckpt
            
        subprocess.run(["rm", "-rf", temp_dir])
        
    return None, None, None

def main():
    pat = os.environ.get("VAULT_PAT")
    if not pat:
        print("[ERROR] VAULT_PAT not set!")
        sys.exit(1)
        
    print("[INIT] Detecting active CNBC vault...")
    v_info, vault_dir, ckpt = find_active_vault(pat)
    
    if not v_info:
        print("[COMPLETE] All CNBC vaults (Volumes 1-13) are fully harvested!")
        return

    v_name = v_info["name"]
    safe_git(["git", "config", "user.name", "CNBCBot"], cwd=vault_dir)
    safe_git(["git", "config", "user.email", "bot@intelligence.internal"], cwd=vault_dir)

    cur_vol = ckpt.get("current_vol", v_info["start_vol"])
    cur_offset = ckpt.get("current_offset", 0)
    total_articles = ckpt.get("articles_collected", 0)
    
    print(f"[ACTIVE] Vault: {v_name} | Volume: {cur_vol} | Offset: {cur_offset} | Total Collected: {total_articles:,}")

    collected_in_run = 0
    
    while collected_in_run < ARTICLES_PER_RUN and cur_vol <= v_info["end_vol"]:
        print(f"\n[FETCH] Sitemaps for Volume {cur_vol}...")
        urls = fetch_sitemap_urls(cur_vol)
        
        if not urls:
            print(f"  • Vol {cur_vol}: 0 URLs. Advancing.")
            cur_vol += 1
            cur_offset = 0
            ckpt["current_vol"] = cur_vol
            ckpt["current_offset"] = 0
            continue
            
        remaining = urls[cur_offset:]
        if not remaining:
            print(f"[DONE] Finished Volume {cur_vol} ({len(urls)} articles).")
            cur_vol += 1
            cur_offset = 0
            ckpt["current_vol"] = cur_vol
            ckpt["current_offset"] = 0
            continue
            
        needed = ARTICLES_PER_RUN - collected_in_run
        batch_urls = remaining[:needed]
        
        print(f"[EXTRACT] Processing {len(batch_urls)} CNBC articles ({WORKER_THREADS} threads)...")
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
            vol_dir = os.path.join(vault_dir, "data", f"volume_{cur_vol:02d}")
            os.makedirs(vol_dir, exist_ok=True)
            
            for i in range(0, len(extracted_batch), ARTICLES_PER_FILE):
                sub_chunk = extracted_batch[i:i+ARTICLES_PER_FILE]
                file_name = f"chunk_{cur_offset - len(batch_urls) + i:06d}.json.gz"
                file_path = os.path.join(vol_dir, file_name)
                comp = gzip.compress(json.dumps(sub_chunk, ensure_ascii=False).encode("utf-8"))
                with open(file_path, "wb") as f:
                    f.write(comp)
                    
        if cur_offset >= len(urls):
            cur_vol += 1
            cur_offset = 0
            
        ckpt["current_vol"] = cur_vol
        ckpt["current_offset"] = cur_offset
        ckpt["articles_collected"] = total_articles
        ckpt["updated_at"] = datetime.utcnow().isoformat() + "Z"

    ckpt_path = os.path.join(vault_dir, "checkpoint.json")
    with open(ckpt_path, "w", encoding="utf-8") as f:
        json.dump(ckpt, f, indent=2)

    if collected_in_run > 0:
        safe_git(["git", "add", "-A"], cwd=vault_dir)
        commit_msg = f"[CNBC-CLOUD] Ingest Vol {cur_vol} (+{collected_in_run:,} articles, Total Vault: {total_articles:,}) [skip ci]"
        safe_git(["git", "commit", "-m", commit_msg], cwd=vault_dir)
        print(f"[PUSH] Pushing to {v_name}...")
        safe_git(["git", "push", "origin", "main"], cwd=vault_dir)
        print(f"[SUCCESS] Pushed batch: {commit_msg}")
    else:
        print("[INFO] No articles collected in this cycle.")

    subprocess.run(["rm", "-rf", vault_dir])

if __name__ == "__main__":
    main()
