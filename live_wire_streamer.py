#!/usr/bin/env python3
import os
import sys
import json
import gzip
import time
import hashlib
import subprocess
import urllib.request
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

GITHUB_USER = "parshant65-lang"
VAULT_NAME = "live-financial-wire-vault"

# 20 Verified Live Feeds (World-Class Financial Wire)
FEEDS = [
    {"source": "Google News World Business", "url": "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=en-US&gl=US&ceid=US:en"},
    {"source": "Google News India Business", "url": "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=en-IN&gl=IN&ceid=IN:en"},
    {"source": "Bloomberg Live Wire", "url": "https://news.google.com/rss/search?q=when:1h+source:bloomberg&hl=en-US&gl=US&ceid=US:en"},
    {"source": "Reuters Live Wire", "url": "https://news.google.com/rss/search?q=when:1h+source:reuters&hl=en-US&gl=US&ceid=US:en"},
    {"source": "WSJ Real-Time Wire", "url": "https://news.google.com/rss/search?q=when:1h+source:wall-street-journal&hl=en-US&gl=US&ceid=US:en"},
    {"source": "MarketWatch Real-Time", "url": "https://feeds.content.dowjones.io/public/rss/mw_realtimeheadlines"},
    {"source": "Techmeme Tech Breaking", "url": "https://www.techmeme.com/feed.xml"},
    {"source": "OilPrice Global Energy", "url": "https://oilprice.com/rss/main"},
    {"source": "PR Newswire Financial", "url": "https://www.prnewswire.com/rss/financial-services-latest-news/financial-services-latest-news-list.rss"},
    {"source": "Economic Times Markets", "url": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"},
    {"source": "Economic Times Economy", "url": "https://economictimes.indiatimes.com/news/economy/rssfeeds/1373380680.cms"},
    {"source": "Economic Times Wealth", "url": "https://economictimes.indiatimes.com/wealth/rssfeeds/837555174.cms"},
    {"source": "Business Standard Markets", "url": "https://www.business-standard.com/rss/markets-106.rss"},
    {"source": "Business Standard Companies", "url": "https://www.business-standard.com/rss/companies-101.rss"},
    {"source": "Livemint Markets", "url": "https://www.livemint.com/rss/markets"},
    {"source": "Livemint Companies", "url": "https://www.livemint.com/rss/companies"},
    {"source": "The Hindu BusinessLine", "url": "https://www.thehindubusinessline.com/markets/feeder/default.rss"},
    {"source": "The Guardian Business", "url": "https://www.theguardian.com/uk/business/rss"},
    {"source": "Fortune Global", "url": "https://fortune.com/feed"},
    {"source": "CoinDesk Crypto", "url": "https://www.coindesk.com/arc/outboundfeeds/rss/"}
]

# High-Precision Disambiguated Ticker Database (Zero False Positive Target)
TICKER_DB = [
    # Top Indian Equities (NSE)
    {"ticker": "RELIANCE.NS", "name": "Reliance Industries", "exchange": "NSE", "sector": "Energy/Retail", "patterns": [r"\bReliance\s+Industries\b", r"\bRIL\b", r"\bReliance\s+Retail\b", r"\bReliance\s+Jio\b", r"\bJio\s+Platforms\b"]},
    {"ticker": "TCS.NS", "name": "Tata Consultancy Services", "exchange": "NSE", "sector": "IT", "patterns": [r"\bTata\s+Consultancy\s+Services\b", r"\bTCS\b"]},
    {"ticker": "HDFCBANK.NS", "name": "HDFC Bank", "exchange": "NSE", "sector": "Banking", "patterns": [r"\bHDFC\s+Bank\b", r"\bHDFCBANK\b"]},
    {"ticker": "ICICIBANK.NS", "name": "ICICI Bank", "exchange": "NSE", "sector": "Banking", "patterns": [r"\bICICI\s+Bank\b", r"\bICICIBANK\b"]},
    {"ticker": "INFY.NS", "name": "Infosys", "exchange": "NSE", "sector": "IT", "patterns": [r"\bInfosys\b", r"\bInfy\b"]},
    {"ticker": "SBIN.NS", "name": "State Bank of India", "exchange": "NSE", "sector": "Banking", "patterns": [r"\bState\s+Bank\s+of\s+India\b", r"\bSBI\b"]},
    {"ticker": "TATAMOTORS.NS", "name": "Tata Motors", "exchange": "NSE", "sector": "Automobile", "patterns": [r"\bTata\s+Motors\b", r"\bTaMo\b", r"\bJaguar\s+Land\s+Rover\b", r"\bJLR\b"]},
    {"ticker": "TATASTEEL.NS", "name": "Tata Steel", "exchange": "NSE", "sector": "Metals", "patterns": [r"\bTata\s+Steel\b"]},
    {"ticker": "BHARTIARTL.NS", "name": "Bharti Airtel", "exchange": "NSE", "sector": "Telecom", "patterns": [r"\bBharti\s+Airtel\b", r"\bAirtel\b"]},
    {"ticker": "LT.NS", "name": "Larsen & Toubro", "exchange": "NSE", "sector": "Infrastructure", "patterns": [r"\bLarsen\s+&\s+Toubro\b", r"\bL&T\b"]},
    {"ticker": "ITC.NS", "name": "ITC Limited", "exchange": "NSE", "sector": "FMCG", "patterns": [r"\bITC\s+(?:Ltd|Limited|shares?|hotels?|Q[1-4]|profit)\b"]},
    {"ticker": "ADANIENT.NS", "name": "Adani Enterprises", "exchange": "NSE", "sector": "Conglomerate", "patterns": [r"\bAdani\s+Enterprises\b"]},
    {"ticker": "ADANIPORTS.NS", "name": "Adani Ports", "exchange": "NSE", "sector": "Infrastructure", "patterns": [r"\bAdani\s+Ports\b"]},
    {"ticker": "MARUTI.NS", "name": "Maruti Suzuki", "exchange": "NSE", "sector": "Automobile", "patterns": [r"\bMaruti\s+Suzuki\b", r"\bMaruti\b"]},
    {"ticker": "SUNPHARMA.NS", "name": "Sun Pharma", "exchange": "NSE", "sector": "Pharma", "patterns": [r"\bSun\s+Pharma\b"]},
    {"ticker": "BAJFINANCE.NS", "name": "Bajaj Finance", "exchange": "NSE", "sector": "NBFC", "patterns": [r"\bBajaj\s+Finance\b"]},
    {"ticker": "DISHTV.NS", "name": "Dish TV India", "exchange": "NSE", "sector": "Media", "patterns": [r"\bDish\s+TV\b"]},
    {"ticker": "IDEA.NS", "name": "Vodafone Idea", "exchange": "NSE", "sector": "Telecom", "patterns": [r"\bVodafone\s+Idea\b", r"\bIdea\s+Cellular\b", r"\bVi\s+telecom\b"]},
    {"ticker": "SAIL.NS", "name": "Steel Authority of India", "exchange": "NSE", "sector": "Metals", "patterns": [r"\bSteel\s+Authority\s+of\s+India\b", r"\bSAIL\s+steel\b", r"\bSAIL\s+plants?\b", r"\bSAIL\s+shares?\b"]},
    
    # Global Mega-Caps
    {"ticker": "NVDA", "name": "Nvidia", "exchange": "NASDAQ", "sector": "Semiconductors", "patterns": [r"\bNvidia\b", r"\bNVDA\b", r"\bJensen\s+Huang\b"]},
    {"ticker": "MSFT", "name": "Microsoft", "exchange": "NASDAQ", "sector": "Technology", "patterns": [r"\bMicrosoft\b", r"\bMSFT\b", r"\bSatya\s+Nadella\b"]},
    {"ticker": "AAPL", "name": "Apple", "exchange": "NASDAQ", "sector": "Technology", "patterns": [r"\bApple\s+(?:Inc|iPhone|iPad|Mac|shares?|stock|CEO|Q[1-4]|earnings|revenue)\b", r"\bAAPL\b"]},
    {"ticker": "TSLA", "name": "Tesla", "exchange": "NASDAQ", "sector": "Automotive / Tech", "patterns": [r"\bTesla\b", r"\bTSLA\b", r"\bElon\s+Musk\b"]},
    {"ticker": "AMZN", "name": "Amazon", "exchange": "NASDAQ", "sector": "E-Commerce / Cloud", "patterns": [r"\bAmazon\s+(?:AWS|shares?|stock|Q[1-4]|earnings|e-commerce|cloud)\b", r"\bAMZN\b"]},
    {"ticker": "GOOGL", "name": "Alphabet / Google", "exchange": "NASDAQ", "sector": "Technology", "patterns": [r"\bAlphabet\s+Inc\b", r"\bGoogle\s+(?:Cloud|search|AI|shares?|stock|Q[1-4]|earnings)\b", r"\bGOOGL?\b"]},
    {"ticker": "CISCO", "name": "Cisco Systems", "exchange": "NASDAQ", "sector": "Networking", "patterns": [r"\bCisco\s+(?:Systems|shares?|stock|Q[1-4]|earnings|CEO|Reports)\b", r"\bCSCO\b"]}
]

BULLISH_KEYWORDS = ["surges", "beats", "jumps", "rally", "rallies", "profit up", "growth", "secures order", "contract", "record high", "dividend", "outperform", "buy", "bullish", "upper circuit"]
BEARISH_KEYWORDS = ["slumps", "plunges", "misses", "losses", "loss widens", "fraud", "raid", "resigns", "downgrade", "sell", "bearish", "crash", "probe", "outage", "scandal", "lower circuit"]

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

def analyze_headline(title):
    matched_tickers = []
    for entry in TICKER_DB:
        for pat in entry["patterns"]:
            # Strict regex matching
            if re.search(pat, title, re.IGNORECASE if not pat.isupper() else 0):
                matched_tickers.append({
                    "ticker": entry["ticker"],
                    "name": entry["name"],
                    "exchange": entry["exchange"],
                    "sector": entry["sector"]
                })
                break

    t_lower = title.lower()
    bull_score = sum(1 for w in BULLISH_KEYWORDS if w in t_lower)
    bear_score = sum(1 for w in BEARISH_KEYWORDS if w in t_lower)

    sentiment = "NEUTRAL"
    score = 0.0
    if bull_score > bear_score:
        sentiment = "BULLISH"
        score = min(1.0, 0.4 + bull_score * 0.25)
    elif bear_score > bull_score:
        sentiment = "BEARISH"
        score = max(-1.0, -0.4 - bear_score * 0.25)

    urgency = "LOW"
    if any(w in t_lower for w in ["q1", "q2", "q3", "q4", "results", "earnings", "profit", "cbi", "raid", "probe", "resigns", "outage", "contract", "order", "merger"]):
        urgency = "HIGH"
    elif bull_score > 0 or bear_score > 0:
        urgency = "MEDIUM"

    return matched_tickers, sentiment, score, urgency

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
                    tickers, sent, sent_score, urg = analyze_headline(t_text)
                    items_out.append({
                        "id": art_id,
                        "source": name,
                        "title": t_text,
                        "url": l_text,
                        "summary": d_text,
                        "published_at": p_text,
                        "ingested_at": datetime.now(timezone.utc).isoformat(),
                        "tickers": tickers,
                        "sentiment": sent,
                        "sentiment_score": sent_score,
                        "urgency": urg
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
        now = datetime.now(timezone.utc)
        day_dir = os.path.join(temp_dir, "data", now.strftime("%Y-%m-%d"))
        os.makedirs(day_dir, exist_ok=True)

        chunk_file = f"wire_{now.strftime('%H-%M-%S')}.json.gz"
        chunk_path = os.path.join(day_dir, chunk_file)

        comp = gzip.compress(json.dumps(new_articles, ensure_ascii=False, indent=2).encode("utf-8"))
        with open(chunk_path, "wb") as f:
            f.write(comp)

        total_ingested = ckpt.get("articles_ingested", 0) + len(new_articles)
        ckpt["articles_ingested"] = total_ingested
        ckpt["last_stream_time"] = now.isoformat()
        ckpt["sources_monitored"] = len(FEEDS)

        with open(ckpt_path, "w", encoding="utf-8") as f:
            json.dump(ckpt, f, indent=2)

        # Keep seen_hashes capped to last 50,000 to keep repo light
        trimmed_hashes = list(seen_hashes)[-50000:]
        with open(seen_path, "w", encoding="utf-8") as f:
            json.dump(trimmed_hashes, f)

        safe_git(["git", "config", "user.name", "LiveWireBot"], cwd=temp_dir)
        safe_git(["git", "config", "user.email", "livewire@intelligence.internal"], cwd=temp_dir)
        safe_git(["git", "add", "-A"], cwd=temp_dir)

        commit_msg = f"[LIVE-WIRE-NLP] Stream +{len(new_articles):,} items with Smart Ticker/Sentiment Tagging (Total: {total_ingested:,}) [skip ci]"
        safe_git(["git", "commit", "-m", commit_msg], cwd=temp_dir)

        print(f"[PUSH] Pushing to {VAULT_NAME}...")
        safe_git(["git", "push", "origin", "main"], cwd=temp_dir)
        print(f"[SUCCESS] {commit_msg}")
    else:
        print("[INFO] No new breaking stories in this minute cycle.")

    subprocess.run(["rm", "-rf", temp_dir])

if __name__ == "__main__":
    main()
