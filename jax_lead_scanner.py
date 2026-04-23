import os
import json
import time
import hashlib
import logging
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from typing import Optional

import requests
import anthropic
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("LeadForge")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

GARAGE_KEYWORDS = [
    "garage door", "garage spring", "garage opener",
    "broken garage", "garage door broke", "garage door stuck",
    "torsion spring", "garage cable", "overhead door",
    "garage door install", "new garage door",
]

CRAIGSLIST_URLS = [
    "https://jacksonville.craigslist.org/search/jacksonville/sss?query=garage+door&sort=date",
    "https://jacksonville.craigslist.org/search/jacksonville/sss?query=garage+door+repair&sort=date",
    "https://jacksonville.craigslist.org/search/jacksonville/hhh?query=garage+door&sort=date",
]

@dataclass
class Lead:
    source: str
    raw_text: str
    url: str
    name: Optional[str]
    phone: Optional[str]
    address: Optional[str]
    signal_summary: str
    urgency: str
    score: int
    estimated_value: Optional[str]
    status: str
    created_at: str

def now() -> str:
    return datetime.now(timezone.utc).isoformat()

def make_id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]

def is_garage_related(text: str) -> bool:
    return any(kw in text.lower() for kw in GARAGE_KEYWORDS)

def enrich_signal(text: str, url: str, source: str) -> Optional[Lead]:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = f"""
You are a lead qualification AI for a garage door company in Jacksonville, FL.
Analyze this and extract lead information.

SOURCE: {source}
URL: {url}
TEXT: {text[:2000]}

Return ONLY a valid JSON object:
{{
  "name": "person name or null",
  "phone": "phone number or null",
  "address": "address or neighborhood or null",
  "signal_summary": "one sentence describing the need",
  "urgency": "high | medium | low",
  "score": integer 1-10,
  "estimated_value": "job value like $250-$400 or null",
  "is_valid_lead": true or false,
  "disqualify_reason": "reason or null"
}}
Return ONLY JSON. No explanation.
"""
    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw.strip())
    except Exception as e:
        log.warning(f"Claude enrichment failed: {e}")
        return None

    if not data.get("is_valid_lead"):
        return None
    if data.get("disqualify_reason"):
        return None
    score = int(data.get("score", 0))
    if score < 5:
        return None

    return Lead(
        source=source,
        raw_text=text[:500],
        url=url,
        name=data.get("name"),
        phone=data.get("phone"),
        address=data.get("address"),
        signal_summary=data.get("signal_summary", ""),
        urgency=data.get("urgency", "medium"),
        score=score,
        estimated_value=data.get("estimated_value"),
        status="new",
        created_at=now(),
    )

def scan_craigslist():
    log.info("Craigslist Scanner starting...")
    leads = []
    seen = set()

    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15"
    }

    for url in CRAIGSLIST_URLS:
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code != 200:
                log.warning(f"Craigslist returned {resp.status_code}")
                continue

            from html.parser import HTMLParser

            class ListingParser(HTMLParser):
                def __init__(self):
                    super().__init__()
                    self.listings = []
                    self.current_link = None
                    self.capture = False

                def handle_starttag(self, tag, attrs):
                    attrs = dict(attrs)
                    if tag == "a" and "href" in attrs and "cl-app-anchor" in attrs.get("class", ""):
                        self.current_link = attrs["href"]
                        self.capture = True

                def handle_data(self, data):
                    if self.capture and data.strip():
                        self.listings.append((data.strip(), self.current_link))
                        self.capture = False

            parser = ListingParser()
            parser.feed(resp.text)

            for title, link in parser.listings:
                if not is_garage_related(title):
                    continue
                signal_id = make_id("craigslist", link or title)
                if signal_id in seen:
                    continue
                seen.add(signal_id)

                full_text = title
                if link:
                    try:
                        detail = requests.get(link, headers=headers, timeout=10)
                        if detail.status_code == 200:
                            full_text = detail.text[:3000]
                        time.sleep(1)
                    except:
                        pass

                lead = enrich_signal(full_text, link or url, "craigslist_jacksonville")
                if lead:
                    leads.append(lead)
                    log.info(f"LEAD | score:{lead.score}/10 | {lead.signal_summary}")

                time.sleep(1)

        except Exception as e:
            log.warning(f"Craigslist scan error: {e}")

    log.info(f"Craigslist scan done — {len(leads)} leads found")
    return leads

def run_all_agents():
    log.info("LeadForge Jacksonville — Starting")
    all_leads = []
    all_leads.extend(scan_craigslist())
    log.info(f"Run complete — {len(all_leads)} leads found")
    for lead in all_leads:
        log.info(f"LEAD | score:{lead.score} | {lead.signal_summary} | {lead.url}")
    return len(all_leads)

if __name__ == "__main__":
    run_all_agents()

