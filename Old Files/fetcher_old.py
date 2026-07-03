import feedparser
import requests
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
import json
import os

print("Starting M&A article fetch...")

articles = []

os.makedirs("data", exist_ok=True)

headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36"
}

MAX_ENTRIES_PER_FEED = 25

# ─── GOOGLE NEWS QUERIES ──────────────────────────────────────────

google_queries = [
    "merger acquisition billion",
    "company acquires billion",
    "private equity acquisition billion",
    "takeover bid billion",
]

print("\nFetching Google News queries...")

for query in google_queries:
    url_query = query.replace(" ", "+")
    url = f"https://news.google.com/rss/search?q={url_query}&hl=en-US&gl=US&ceid=US:en"

    try:
        response = requests.get(url, headers=headers, timeout=10)
        feed = feedparser.parse(response.content)

        entries = feed.entries[:MAX_ENTRIES_PER_FEED]

        for entry in entries:
            articles.append({
                "headline": entry.get("title", ""),
                "url": entry.get("link", ""),
                "date": entry.get("published", "Unknown"),
                "source": "Google News",
                "text": entry.get("summary", "")
            })

        print(f"  Google '{query}': {len(entries)} articles")

    except Exception as e:
        print(f"  Google '{query}' error: {e}")


# ─── GOOGLE NEWS INTERNATIONAL — LIGHT VERSION ────────────────────

international_queries = [
    "merger acquisition billion",
]

print("\nFetching Google News International...")

for query in international_queries:
    for region, lang in [("GB", "en-GB")]:
        url_query = query.replace(" ", "+")
        url = f"https://news.google.com/rss/search?q={url_query}&hl={lang}&gl={region}&ceid={region}:{lang[:2]}"

        try:
            response = requests.get(url, headers=headers, timeout=10)
            feed = feedparser.parse(response.content)

            entries = feed.entries[:MAX_ENTRIES_PER_FEED]

            for entry in entries:
                articles.append({
                    "headline": entry.get("title", ""),
                    "url": entry.get("link", ""),
                    "date": entry.get("published", "Unknown"),
                    "source": "Google News International",
                    "text": entry.get("summary", "")
                })

            print(f"  {region} '{query}': {len(entries)} articles")

        except Exception as e:
            print(f"  {region} error: {e}")



# ─── SEC EDGAR ────────────────────────────────────────────────────

print("\nFetching SEC EDGAR...")

start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
end_date = datetime.now().strftime("%Y-%m-%d")

sec_url = (
    f"https://efts.sec.gov/LATEST/search-index?"
    f"q=%22merger%22+%22acquisition%22"
    f"&dateRange=custom&startdt={start_date}&enddt={end_date}&forms=8-K"
)

try:
    sec_response = requests.get(
        sec_url,
        headers={"User-Agent": "ma-deals-tracker contact@example.com"},
        timeout=10
    )

    sec_data = sec_response.json()
    sec_hits = sec_data.get("hits", {}).get("hits", [])

    sec_hits = sec_hits[:50]

    for hit in sec_hits:
        source = hit.get("_source", {})
        display_names = source.get("display_names", ["Unknown"])
        entity_id = source.get("entity_id", "")

        articles.append({
            "headline": display_names[0] + " — SEC Filing",
            "url": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=" + entity_id,
            "date": source.get("file_date", "Unknown"),
            "source": "SEC EDGAR",
            "text": source.get("file_date", "") + " filing"
        })

    print(f"  SEC EDGAR: {len(sec_hits)} filings found")

except Exception as e:
    print(f"  SEC EDGAR error: {e}")


# ─── DEDUPLICATE BY URL ───────────────────────────────────────────

print(f"\nTotal raw articles before dedup: {len(articles)}")

seen_urls = set()
unique_articles = []

for article in articles:
    url = article.get("url", "")

    if not url:
        continue

    if url not in seen_urls:
        seen_urls.add(url)
        unique_articles.append(article)

print(f"After URL dedup: {len(unique_articles)}")


# ─── FILTER: LAST 7 DAYS ─────────────────────────────────────────

print("Filtering for last 7 days...")

seven_days_ago = datetime.now() - timedelta(days=7)
recent_articles = []

for article in unique_articles:
    try:
        article_date = parsedate_to_datetime(article["date"])
        article_date = article_date.replace(tzinfo=None)

        if article_date >= seven_days_ago:
            recent_articles.append(article)

    except Exception:
        recent_articles.append(article)

print(f"Last 7 days: {len(recent_articles)}")


# ─── FILTER: M&A KEYWORDS ─────────────────────────────────────────

print("Filtering for M&A keywords...")

ma_keywords = [
    "acquires", "acquire", "acquisition", "merger", "merges",
    "takeover", "buyout", "purchase", "buys", "stake",
    "agreement", "transaction", "combine", "offer", "bid"
]

filtered_articles = []

for article in recent_articles:
    headline_lower = article.get("headline", "").lower()

    if any(keyword in headline_lower for keyword in ma_keywords):
        filtered_articles.append(article)

print(f"M&A relevant: {len(filtered_articles)}")


# ─── SAVE ─────────────────────────────────────────────────────────

with open("data/raw_articles.json", "w") as f:
    json.dump(filtered_articles, f, indent=2)

print(f"\nSaved {len(filtered_articles)} articles to data/raw_articles.json")
print("Done!")