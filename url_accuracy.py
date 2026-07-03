import anthropic
import os
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# ─── PICK A REAL ARTICLE URL TO TEST ─────────────────────────────
# Use a real, current, non-paywalled article you can verify by eye
TEST_URL =  "https://news.google.com/rss/articles/CBMinAFBVV95cUxQeEpNTWYtSjJCSV9vTjBvX1JMeHBOdU1Ea2U2N0NSa193NUhCS21DVkV3UGtPVXltZEFSUFpTWlNFVlRKVTlaMEVONTNuOTc3UjljVXduRWtRNTBGNXlONTRSY0N2dGdDLUZsY2hDcWtwZzRXTlpXMW5xbzdfV0pMejRKa1d1Tlh2VUNtQW04NU54V2VVTVlfTGJQT3DSAa4BQVVfeXFMUHcwUzg0bHhITk5WemZDVzBKV1hEWUE4TUtPWkhDX2Q0ZUFvQ2lCd2phR1JfTVZTbngyX2owS1dqLVFZbkxVdkxNRVV0dlk3ZW93QnZKb0NEdkFUenlPclZUUlFTbGgzQ1VwNURzcFRVSGEwNjd0aENVMFd5TXNrUFJBLWU3Qm1naFBlalU5VHg1RkRHYXJpR2JHSEVfQ3RJdG9aeE1vSmNjSk12RHl3?oc=5"

TEST_HEADLINE = "Greenwich-Based Company Completes $17 Billion Acquisition"


def get_article_text(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers, timeout=10)
    soup = BeautifulSoup(response.content, "html.parser")
    paragraphs = soup.find_all("p")
    text = " ".join([p.get_text(" ", strip=True) for p in paragraphs])
    return text


print("Fetching article text...")
article_text = get_article_text(TEST_URL)

print(f"\n{'='*70}")
print("RAW ARTICLE TEXT (first 1000 chars) — READ THIS YOURSELF FIRST:")
print(f"{'='*70}")
print(article_text[:1000])
print(f"{'='*70}\n")

input("Press Enter after you've read the article text above and noted the real facts...")

prompt = f"""
You are an M&A analyst. Extract deal information from this article.

Headline: {TEST_HEADLINE}

Article text:
{article_text[:3000]}

Return ONLY valid JSON:
{{
  "acquirer": "string or null",
  "target": "string or null",
  "value": "string or null",
  "sector": "string",
  "geography": "string or null",
  "date": "YYYY-MM-DD or null",
  "rationale": "one sentence or null",
  "key_risk": "one sentence or null",
  "confidence_note": "explain what in the article text supports each fact you extracted, or note if you are uncertain about any field"
}}

Rules:
- Do NOT invent facts not present in the article text
- If something is unclear or absent, use null and say so in confidence_note
- Return ONLY JSON, no markdown
"""

print("\nSending to Claude...\n")

message = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=800,
    temperature=0,
    messages=[{"role": "user", "content": prompt}]
)

result = message.content[0].text.strip()
result = result.replace("```json", "").replace("```", "").strip()

print(f"{'='*70}")
print("CLAUDE'S EXTRACTION:")
print(f"{'='*70}")
print(result)
print(f"{'='*70}\n")

print("NOW COMPARE:")
print("1. Does the acquirer/target match what you read?")
print("2. Does the deal value match?")
print("3. Does the rationale reflect what the article actually said,")
print("   or does it sound like generic filler?")
print("4. Check the confidence_note — does it point to real text,")
print("   or does it sound like it's guessing?")