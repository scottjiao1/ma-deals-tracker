import feedparser
import requests
from datetime import datetime, timedelta
import json

print("Starting M&A article fetch...")

articles = []

headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# ─── SOURCE 1: GOOGLE NEWS RSS (M&A) ─────────────────────────────
print("\nFetching Google News — M&A deals...")

google_ma_url = "https://news.google.com/rss/search?q=merger+acquisition+billion&hl=en-US&gl=US&ceid=US:en"
response1 = requests.get(google_ma_url, headers=headers)
google_ma_feed = feedparser.parse(response1.content)

for entry in google_ma_feed.entries:
    articles.append({
        "headline": entry.title,
        "url": entry.link,
        "date": entry.get("published", "Unknown"),
        "source": "Google News",
        "text": entry.get("summary", "")
    })

print(f"Google News M&A: {len(google_ma_feed.entries)} articles found")

# ─── SOURCE 2: GOOGLE NEWS RSS (DEALS) ───────────────────────────
print("\nFetching Google News — deal announcements...")

google_deals_url = "https://news.google.com/rss/search?q=acquires+deal+announcement&hl=en-US&gl=US&ceid=US:en"
response2 = requests.get(google_deals_url, headers=headers)
google_deals_feed = feedparser.parse(response2.content)

for entry in google_deals_feed.entries:
    articles.append({
        "headline": entry.title,
        "url": entry.link,
        "date": entry.get("published", "Unknown"),
        "source": "Google News",
        "text": entry.get("summary", "")
    })

print(f"Google News Deals: {len(google_deals_feed.entries)} articles found")

# ─── SOURCE 3: SEC EDGAR ─────────────────────────────────────────
print("\nFetching SEC EDGAR...")

sec_url = "https://efts.sec.gov/LATEST/search-index?q=%22merger%22+%22acquisition%22&dateRange=custom&startdt={}&enddt={}&forms=8-K".format(
    (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"),
    datetime.now().strftime("%Y-%m-%d")
)

try:
    sec_response = requests.get(
        sec_url,
        headers={"User-Agent": "ma-deals-tracker contact@example.com"}
    )
    sec_data = sec_response.json()
    sec_hits = sec_data.get("hits", {}).get("hits", [])

    for hit in sec_hits:
        source = hit.get("_source", {})
        articles.append({
            "headline": source.get("display_names", ["Unknown"])[0] + " — SEC Filing",
            "url": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=" + source.get("entity_id", ""),
            "date": source.get("file_date", "Unknown"),
            "source": "SEC EDGAR",
            "text": source.get("file_date", "") + " filing"
        })

    print(f"SEC EDGAR: {len(sec_hits)} filings found")

except Exception as e:
    print(f"SEC EDGAR error: {e}")
    print("Skipping SEC EDGAR and continuing...")

# ─── REMOVE DUPLICATES ───────────────────────────────────────────
seen_urls = set()
unique_articles = []
for article in articles:
    if article["url"] not in seen_urls:
        seen_urls.add(article["url"])
        unique_articles.append(article)

print(f"\nTotal after dedup: {len(unique_articles)}")

# ─── FILTER TO M&A RELEVANT ONLY ─────────────────────────────────
print("Filtering for M&A relevant articles...")

ma_keywords = [
    "acquires", "acquisition", "merger", "merges", "takeover",
    "buyout", "deal", "billion", "purchase", "buys"
]

filtered_articles = []
for article in unique_articles:
    headline_lower = article["headline"].lower()
    if any(keyword in headline_lower for keyword in ma_keywords):
        filtered_articles.append(article)

print(f"M&A relevant articles: {len(filtered_articles)} out of {len(unique_articles)}")

# ─── SAVE TO FILE ────────────────────────────────────────────────
with open("data/raw_articles.json", "w") as f:
    json.dump(filtered_articles, f, indent=2)

print(f"\nSaved {len(filtered_articles)} articles to data/raw_articles.json")
print("Done!")