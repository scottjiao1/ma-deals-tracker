import json
import re
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from difflib import SequenceMatcher

INPUT_FILE = "data/raw_articles.json"
OUTPUT_FILE = "data/filtered_articles.json"
MAX_OUTPUT = 20

print("Starting simplified pre-filter...")

# -----------------------------
# Load data
# -----------------------------

with open(INPUT_FILE, "r") as f:
    articles = json.load(f)

print(f"Loaded {len(articles)} raw articles")


# -----------------------------
# Helper functions
# -----------------------------

def clean_text(text):
    return re.sub(r"\s+", " ", str(text).lower()).strip()


def parse_article_date(date_str):
    try:
        if "T" in str(date_str):
            return datetime.fromisoformat(str(date_str).replace("Z", "+00:00")).replace(tzinfo=None)
        return parsedate_to_datetime(str(date_str)).replace(tzinfo=None)
    except Exception:
        return None


def extract_publisher(article):
    text = str(article.get("text", ""))
    match = re.search(r'<font color="#6f6f6f">(.*?)</font>', text)

    if match:
        return match.group(1).lower()

    return clean_text(article.get("source", ""))


def is_bad_article(article):
    headline = clean_text(article.get("headline", ""))
    text = clean_text(article.get("text", ""))
    publisher = extract_publisher(article)
    url = clean_text(article.get("url", ""))

    combined = f"{headline} {text} {publisher} {url}"

    blocked_sources = [
        "the onion", "espn", "yahoo sports", "bleacher report",
        "motley fool", "facebook.com"
    ]

    bad_terms = [
        # Commentary / analysis
        "what it means", "could mean", "here's why", "explained",
        "opinion", "analysis", "commentary", "roundup", "top 10", "top 5",

        # Market / stock articles
        "stock price", "shares rise", "shares fall", "stock falls",
        "stock gains", "earnings", "outlook", "rallies", "surges",
        "soars", "pops", "climbs",

        # Not new M&A
        "watchdog", "regulatory approval", "offers concessions",
        "may intervene", "intervene", "debt", "loan", "credit facility",
        "bond offering", "share repurchase", "dividend",

        # Rejected / rumor language
        "rejects", "rejected", "snubs", "turns down", "knocks back",
        "in talks", "considering bid", "weighs bid", "front-runner",

        # Sports / politics / military
        "nhl", "nba", "nfl", "mlb", "transfer fee", "contract extension",
        "election", "campaign", "mayor", "missile", "air defense",
        "military contract"
    ]

    return (
        any(source in combined for source in blocked_sources) or
        any(term in combined for term in bad_terms)
    )


def is_likely_ma(article):
    headline = clean_text(article.get("headline", ""))
    text = clean_text(article.get("text", ""))

    combined = f"{headline} {text}"

    ma_terms = [
        "to acquire", "acquires", "acquired", "acquisition",
        "to buy", "buys", "buyout", "merger", "merge",
        "agreement to acquire", "definitive agreement",
        "purchase agreement", "asset purchase", "stock purchase",
        "takeover bid", "offer for", "stake in",
        "combination", "business combination",
        "completed acquisition", "closes acquisition",
        "announces acquisition"
    ]

    return any(term in combined for term in ma_terms)


def has_billion_signal(article):
    combined = f"{article.get('headline', '')} {article.get('text', '')}".lower()

    billion_patterns = [
        r"\$\s?\d+(\.\d+)?\s?b\b",
        r"\$\s?\d+(\.\d+)?\s?bn\b",
        r"\$\s?\d+(\.\d+)?\s?billion",
        r"us\$\s?\d+(\.\d+)?\s?b\b",
        r"us\$\s?\d+(\.\d+)?\s?bn\b",
        r"us\$\s?\d+(\.\d+)?\s?billion",
        r"au\$\s?\d+(\.\d+)?\s?b\b",
        r"au\$\s?\d+(\.\d+)?\s?bn\b",
        r"au\$\s?\d+(\.\d+)?\s?billion",
        r"£\s?\d+(\.\d+)?\s?b\b",
        r"£\s?\d+(\.\d+)?\s?bn\b",
        r"£\s?\d+(\.\d+)?\s?billion",
        r"€\s?\d+(\.\d+)?\s?b\b",
        r"€\s?\d+(\.\d+)?\s?bn\b",
        r"€\s?\d+(\.\d+)?\s?billion",
        r"\d+(\.\d+)?\s?billion",
        r"\d+(\.\d+)?\s?bn\b"
    ]

    return any(re.search(pattern, combined) for pattern in billion_patterns)


def is_recent(article, days=7):
    article_date = parse_article_date(article.get("date", ""))

    if article_date is None:
        return True

    return article_date >= datetime.now() - timedelta(days=days)


def normalize_for_similarity(article):
    text = clean_text(article.get("headline", ""))

    text = re.sub(r"\$?\d+(\.\d+)?\s?(billion|million|bn|b|m)\b", " ", text)
    text = re.sub(r"us\$|au\$|£|€|\$", " ", text)
    text = re.sub(r"[^a-z0-9\s]", " ", text)

    remove_words = {
        "to", "in", "a", "the", "and", "of", "for", "by", "deal",
        "billion", "million", "its", "with", "as", "at", "is", "an",
        "from", "on", "into", "will", "has", "have", "been", "be",
        "that", "this", "are", "was", "it", "or", "but", "after",
        "over", "up", "out", "about", "new", "says", "said", "would",
        "could", "may", "than", "also", "per", "vs", "via", "amid",
        "company", "firm", "corp", "corporation", "inc", "ltd", "plc",
        "llc", "co", "group", "holdings", "holding", "international",
        "business", "assets", "operations",

        # M&A verbs
        "acquires", "acquire", "acquired", "acquisition", "merger",
        "merge", "buys", "buy", "buyout", "purchase", "takeover",
        "bid", "offer", "stake", "agreement", "announces", "completed",
        "closes", "definitive"
    }

    words = [
        w for w in text.split()
        if w not in remove_words and len(w) > 2 and not w.isdigit()
    ]

    return " ".join(words)


def extract_value_signature(article):
    text = clean_text(article.get("headline", ""))

    match = re.search(r"(\d+\.?\d*)\s?(billion|bn\b)", text)
    if match:
        return match.group(1)

    match = re.search(r"\$\s?(\d+\.?\d*)\s?b\b", text)
    if match:
        return match.group(1)

    return ""


def similarity(a, b):
    return SequenceMatcher(None, a, b).ratio()


def is_same_deal(article_a, article_b):
    norm_a = article_a.get("normalized_headline", "")
    norm_b = article_b.get("normalized_headline", "")

    if not norm_a or not norm_b:
        return False

    words_a = set(norm_a.split())
    words_b = set(norm_b.split())

    overlap = len(words_a & words_b)
    smaller_set = min(len(words_a), len(words_b))

    if smaller_set > 0:
        overlap_ratio = overlap / smaller_set
        text_similarity = similarity(norm_a, norm_b)

        if overlap_ratio >= 0.55 or text_similarity >= 0.70:
            return True

    value_a = extract_value_signature(article_a)
    value_b = extract_value_signature(article_b)

    if value_a and value_b and value_a == value_b:
        overlap_ratio = len(words_a & words_b) / max(1, smaller_set)
        if overlap_ratio >= 0.35:
            return True

    return False


# -----------------------------
# Step 1: Basic filtering
# -----------------------------

filtered = []

for article in articles:
    if is_bad_article(article):
        continue
    if not is_recent(article):
        continue
    if not is_likely_ma(article):
        continue
    if not has_billion_signal(article):
        continue

    article["publisher"] = extract_publisher(article)
    article["normalized_headline"] = normalize_for_similarity(article)

    filtered.append(article)

print(f"After basic filters: {len(filtered)}")


# -----------------------------
# Step 2: Group duplicate deals
# -----------------------------

deal_groups = []

for article in filtered:
    added = False

    for group in deal_groups:
        representative = group[0]

        if is_same_deal(article, representative):
            group.append(article)
            added = True
            break

    if not added:
        deal_groups.append([article])

print(f"Unique deal groups: {len(deal_groups)}")


# -----------------------------
# Step 3: Collapse groups
# -----------------------------

collapsed_deals = []

for group in deal_groups:
    best_article = group[0]

    source_list = []
    url_variants = []
    headline_variants = []

    for article in group:
        publisher = article.get("publisher", "")

        if publisher and publisher not in source_list:
            source_list.append(publisher)

        if article.get("url") and article.get("url") not in url_variants:
            url_variants.append(article.get("url"))

        if article.get("headline") and article.get("headline") not in headline_variants:
            headline_variants.append(article.get("headline"))

    best_article["mention_count"] = len(group)
    best_article["source_list"] = source_list
    best_article["url_variants"] = url_variants
    best_article["headline_variants"] = headline_variants

    collapsed_deals.append(best_article)


# -----------------------------
# Step 4: Sort by coverage
# -----------------------------

collapsed_deals = sorted(
    collapsed_deals,
    key=lambda x: x.get("mention_count", 1),
    reverse=True
)

final_articles = collapsed_deals[:MAX_OUTPUT]


# -----------------------------
# Save
# -----------------------------

with open(OUTPUT_FILE, "w") as f:
    json.dump(final_articles, f, indent=2)

print("\nPre-filter complete")
print(f"Started with: {len(articles)} articles")
print(f"After filters: {len(filtered)} articles")
print(f"Unique deals: {len(collapsed_deals)}")
print(f"Sent to Claude: {len(final_articles)} articles")

print("\nArticles queued for Claude:")
for i, article in enumerate(final_articles, start=1):
    print(
        f"{i:2}. [x{article.get('mention_count', 1)}] "
        f"{article.get('headline', '')[:90]}"
    )
    print(f"    sources: {', '.join(article.get('source_list', [])[:4])}")