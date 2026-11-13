#!/usr/bin/env python3
import os
import sys
import json
import gzip
import time
import hashlib
import subprocess
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime

GITHUB_USER = "parshant65-lang"
VAULT_NAME = "live-financial-wire-vault"

FEEDS = [
    {"source": "Google News World Business", "url": "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=en-US&gl=US&ceid=US:en"},
    {"source": "Google News India Business", "url": "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=en-IN&gl=IN&ceid=IN:en"},
    {"source": "Economic Times Markets", "url": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"},
    {"source": "Economic Times Economy", "url": "https://economictimes.indiatimes.com/news/economy/rssfeeds/1373380680.cms"},
    {"source": "Business Standard Markets", "url": "https://www.business-standard.com/rss/markets-106.rss"},
    {"source": "Business Standard Companies", "url": "https://www.business-standard.com/rss/companies-101.rss"},
    {"source": "Livemint Markets", "url": "https://www.livemint.com/rss/markets"},
    {"source": "The Hindu BusinessLine", "url": "https://www.thehindubusinessline.com/markets/feeder/default.rss"},
    {"source": "The Guardian Business", "url": "https://www.theguardian.com/uk/business/rss"},
    {"source": "Fortune Global", "url": "https://fortune.com/feed"}
]

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

def safe_git(cmd, cwd):
    for attempt in range(3):
        try:
            return subprocess.check_output(cmd, cwd=cwd, stderr=subprocess.STDOUT).decode().strip()
        except subprocess.CalledProcessError as e:
            err = e.output.decode() if e.output else str(e)
            print(f"[GIT-WARN] Attempt {attempt+1} failed: {err}")
            time.sleep(2)
    raise RuntimeError(f"Git failed: {' '.join(cmd)}")

def hash_str(s):
    return hashlib.md5(s.encode("utf-8", errors="ignore")).hexdigest()

def fetch_feed(feed_info):
    name = feed_info["source"]
    url = feed_info["url"]
    items_out = []
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=12) as resp:
            xml_data = resp.read()
            root = ET.fromstring(xml_data)
            
            for item in root.findall(".//item"):
                title = item.find("title")
                link = item.find("link")
                pubDate = item.find("pubDate")
                desc = item.find("description")
                
                t_text = title.text.strip() if title is not None and title.text else ""
                l_text = link.text.strip() if link is not None and link.text else ""
                d_text = desc.text.strip() if desc is not None and desc.text else ""
                p_text = pubDate.text.strip() if pubDate is not None and pubDate.text else ""
                
                if t_text and (l_text or d_text):
                    art_id = hash_str(f"{t_text}_{l_text}")
                    items_out.append({
                        "id": art_id,
                        "source": name,
                        "title": t_text,
                        "url": l_text,
                        "summary": d_text,
                        "published_at": p_text,
                        "ingested_at": datetime.utcnow().isoformat() + "Z"
                    })
    except Exception as e:
        print(f"  [WARN] Failed to fetch {name}: {e}")
    return items_out

def main():
    pat = os.environ.get("VAULT_PAT")
    if not pat:
        print("[ERROR] VAULT_PAT not set!")
        sys.exit(1)

    print("[INIT] Cloning live-financial-wire-vault...")
    remote = f"https://x-access-token:{pat}@github.com/{GITHUB_USER}/{VAULT_NAME}.git"
    temp_dir = "temp_live_wire"
    if os.path.exists(temp_dir):
        subprocess.run(["rm", "-rf", temp_dir])
        
    safe_git(["git", "clone", "--depth", "1", remote, temp_dir], cwd=".")
    
    ckpt_path = os.path.join(temp_dir, "checkpoint.json")
    with open(ckpt_path, "r", encoding="utf-8") as f:
        ckpt = json.load(f)
        
    seen_path = os.path.join(temp_dir, "seen_hashes.json")
    seen_hashes = set()
    if os.path.exists(seen_path):
        try:
            with open(seen_path, "r", encoding="utf-8") as f:
                seen_hashes = set(json.load(f))
        except Exception:
            pass
            
    print(f"[ACTIVE] Vault: {VAULT_NAME} | Total Streamed: {ckpt.get('articles_ingested', 0):,} | Seen Cache: {len(seen_hashes):,}")
    
    new_articles = []
    print(f"\n[STREAM] Polling {len(FEEDS)} real-time global financial feeds...")
    for feed in FEEDS:
        t0 = time.time()
        feed_items = fetch_feed(feed)
        dt = time.time() - t0
        
        fresh_in_feed = 0
        for item in feed_items:
            h = item["id"]
            if h not in seen_hashes:
                seen_hashes.add(h)
                new_articles.append(item)
                fresh_in_feed += 1
                
        print(f"  ✓ {feed['source']:28} : {len(feed_items):2d} items ({fresh_in_feed} fresh) in {dt:.2f}s")

    print(f"\n[SUMMARY] Ingested {len(new_articles):,} fresh breaking articles in this cycle!")

    if new_articles:
        now = datetime.utcnow()
        day_dir = os.path.join(temp_dir, "data", now.strftime("%Y-%m-%d"))
        os.makedirs(day_dir, exist_ok=True)
        
        chunk_file = f"wire_{now.strftime('%H-%M-%S')}.json.gz"
        chunk_path = os.path.join(day_dir, chunk_file)
        
        comp = gzip.compress(json.dumps(new_articles, ensure_ascii=False, indent=2).encode("utf-8"))
        with open(chunk_path, "wb") as f:
            f.write(comp)
            
        total_ingested = ckpt.get("articles_ingested", 0) + len(new_articles)
        ckpt["articles_ingested"] = total_ingested
        ckpt["last_stream_time"] = now.isoformat() + "Z"
        
        with open(ckpt_path, "w", encoding="utf-8") as f:
            json.dump(ckpt, f, indent=2)
            
        # Keep seen_hashes capped to last 50,000 to keep repo light
        trimmed_hashes = list(seen_hashes)[-50000:]
        with open(seen_path, "w", encoding="utf-8") as f:
            json.dump(trimmed_hashes, f)
            
        safe_git(["git", "config", "user.name", "LiveWireBot"], cwd=temp_dir)
        safe_git(["git", "config", "user.email", "livewire@intelligence.internal"], cwd=temp_dir)
        safe_git(["git", "add", "-A"], cwd=temp_dir)
        
        commit_msg = f"[LIVE-WIRE] Stream +{len(new_articles):,} breaking news items (Total: {total_ingested:,}) [skip ci]"
        safe_git(["git", "commit", "-m", commit_msg], cwd=temp_dir)
        
        print(f"[PUSH] Pushing to {VAULT_NAME}...")
        safe_git(["git", "push", "origin", "main"], cwd=temp_dir)
        print(f"[SUCCESS] {commit_msg}")
    else:
        print("[INFO] No new breaking stories in this minute cycle.")

    subprocess.run(["rm", "-rf", temp_dir])

if __name__ == "__main__":
    main()
