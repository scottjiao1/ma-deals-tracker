import feedparser
import requests
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
import json
import os
#imports a bunch of libraries that help read RSS feeds, make HTTP requests, read JSOn files etc.

print("Starting M&A article fetch — Google News + SEC EDGAR...")

articles = []

os.makedirs("data", exist_ok=True) #guarantees that the "data" directory exists, creating it if necessary

headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36"
}
#Makes request look like it is coming from Google Chrome and not Python Script

MAX_ENTRIES_PER_QUERY = 50

# ─── GOOGLE NEWS QUERIES — focused on COMPLETED deals ─────────────

google_queries = [
    "completes acquisition billion",
    "closes acquisition billion",
    "acquires billion deal",
    "finalizes merger billion",
]
#Google returns RSS feed for these queries

print("\nFetching Google News queries (completed deals)...")

for query in google_queries: 
    url_query = query.replace(" ", "+")
    url = f"https://news.google.com/rss/search?q={url_query}&hl=en-US&gl=US&ceid=US:en"

    try: #Tries to fetch the RSS feed for the query and parse it using feedparser. If successful, it extracts the relevant information from each entry and appends it to the articles list. If an error occurs, it prints an error message.
        response = requests.get(url, headers=headers, timeout=10)
        feed = feedparser.parse(response.content)

        entries = feed.entries[:MAX_ENTRIES_PER_QUERY] #only takes first 50 entries

        for entry in entries: #For each entry in the feed, it extracts the title, link, published date, and summary, and appends it to the articles list as a dictionary with keys "headline", "url", "date", "source", and "text".
            articles.append({
                "headline": entry.get("title", ""),
                "url": entry.get("link", ""),
                "date": entry.get("published", "Unknown"),
                "source": "Google News",
                "text": entry.get("summary", "")
            }) #builds a standard structure for each article with the relevant information extracted from the RSS feed entry.

        print(f"  '{query}': {len(entries)} articles")

    except Exception as e:
        print(f"  '{query}' error: {e}")


# ─── SEC EDGAR ─────────────────────────────────────────────────────

print("\nFetching SEC EDGAR...")

start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d") #last 7 days
end_date = datetime.now().strftime("%Y-%m-%d")

sec_url = (
    f"https://efts.sec.gov/LATEST/search-index?"
    f"q=%22merger%22+%22acquisition%22"
    f"&dateRange=custom&startdt={start_date}&enddt={end_date}&forms=8-K"
)

try: #Sends a GET request to the SEC EDGAR search API to fetch filings related to mergers and acquisitions within the last 7 days. It processes the response, extracts relevant information, and appends it to the articles list. If an error occurs, it prints an error message.
    sec_response = requests.get(
        sec_url,
        headers={"User-Agent": "ma-deals-tracker contact@example.com"},
        timeout=10
    )

    sec_data = sec_response.json()
    sec_hits = sec_data.get("hits", {}).get("hits", [])
    sec_hits = sec_hits[:MAX_ENTRIES_PER_QUERY]

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


# ─── DEDUPLICATE BY URL ────────────────────────────────────────────

print(f"\nTotal raw articles before dedup: {len(articles)}")

seen_urls = set()
unique_articles = []

for article in articles: #Deduplicates the articles list by checking if the URL of each article has already been seen. If the URL is unique, it adds the article to the unique_articles list and marks the URL as seen. Finally, it prints the count of unique articles after deduplication.
    url = article.get("url", "")
    if not url:
        continue
    if url not in seen_urls:
        seen_urls.add(url)
        unique_articles.append(article)

print(f"After URL dedup: {len(unique_articles)}")


# ─── FILTER: LAST 7 DAYS ──────────────────────────────────────────

print("Filtering for last 7 days...")

seven_days_ago = datetime.now() - timedelta(days=7)
recent_articles = [] #filters the unique_articles list to include only those articles that have a date within the last 7 days. It attempts to parse the date of each article and compares it to the date 7 days ago. If the article's date is within this range, it is added to the recent_articles list. If parsing fails, the article is also included in recent_articles. Finally, it prints the count of articles from the last 7 days.

for article in unique_articles:
    try:
        article_date = parsedate_to_datetime(article["date"])
        article_date = article_date.replace(tzinfo=None)
        if article_date >= seven_days_ago:
            recent_articles.append(article)
    except Exception:
        recent_articles.append(article)

print(f"Last 7 days: {len(recent_articles)}")


# ─── FILTER: MUST MENTION BILLION ─────────────────────────────────

print("Filtering for billion-dollar deals...")

billion_articles = []

for article in recent_articles: #for each article in the recent_articles list, it checks if the headline contains the words "billion" or "bn" (case-insensitive). If either of these keywords is found in the headline, the article is added to the billion_articles list. Finally, it prints the count of articles that mention billion-dollar deals.
    headline_lower = article.get("headline", "").lower()
    if "billion" in headline_lower or "bn" in headline_lower:
        billion_articles.append(article)

print(f"Billion-dollar deals: {len(billion_articles)}")


# ─── SAVE ──────────────────────────────────────────────────────────

with open("data/raw_articles.json", "w") as f: #writes the filtered list of billion-dollar deal articles to a JSON file named "raw_articles.json" in the "data" directory, formatting it with an indentation of 2 spaces for readability.
    json.dump(billion_articles, f, indent=2)

print(f"\nSaved {len(billion_articles)} articles to data/raw_articles.json")
print("Done!")