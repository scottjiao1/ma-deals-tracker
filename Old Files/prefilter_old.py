import json
import re
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from difflib import SequenceMatcher

INPUT_FILE = "data/raw_articles2.json"
OUTPUT_FILE = "data/filtered_articles.json"
MAX_OUTPUT = 20

print("Starting pre-filter...")

with open(INPUT_FILE, "r") as f:
    articles = json.load(f)

print(f"Total articles loaded: {len(articles)}")


# ─── HELPER FUNCTIONS ─────────────────────────────────────────────

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
    text = article.get("text", "")
    match = re.search(r'<font color="#6f6f6f">(.*?)</font>', str(text))
    if match:
        return match.group(1).lower()
    return article.get("source", "").lower()


def is_bad_article(article):
    headline = clean_text(article.get("headline", ""))
    publisher = extract_publisher(article)
    url = clean_text(article.get("url", ""))
    combined = f"{headline} {publisher} {url}"

    blocked_sources = [
        "the onion", "facebook.com", "espn", "yahoo sports",
        "bleacher report", "motley fool"
    ]

    bad_terms = [
        # Stock/market analysis not deals
        "stock price", "shares rise", "shares fall", "stock falls",
        "stock gains", "earnings", "raises fiscal", "outlook",
        "share price jump", "soars on", "pops on", "climbs on",
        "rises on", "surges on", "rallies on",
        # Not M&A
        "debt well before sale", "banks get bids", "what it means",
        "could mean", "here's why", "explained", "opinion:",
        "analysis:", "comment:", "roundup", "top 10", "top 5",
        "watchdog", "ethics filing", "long-term lease",
        "military contract", "missile defense", "air defense",
        "pentagon for $800", "record $200 billion",
        "sector mergers and acquisitions", "market activity",
        "industry overview", "market reaches", "market value",
        # Political not M&A
        "harris reaches", "socialist mayor", "journalist jumps",
        # Sports
        "nhl", "nba", "nfl", "mlb", "transfer fee",
        "signs with", "signs for", "contract extension",
    ]

    return (
        any(s in combined for s in blocked_sources) or
        any(t in combined for t in bad_terms)
    )


def is_likely_ma(article):
    headline = clean_text(article.get("headline", ""))

    ma_terms = [
        "to acquire", "acquires", "acquired", "acquisition",
        "to buy", "buys", "buyout", "merger", "merge",
        "takeover", "bid for", "offer for", "stake in",
        "purchase of", "agreement to", "deal to"
    ]

    return any(term in headline for term in ma_terms)


def has_billion_signal(article):
    headline = article.get("headline", "").lower()

    patterns = [
        r"\$\s?\d+(\.\d+)?\s?(b\b|bn\b|billion)",
        r"us\$\s?\d+(\.\d+)?\s?billion",
        r"au\$\s?\d+(\.\d+)?\s?billion",
        r"£\s?\d+(\.\d+)?\s?(b\b|bn\b|billion)",
        r"€\s?\d+(\.\d+)?\s?(b\b|bn\b|billion)",
        r"\d+(\.\d+)?\s?billion",
        r"\d+(\.\d+)?\s?bn\b",
    ]

    return any(re.search(p, headline) for p in patterns)


def get_source_score(article):
    publisher = extract_publisher(article)
    url = clean_text(article.get("url", ""))
    headline = clean_text(article.get("headline", ""))
    source_text = f"{publisher} {url} {headline}"

    # Tier 1 — Free, reliable, scrapeable
    if "reuters" in source_text:
        return 100
    if "cnbc" in source_text:
        return 95
    if any(s in source_text for s in ["ft.com", "financial times"]):
        return 88
    if "sec edgar" in source_text:
        return 85
    if any(s in source_text for s in ["pr newswire", "globenewswire", "businesswire"]):
        return 82

    # Tier 2 — Free, decent quality
    if "yahoo finance" in source_text:
        return 75
    if any(s in source_text for s in ["business journals", "bizjournals"]):
        return 70
    if any(s in source_text for s in ["qz.com", "business insider"]):
        return 65
    if any(s in source_text for s in ["south china morning post", "scmp"]):
        return 60
    if any(s in source_text for s in ["techcrunch", "axios"]):
        return 65

    # Tier 3 — Paywalled, deprioritize
    if any(s in source_text for s in ["wsj", "wall street journal"]):
        return 30
    if "bloomberg" in source_text:
        return 30

    # Tier 4 — Low quality / obscure
    if any(s in source_text for s in [
        "minichart", "tech my money", "tradingkey",
        "proactive", "marketscreener"
    ]):
        return 10

    return 40


def get_recency_score(article):
    article_date = parse_article_date(article.get("date", ""))

    if article_date is None:
        return 0

    age_days = (datetime.now() - article_date).days

    if age_days <= 1:
        return 10
    if age_days <= 3:
        return 6
    if age_days <= 7:
        return 2
    return -20


def get_article_score(article):
    score = 0
    score += get_source_score(article)
    score += get_recency_score(article)

    headline = clean_text(article.get("headline", ""))

    if is_likely_ma(article):
        score += 15

    if has_billion_signal(article):
        score += 8

    strong_terms = [
        "to acquire", "acquires", "acquired", "buys",
        "to buy", "merger", "takeover bid", "buyout",
        "agreement to acquire", "definitive agreement"
    ]
    if any(term in headline for term in strong_terms):
        score += 10

    soft_terms = [
        "may intervene", "front-runner", "nears deal",
        "could top", "in talks"
    ]
    if any(term in headline for term in soft_terms):
        score -= 8

    return score


def get_deal_signature(article):
    """
    Creates acquirer_proxy + deal_value signature.
    Catches same deal described with different target names.
    Example: KKR acquires EDF Power Solutions vs
             KKR acquires EDF Renewable Energy Business
    Both have KKR + $4.2B → same signature → same deal.
    """
    headline = clean_text(article.get("headline", ""))

    value_match = re.search(
        r"(\d+\.?\d*)\s*(billion|bn\b)",
        headline
    )
    value_str = value_match.group(1) if value_match else ""

    skip_words = {
        "acquire", "acquires", "acquisition", "merger", "buys",
        "purchase", "billion", "deal", "stake", "the", "and",
        "for", "to", "in", "of", "a", "an", "its"
    }
    words = [
        w for w in headline.split()
        if len(w) > 3 and w not in skip_words
    ]
    acquirer_proxy = " ".join(words[:2]) if words else ""

    if acquirer_proxy and value_str:
        return f"{acquirer_proxy}_{value_str}"
    return ""


def normalize_for_similarity(headline):
    headline = clean_text(headline)
    headline = re.sub(r"\$?\d+(\.\d+)?\s?(billion|million|bn|b|m)\b", " ", headline)
    headline = re.sub(r"us\$|au\$|£|€|\$", " ", headline)
    headline = re.sub(r"[^a-z0-9\s]", " ", headline)

    remove_words = {
        "to", "in", "a", "the", "and", "of", "for", "by", "deal",
        "billion", "million", "its", "with", "as", "at", "is", "an",
        "from", "on", "into", "will", "has", "have", "been", "be",
        "that", "this", "are", "was", "it", "or", "but", "after",
        "over", "up", "out", "about", "new", "says", "said", "would",
        "could", "may", "than", "also", "per", "vs", "via", "amid",
        "acquires", "acquire", "acquisition", "merger", "buys", "buy",
        "purchase", "stake", "takeover", "bid", "offer", "closes",
        "completes", "announces", "signs", "reaches", "agrees",
        "agreed", "entered", "strikes", "company", "firm", "corp",
        "corporation", "inc", "ltd", "plc", "llc", "co", "group",
        "holdings", "international", "business", "assets", "operations"
    }

    words = [
        w for w in headline.split()
        if w not in remove_words and len(w) > 2 and not w.isdigit()
    ]
    return " ".join(words)


def similarity(a, b):
    return SequenceMatcher(None, a, b).ratio()


def is_same_deal(article_a, article_b):
    # Check 1: normalized headline similarity
    a = article_a.get("normalized_headline", "")
    b = article_b.get("normalized_headline", "")

    if a and b:
        words_a = set(a.split())
        words_b = set(b.split())
        overlap = len(words_a & words_b)
        smaller_set = min(len(words_a), len(words_b))

        if smaller_set > 0:
            overlap_ratio = overlap / smaller_set
            text_sim = similarity(a, b)
            if overlap_ratio >= 0.55 or text_sim >= 0.70:
                return True

    # Check 2: same acquirer proxy + same deal value
    sig_a = get_deal_signature(article_a)
    sig_b = get_deal_signature(article_b)

    if sig_a and sig_b and sig_a == sig_b and len(sig_a) > 5:
        return True

    return False


# ─── STEP 1: REMOVE JUNK AND NON-M&A ─────────────────────────────
step1 = []
for article in articles:
    if is_bad_article(article):
        continue
    if not is_likely_ma(article):
        continue
    if not has_billion_signal(article):
        continue
    step1.append(article)

print(f"After junk + M&A + billion filter: {len(step1)}")


# ─── STEP 2: KEEP ONLY LAST 7 DAYS ───────────────────────────────
seven_days_ago = datetime.now() - timedelta(days=7)
step2 = []

for article in step1:
    article_date = parse_article_date(article.get("date", ""))
    if article_date is None or article_date >= seven_days_ago:
        step2.append(article)

print(f"After recency filter: {len(step2)}")


# ─── STEP 3: SCORE AND ENRICH ─────────────────────────────────────
for article in step2:
    article["score"] = get_article_score(article)
    article["publisher"] = extract_publisher(article)
    article["normalized_headline"] = normalize_for_similarity(
        article.get("headline", "")
    )


# ─── STEP 4: SORT BY SCORE ────────────────────────────────────────
sorted_articles = sorted(
    step2,
    key=lambda x: x.get("score", 0),
    reverse=True
)


# ─── STEP 5: GROUP BY DEAL AND KEEP BEST SOURCE ───────────────────
deal_groups = []

for article in sorted_articles:
    added_to_group = False

    for group in deal_groups:
        representative = group["articles"][0]
        if is_same_deal(article, representative):
            group["articles"].append(article)
            added_to_group = True
            break

    if not added_to_group:
        deal_groups.append({"articles": [article]})


# ─── STEP 6: COLLAPSE GROUPS ──────────────────────────────────────
collapsed_deals = []

for group in deal_groups:
    group_articles = sorted(
        group["articles"],
        key=lambda x: x.get("score", 0),
        reverse=True
    )

    best_article = group_articles[0]

    source_list = []
    url_list = []
    headline_list = []

    for a in group_articles:
        publisher = a.get("publisher") or extract_publisher(a)
        url = a.get("url", "")
        headline = a.get("headline", "")

        if publisher and publisher not in source_list:
            source_list.append(publisher)
        if url and url not in url_list:
            url_list.append(url)
        if headline and headline not in headline_list:
            headline_list.append(headline)

    best_article["mention_count"] = len(group_articles)
    best_article["source_list"] = source_list
    best_article["url_variants"] = url_list
    best_article["headline_variants"] = headline_list
    best_article["final_prefilter_score"] = (
        best_article.get("score", 0) + (len(group_articles) * 8)
    )

    collapsed_deals.append(best_article)

print(f"After collapsing duplicates: {len(collapsed_deals)} unique deals")


# ─── STEP 7: SORT AND CAP ─────────────────────────────────────────
collapsed_deals = sorted(
    collapsed_deals,
    key=lambda x: x.get("final_prefilter_score", 0),
    reverse=True
)

final_articles = collapsed_deals[:MAX_OUTPUT]


# ─── STEP 8: SAVE ─────────────────────────────────────────────────
with open(OUTPUT_FILE, "w") as f:
    json.dump(final_articles, f, indent=2)

print("\n" + "=" * 70)
print("Pre-filter complete")
print(f"  Started with:       {len(articles):>4} articles")
print(f"  After filtering:    {len(step2):>4} articles")
print(f"  Unique deal groups: {len(collapsed_deals):>4} deals")
print(f"  Sent to Claude:     {len(final_articles):>4} articles")
print(f"  Est. Claude cost:  ~${len(final_articles) * 0.01:.2f}")
print("=" * 70)

print("\nArticles queued for Claude:")
for i, article in enumerate(final_articles, start=1):
    sources = ", ".join(article.get("source_list", [])[:3])
    tier = (
        "★★★" if get_source_score(article) >= 88 else
        "★★ " if get_source_score(article) >= 60 else
        "★  "
    )
    print(
        f"  {i:2}. [{tier}] "
        f"[score {article.get('final_prefilter_score', 0):3}] "
        f"[x{article.get('mention_count', 1)}] "
        f"{article.get('headline', '')[:70]}"
    )
    print(f"       sources: {sources}")