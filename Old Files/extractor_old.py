import anthropic
import json
import os
import re
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

INPUT_FILE = "data/filtered_articles.json"
OUTPUT_FILE = "data/deals.json"
MAX_FINAL_DEALS = 5

load_dotenv()
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def get_article_text(url):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0"
        }
        response = requests.get(url, headers=headers, timeout=10)

        soup = BeautifulSoup(response.content, "html.parser")
        paragraphs = soup.find_all("p")
        text = " ".join([p.get_text(" ", strip=True) for p in paragraphs])

        bad_signals = [
            "subscribe",
            "sign in",
            "log in",
            "enable javascript",
            "access denied",
            "cookies",
            "paywall"
        ]

        if any(signal in text.lower() for signal in bad_signals):
            return ""

        return text[:3000]

    except Exception as e:
        print(f"  Could not fetch article text: {e}")
        return ""


def choose_article_content(article):
    rss_summary = article.get("text", "") or ""
    headline = article.get("headline", "") or ""
    url = article.get("url", "") or ""

    scraped_text = get_article_text(url)

    if len(scraped_text) > len(rss_summary):
        return scraped_text

    if len(rss_summary) >= 50:
        return rss_summary

    return headline


def clean_json_response(text):
    return text.replace("```json", "").replace("```", "").strip()


def normalize_company_name(name):
    if not name:
        return ""

    name = name.lower().strip()
    name = re.sub(r"[^a-z0-9\s]", "", name)

    remove_words = {
        "inc", "corp", "corporation", "company", "co", "ltd",
        "plc", "llc", "group", "holdings", "holding",
        "limited", "sa", "ag", "se"
    }

    return " ".join([w for w in name.split() if w not in remove_words])


def extract_deal(article):
    headline = article.get("headline", "")
    source_url = article.get("url", "")
    publisher = article.get("publisher", article.get("source", ""))
    article_date = article.get("date", "")
    article_content = choose_article_content(article)

    prompt = f"""
You are an M&A analyst creating a daily deal dashboard.

Use ONLY the information below. Do not invent missing facts.

Headline:
{headline}

Article / RSS Content:
{article_content}

Publisher:
{publisher}

Article date:
{article_date}

Source URL:
{source_url}

Return ONLY valid JSON with this exact structure:

{{
  "acquirer": "string or null",
  "target": "string or null",
  "value": "string or null",
  "value_billions": number or null,
  "sector": "Tech, Healthcare, Energy, Finance, Media, Retail, Industrial, Consumer, Real Estate, Other",
  "geography": "string or null",
  "date": "YYYY-MM-DD or null",
  "rationale": "one concise sentence explaining strategic rationale, or null",
  "key_risk": "one concise sentence explaining the biggest risk, or null",
  "why_it_matters": "one concise sentence explaining why this deal matters to finance/consulting readers, or null",
  "deal_status": "Announced, Pending, Rejected, Rumored, Completed, or Other",
  "is_ma_deal": true or false,
  "source": "{publisher}",
  "source_url": "{source_url}",
  "headline": "{headline}"
}}

Rules:
- Return is_ma_deal false for satire, sports trades, market overview articles, stock analysis, debt financing, government weapons purchases, or articles without a specific acquirer and target.
- If this is only an industry trend article, return is_ma_deal false.
- If the article describes a rejected takeover bid, keep it as an M&A deal and set deal_status to "Rejected".
- If the article describes a rumored or potential transaction, keep it as an M&A deal and set deal_status to "Rumored" or "Pending".
- If the value is in millions, convert value_billions correctly. Example: $800M = 0.8.
- If value is not disclosed, use null.
- Do not infer unsupported facts.
- Return only JSON. No markdown. No explanation.
"""

    try:
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=700,
            temperature=0,
            messages=[{"role": "user", "content": prompt}]
        )

        response_text = clean_json_response(message.content[0].text)
        return json.loads(response_text)

    except Exception as e:
        print(f"  Extraction error: {e}")
        return None


def is_duplicate_deal(deal, existing_deals):
    acquirer = normalize_company_name(deal.get("acquirer"))
    target = normalize_company_name(deal.get("target"))

    if not acquirer or not target:
        return False

    for existing in existing_deals:
        existing_acquirer = normalize_company_name(existing.get("acquirer"))
        existing_target = normalize_company_name(existing.get("target"))

        if acquirer == existing_acquirer and target == existing_target:
            return True

    return False


def deal_sort_key(deal):
    try:
        value_score = float(deal.get("value_billions") or 0)
    except (ValueError, TypeError):
        value_score = 0

    status_score = {
        "Announced": 5,
        "Completed": 4,
        "Pending": 3,
        "Rejected": 2,
        "Rumored": 1,
        "Other": 0
    }.get(deal.get("deal_status", ""), 0)

    return (value_score, status_score)


print("Loading filtered articles...")

with open(INPUT_FILE, "r") as f:
    articles = json.load(f)

print(f"Articles queued for Claude: {len(articles)}")
print(f"Estimated cost: ~${len(articles) * 0.01:.2f}\n")

deals = []

for i, article in enumerate(articles, start=1):
    print(f"Processing {i}/{len(articles)}: {article.get('headline', '')[:80]}...")

    deal = extract_deal(article)

    if deal is None:
        print("  → Skipped: extraction failed")
        continue

    if not deal.get("is_ma_deal"):
        print("  → Skipped: not an M&A deal")
        continue

    if not deal.get("acquirer") or not deal.get("target"):
        print("  → Skipped: missing acquirer or target")
        continue

    if is_duplicate_deal(deal, deals):
        print("  → Skipped: duplicate deal")
        continue

    deals.append(deal)

    print(
        f"  ✓ {deal.get('acquirer')} → {deal.get('target')} "
        f"({deal.get('value', 'Value unknown')}, {deal.get('deal_status')})"
    )

print(f"\nValid unique deals extracted: {len(deals)}")

sorted_deals = sorted(deals, key=deal_sort_key, reverse=True)
top_deals = sorted_deals[:MAX_FINAL_DEALS]

with open(OUTPUT_FILE, "w") as f:
    json.dump(top_deals, f, indent=2)

print(f"\nTop {len(top_deals)} deals saved to {OUTPUT_FILE}:")
for deal in top_deals:
    print(
        f"  • {deal.get('acquirer')} → {deal.get('target')} "
        f"— {deal.get('value', 'Value unknown')} "
        f"({deal.get('sector')})"
    )

print("\nDone! deals.json updated.")