import anthropic
import json
import os
import re
import time
import threading
from dotenv import load_dotenv

INPUT_FILE = "data/filtered_articles.json"
OUTPUT_FILE = "data/deals.json"

MAX_FINAL_DEALS = 5
MAX_ARTICLES_SENT = 12
MAX_SUMMARY_CHARS = 700
MAX_TOKENS = 3500

load_dotenv()
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def clean_json_response(text):
    return text.replace("```json", "").replace("```", "").strip()


def is_bad_extracted_deal(deal):
    bad_values = ["unspecified", "unknown", "n/a", "not specified", ""]

    acquirer = str(deal.get("acquirer", "")).lower().strip()
    target = str(deal.get("target", "")).lower().strip()

    if acquirer in bad_values or target in bad_values:
        return True

    if not deal.get("acquirer") or not deal.get("target"):
        return True

    return False


def rank_score(deal):
    try:
        value = float(deal.get("value_billions") or 0)
    except Exception:
        value = 0

    mentions = int(deal.get("mention_count") or 1)

    return (mentions * 3) + value


def build_compact_packet(article):
    summary = article.get("text", "") or ""
    summary = re.sub(r"<.*?>", " ", summary)
    summary = summary[:MAX_SUMMARY_CHARS]

    return {
        "headline": article.get("headline", ""),
        "headline_variants": article.get("headline_variants", [])[:4],
        "summary": summary,
        "date": article.get("date", ""),
        "mention_count": article.get("mention_count", 1),
        "source_list": article.get("source_list", []),
        "source_url": article.get("url", "")
    }


def spinner(stop_event):
    while not stop_event.is_set():
        print("Claude is analyzing deals...", end="\r")
        time.sleep(1)


print("Loading filtered articles...")

with open(INPUT_FILE, "r") as f:
    articles = json.load(f)

articles = articles[:MAX_ARTICLES_SENT]

print(f"Loaded {len(articles)} articles for Claude")

packets = [build_compact_packet(article) for article in articles]

print("\nSending compact deal packets to Claude...")
print("This should be faster than sending full article text.\n")

prompt = f"""
You are an M&A analyst creating a daily M&A dashboard.

You will receive compact article packets. Each packet likely represents one M&A deal group.

Your job:
1. Identify valid unique M&A deals.
2. Remove duplicate stories.
3. Exclude weak or unclear deals.
4. Exclude old deal updates, regulatory-only updates, rumors, rejected bids, speculation, and articles about deals merely "in talks" or "nearing" completion.
5. Include only confirmed deals that are announced, signed, or completed.
6. Do NOT include any deal if acquirer or target is unspecified, unknown, unclear, or missing.
7. Return up to 8 valid deals. Python will rank the final top 5.

Important:
- Do not include deals with "unspecified target" or "unspecified acquirer."
- Do not include vague headlines where the actual target cannot be identified.
- Do not invent missing facts.
- If value is missing, use null.
- Return ONLY valid JSON.

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
      "why_it_matters": "one concise sentence",
      "mention_count": number,
      "source_list": ["source 1", "source 2"],
      "source_url": "string",
      "headline": "string"
    }}
  ]
}}

Article packets:
{json.dumps(packets, indent=2)}
"""

stop_event = threading.Event()
thread = threading.Thread(target=spinner, args=(stop_event,))
thread.start()

try:
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=MAX_TOKENS,
        temperature=0,
        messages=[{"role": "user", "content": prompt}]
    )

    stop_event.set()
    thread.join()

    print("\nClaude response received. Parsing JSON...")

    response_text = clean_json_response(message.content[0].text)

    with open("data/claude_response.txt", "w") as f:
        f.write(response_text)

    result = json.loads(response_text)
    deals = result.get("deals", [])

except Exception as e:
    stop_event.set()
    thread.join()
    print(f"\nClaude extraction error: {e}")
    deals = []


clean_deals = []

for deal in deals:
    if is_bad_extracted_deal(deal):
        print(f"Skipped vague deal: {deal.get('acquirer')} → {deal.get('target')}")
        continue

    deal["final_score"] = rank_score(deal)
    clean_deals.append(deal)

clean_deals = sorted(
    clean_deals,
    key=lambda x: x.get("final_score", 0),
    reverse=True
)

top_deals = clean_deals[:MAX_FINAL_DEALS]

with open(OUTPUT_FILE, "w") as f:
    json.dump(top_deals, f, indent=2)

print(f"\nSaved {len(top_deals)} deals to {OUTPUT_FILE}")

for deal in top_deals:
    print(
        f"• {deal.get('acquirer')} → {deal.get('target')} "
        f"— {deal.get('value')} "
        f"[x{deal.get('mention_count', 1)}] "
        f"[score {deal.get('final_score')}]"
    )

print("\nDone! deals.json updated.")