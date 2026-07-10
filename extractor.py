import anthropic
import json
import os
import re
import time
import threading
from dotenv import load_dotenv
#imports libraries, including anthropic for interacting with Claude API, re to remove HTML from RSS summaries, and more

INPUT_FILE = "data/filtered_articles.json"
OUTPUT_FILE = "data/deals.json"

MAX_FINAL_DEALS = 5 #only top 5 deals are kept
MAX_ARTICLES_SENT = 12 #only 12 articles sent
MAX_SUMMARY_CHARS = 700 #only 700 characters of summary sent
MAX_TOKENS = 6000

load_dotenv()
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
#Reads .env file to get API key and initializes the Claude client with it.

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
#filters out deals that have unknown acquirers

def rank_score(deal):
    try:
        value = float(deal.get("value_billions") or 0)
    except Exception:
        value = 0

    mentions = int(deal.get("mention_count") or 1)

    return (mentions * 3) + value
#ranks deals based on mention count and deal value

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
#before sending to Claude, function builds a packet with with only headline, summary, date, mention count, source list, and source URL. 

def spinner(stop_event):
    while not stop_event.is_set():
        print("Claude is analyzing deals...", end="\r")
        time.sleep(1)
#supposedly runs a spinner when Claude is processing although it doesn't seem to be working correctly


print("Loading filtered articles...")

with open(INPUT_FILE, "r") as f:
    articles = json.load(f)

articles = articles[:MAX_ARTICLES_SENT]
#loads articles into memory and limits to 12

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
7. Return 5 valid deals.

Important:
- Do not invent missing facts.
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
#builds a prompt that tells Claude to analyze the compact packets and return a JSON with only valid deals, excluding duplicates, weak deals, and rumors

Article packets:
{json.dumps(packets, indent=2)}
"""
#This embeds compact packets into the prompt


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
    #Calls Claude API and waits for a response, chooses model and temperature, which controls randomness of output

    stop_event.set() #a spinner is used to indicate that Claude is processing the request, and it is stopped once a response is received.
    thread.join()

    print("\nClaude response received. Parsing JSON...")

    response_text = clean_json_response(message.content[0].text)
    #this cleans the response text to remove any code block formatting and whitespace, preparing it for JSON parsing.

    with open("data/claude_response.txt", "w") as f:
        f.write(response_text)
    #saves the raw response from Claude to a text file for debugging or record-keeping purposes.

    result = json.loads(response_text)
    deals = result.get("deals", [])
    #converts cleaned response into a Python dictionary

except Exception as e:
    stop_event.set()
    thread.join()
    print(f"\nClaude extraction error: {e}")
    deals = []
    #If error occurs during call, error message is printed and deals list is set to empty.


clean_deals = [] #only holds valid deals that pass the is_bad_extracted_deal filter

for deal in deals:
    if is_bad_extracted_deal(deal):
        print(f"Skipped vague deal: {deal.get('acquirer')} → {deal.get('target')}")
        continue
#loops through all returned deals and filters out bad and vauge deals

    deal["final_score"] = rank_score(deal)
    clean_deals.append(deal)
    #Computes a final score out of 100 for each valid deal based on mention count and deal value

clean_deals = sorted(
    clean_deals,
    key=lambda x: x.get("final_score", 0),
    reverse=True
) #deals sorted by final score in descending order, so that the highest-scoring deals appear first.

top_deals = clean_deals[:MAX_FINAL_DEALS]
#keeps top 5 deals

with open(OUTPUT_FILE, "w") as f:
    json.dump(top_deals, f, indent=2)
    #writes top deals to JSON file

print(f"\nSaved {len(top_deals)} deals to {OUTPUT_FILE}")
#Prints the number of deals saved to the output file

for deal in top_deals:
    print(
        f"• {deal.get('acquirer')} → {deal.get('target')} "
        f"— {deal.get('value')} "
        f"[x{deal.get('mention_count', 1)}] "
        f"[score {deal.get('final_score')}]"
    )
#For each of the top deals, it prints a summary line in terminal