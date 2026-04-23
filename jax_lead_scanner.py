import os
import json
import time
import hashlib
import logging
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from typing import Optional

import requests
import praw
import anthropic
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("leadforge.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("LeadForge")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
REDDIT_CLIENT_ID  = os.getenv("REDDIT_CLIENT_ID")
REDDIT_SECRET     = os.getenv("REDDIT_SECRET")
DATABASE_URL      = os.getenv("DATABASE_URL")
SERP_API_KEY      = os.getenv("SERP_API_KEY")

GARAGE_KEYWORDS = [
    "garage door", "garage spring", "garage opener", "garage panel",
    "broken garage", "garage door broke", "garage door stuck",
    "torsion spring", "garage cable", "garage track", "overhead door",
    "garage door install", "new garage door",
]

@dataclass
class RawSignal:
    source: str
    raw_text: str
    url: str
    location_hint: str
    signal_id: str
    scraped_at: str

@dataclass
class Lead:
    source: str
    raw_text: str
    url: str
    name: Optional[str]
    phone: Optional[str]
    email: Optional[str]
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
    text_lower = text.lower()
    return any(kw in text_lower for kw in GARAGE_KEYWORDS)

def enrich_signal(signal: RawSignal) -> Optional[Lead]:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = f"""
You are a lead qualification AI for a garage door company in Jacksonville, FL.
Analyze this raw signal and extract structured lead information.

SOURCE: {signal.source}
URL: {signal.url}
TEXT:
{signal.raw_text[:2000]}

Return ONLY a valid JSON object with these exact keys:
{{
  "name": "person's name if identifiable, else null",
  "phone": "phone number if present, else null",
  "email": "email if present, else null",
  "address": "street address or neighborhood in Jacksonville if mentioned, else null",
  "signal_summary": "1 sentence: what is the garage door problem or need",
  "urgency": "high | medium | low",
  "score": integer 1-10,
  "estimated_value": "estimated job value like $250-$400 based on the problem, or null",
  "is_jacksonville_lead": true or false,
  "disqualify_reason": "reason if not a real lead, else null"
}}
Return ONLY the JSON. No explanation.
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

    if not data.get("is_jacksonville_lead"):
        return None
    if data.get("disqualify_reason"):
        return None
    score = int(data.get("score", 0))
    if score < 5:
        return None

    return Lead(
        source=signal.source,
        raw_text=signal.raw_text[:500],
        url=signal.url,
        name=data.get("name"),
        phone=data.get("phone"),
        email=data.get("email"),
        address=data.get("address"),
        signal_summary=data.get("signal_summary", ""),
        urgency=data.get("urgency", "medium"),
        score=score,
        estimated_value=data.get("estimated_value"),
        status="new",
        created_at=now(),
    )

def scan_reddit():
    log.info("Reddit Scanner starting...")
    reddit = praw.Reddit(
        client_id=REDDIT_CLIENT_ID,
        client_secret=REDDIT_SECRET,
        user_agent="LeadForge/1.0"
    )
    leads = []
    seen = set()

    JAX_KEYWORDS = [
        "garage door Jacksonville",
        "garage door repair Jacksonville FL",
        "garage door broken jacksonville",
    ]

    for keyword in JAX_KEYWORDS:
        try:
            results = reddit.subreddit("all").search(keyword, sort="new", time_filter="day", limit=25)
            for post in results:
                text = f"{post.title} {post.selftext}"
                if not is_garage_related(text):
                    continue
                signal_id = make_id("reddit", post.id)
                if signal_id in seen:
                    continue
                seen.add(signal_id)
                signal = RawSignal(
                    source="reddit",
                    raw_text=text,
                    url=f"https://reddit.com{post.permalink}",
                    location_hint="jacksonville",
                    signal_id=signal_id,
                    scraped_at=now(),
                )
                lead = enrich_signal(signal)
                if lead:
                    leads.append(lead)
                    log.info(f"Lead found: score {lead.score}/10 — {lead.signal_summary[:60]}")
                time.sleep(1.5)
        except Exception as e:
            log.warning(f"Reddit error: {e}")

    return leads

def run_all_agents():
    log.info("LeadForge Jacksonville — Starting")
    all_leads = []
    all_leads.extend(scan_reddit())
    log.info(f"Run complete — {len(all_leads)} leads found")

    for lead in all_leads:
        log.info(f"LEAD | score:{lead.score} | {lead.signal_summary} | {lead.url}")

    return len(all_leads)

if __name__ == "__main__":
    run_all_agents()






