import anthropic
import json
import os
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# -----------------------------
# Configuration
# -----------------------------

INPUT_FILE = "data/filtered_articles.json"
OUTPUT_FILE = "data/deals.json"
MAX_FINAL_DEALS = 5
MAX_ARTICLE_CHARS = 2000
MAX_URLS_PER_DEAL = 4

# -----------------------------
# Initialize Claude
# -----------------------------

load_dotenv()
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


# -----------------------------
# Get article text
# -----------------------------

def get_article_text(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10)

        soup = BeautifulSoup(response.content, "html.parser")
        paragraphs = soup.find_all("p")
        text = " ".join([p.get_text(" ", strip=True) for p in paragraphs])

        bad_signals = [
            "subscribe", "sign in", "log in", "enable javascript",
            "access denied", "cookies", "paywall", "create an account"
        ]

        if len(text) < 300:
            return ""

        if any(signal in text.lower() for signal in bad_signals):
            return ""

        return text[:MAX_ARTICLE_CHARS]

    except Exception:
        return ""


def build_deal_packet(article):
    headline = article.get("headline", "")
    rss_summary = article.get("text", "")
    url_variants = article.get("url_variants", [article.get("url", "")])
    headline_variants = article.get("headline_variants", [headline])

    accessible_texts = []

    for url in url_variants[:MAX_URLS_PER_DEAL]:
        text = get_article_text(url)

        if text:
            accessible_texts.append({
                "url": url,
                "text": text
            })

    if accessible_texts:
        content_source = "scraped_webpage"
        content = accessible_texts
    else:
        content_source = "rss_summary_fallback"
        combined_summary = "\n\n".join([
            f"Headline: {h}" for h in headline_variants
        ])

        if rss_summary:
            combined_summary += f"\n\nRSS Summary: {rss_summary}"

        content = [{
            "url": article.get("url", ""),
            "text": combined_summary
        }]

    return {
        "headline": headline,
        "headline_variants": headline_variants,
        "publisher": article.get("publisher", article.get("source", "")),
        "source_list": article.get("source_list", []),
        "date": article.get("date", ""),
        "mention_count": article.get("mention_count", 1),
        "url_variants": url_variants,
        "content_source": content_source,
        "content": content
    }


def clean_json_response(text):
    return text.replace("```json", "").replace("```", "").strip()


# -----------------------------
# Load filtered articles
# -----------------------------

print("Loading filtered articles...")

with open(INPUT_FILE, "r") as f:
    articles = json.load(f)

print(f"Loaded {len(articles)} filtered articles")


# -----------------------------
# Visit URLs and build packets
# -----------------------------

print("\nVisiting URLs and collecting accessible text...")

deal_packets = []

for i, article in enumerate(articles, start=1):
    print(f"{i:2}. {article.get('headline', '')[:85]}")

    packet = build_deal_packet(article)
    deal_packets.append(packet)

    if packet["content_source"] == "scraped_webpage":
        print("    ✓ Used scraped webpage text")
    else:
        print("    → Used RSS summary fallback")


# -----------------------------
# Claude extraction
# -----------------------------

prompt = f"""
You are an M&A analyst creating a daily M&A dashboard.

You will receive article packets. Each packet should already represent one likely deal group, but there may still be duplicates.

Your task:
1. Identify unique M&A deals.
2. Remove duplicate stories about the same deal.
3. Exclude old deal updates, regulatory-only updates, rumors, rejected bids, speculation, and articles about deals merely "in talks" or "nearing" completion.
4. Include only finalized/confirmed deals that are announced, signed, or completed.
5. Return the 5 largest valid deals by deal value.

Important rules:
- Include only deals that are announced, signed, or completed.
- Exclude rejected bids.
- Exclude rumored deals.
- Exclude speculative articles.
- Exclude regulatory updates about older deals unless the article says the deal was newly announced, signed, or completed in the current article.
- Exclude market commentary or industry trend articles.
- Do not invent facts.
- If a value is not disclosed, use null.
- If no valid deals exist, return {{"deals": []}}.
- Return ONLY valid JSON. No markdown. No explanation.

Return this exact JSON structure:

{{
  "deals": [
    {{
      "acquirer": "string",
      "target": "string",
      "value": "string or null",
      "value_billions": number or null,
      "sector": "Tech, Healthcare, Energy, Finance, Media, Retail, Industrial, Consumer, Real Estate, Other",
      "geography": "string or null",
      "date": "YYYY-MM-DD or null",
      "deal_status": "Announced, Signed, or Completed",
      "rationale": "one concise sentence",
      "key_risk": "one concise sentence",
      "why_it_matters": "one concise sentence for finance/consulting readers",
      "mention_count": number,
      "source_list": ["source 1", "source 2"],
      "source_url": "best source URL",
      "headline": "best headline"
    }}
  ]
}}

Article packets:
{json.dumps(deal_packets, indent=2)}
"""

print("\nSending all deal packets to Claude in one call...")

try:
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=6000,
        temperature=0,
        messages=[{"role": "user", "content": prompt}]
    )

    response_text = clean_json_response(message.content[0].text)

    with open("data/claude_response.txt", "w") as f:
        f.write(response_text)

    result = json.loads(response_text)
    deals = result.get("deals", [])

except Exception as e:
    print(f"Claude extraction error: {e}")
    deals = []


# -----------------------------
# Final sort and save
# -----------------------------

def value_sort_key(deal):
    try:
        return float(deal.get("value_billions") or 0)
    except Exception:
        return 0


deals = sorted(deals, key=value_sort_key, reverse=True)
top_deals = deals[:MAX_FINAL_DEALS]

with open(OUTPUT_FILE, "w") as f:
    json.dump(top_deals, f, indent=2)

print(f"\nSaved {len(top_deals)} deals to {OUTPUT_FILE}")

for deal in top_deals:
    print(
        f"• {deal.get('acquirer')} → {deal.get('target')} "
        f"— {deal.get('value')} "
        f"[x{deal.get('mention_count', 1)}]"
    )

print("\nDone! deals.json updated.")