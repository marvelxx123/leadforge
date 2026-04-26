# “””
LeadForge Jacksonville - Full Multi-Agent System

5 Agents working together:

AGENT 1 - SCOUT      : Finds raw signals from multiple sources
AGENT 2 - BRAIN      : Claude analyzes, scores, qualifies each lead
AGENT 3 - MEMORY     : Remembers everything, learns what works
AGENT 4 - CONTACT    : Enriches leads with contact info
AGENT 5 - ALERT      : SMS you instantly on hot leads

Sources:

- Duval County Building Permits (public data, never blocks)
- Google Maps competitor reviews (unhappy customers)
- Local news storm damage (emergency leads)
- Google search signals
  “””

import os
import json
import time
import hashlib
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from typing import Optional, List, Tuple

import requests
import anthropic
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
level=logging.INFO,
format=”%(asctime)s [%(levelname)s] %(message)s”
)
log = logging.getLogger(“LeadForge”)

ANTHROPIC_API_KEY  = os.getenv(“ANTHROPIC_API_KEY”)
TWILIO_ACCOUNT_SID = os.getenv(“TWILIO_ACCOUNT_SID”)
TWILIO_AUTH_TOKEN  = os.getenv(“TWILIO_AUTH_TOKEN”)
TWILIO_FROM_NUMBER = os.getenv(“TWILIO_FROM_NUMBER”)
TWILIO_TO_NUMBER   = os.getenv(“TWILIO_TO_NUMBER”)
SERP_API_KEY       = os.getenv(“SERP_API_KEY”)
MEMORY_FILE        = “leadforge_memory.json”

# – Data Models ———————————————–

@dataclass
class Signal:
source: str
raw_text: str
url: str
signal_id: str
scraped_at: str

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
job_type: Optional[str]
status: str
created_at: str

def now() -> str:
return datetime.now(timezone.utc).isoformat()

def make_id(*parts: str) -> str:
return hashlib.sha256(”|”.join(parts).encode()).hexdigest()[:16]

# ================================================================

# AGENT 3 - MEMORY

# ================================================================

class MemoryAgent:
def **init**(self):
self.data = self._load()

```
def _load(self) -> dict:
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return {
        "seen_signals": [],
        "total_leads": 0,
        "leads_by_source": {},
        "run_count": 0,
        "last_run": None,
    }

def _save(self):
    with open(MEMORY_FILE, "w") as f:
        json.dump(self.data, f, indent=2)

def has_seen(self, signal_id: str) -> bool:
    return signal_id in self.data["seen_signals"]

def mark_seen(self, signal_id: str):
    if signal_id not in self.data["seen_signals"]:
        self.data["seen_signals"].append(signal_id)
        if len(self.data["seen_signals"]) > 5000:
            self.data["seen_signals"] = self.data["seen_signals"][-5000:]
    self._save()

def record_lead(self, lead: Lead):
    self.data["total_leads"] += 1
    source = lead.source
    self.data["leads_by_source"][source] = \
        self.data["leads_by_source"].get(source, 0) + 1
    self._save()

def record_run(self, leads_found: int):
    self.data["run_count"] += 1
    self.data["last_run"] = now()
    self._save()

def get_stats(self) -> dict:
    return {
        "total_leads": self.data["total_leads"],
        "total_runs": self.data["run_count"],
        "by_source": self.data["leads_by_source"],
        "last_run": self.data["last_run"],
    }

def get_best_sources(self) -> List[str]:
    sources = self.data["leads_by_source"]
    return sorted(sources, key=lambda x: sources[x], reverse=True) \
        if sources else []
```

# ================================================================

# AGENT 5 - ALERT (SMS)

# ================================================================

class AlertAgent:
def **init**(self):
self.enabled = False
if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
try:
from twilio.rest import Client
self.client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
self.enabled = True
log.info(“Alert Agent: SMS enabled “)
except ImportError:
log.warning(“Alert Agent: twilio package not installed”)
else:
log.warning(“Alert Agent: Twilio keys not set”)

```
def send_sms(self, to: str, message: str):
    if not self.enabled:
        log.info(f"[SMS DISABLED] Would send to {to}: {message[:80]}")
        return
    try:
        msg = self.client.messages.create(
            body=message,
            from_=TWILIO_FROM_NUMBER,
            to=to
        )
        log.info(f"SMS sent  sid:{msg.sid}")
    except Exception as e:
        log.error(f"SMS failed: {e}")

def alert_hot_lead(self, lead: Lead):
    emoji = "" if lead.score >= 9 else ""
    msg = (
        f"{emoji} HOT LEAD {lead.score}/10\n"
        f"Job: {lead.signal_summary}\n"
        f"Type: {lead.job_type or 'unknown'}\n"
        f"Value: {lead.estimated_value or 'TBD'}\n"
        f"Address: {lead.address or 'Jacksonville FL'}\n"
        f"Phone: {lead.phone or 'not found'}\n"
        f"Source: {lead.source}\n"
        f"URL: {(lead.url or '')[:60]}"
    )
    self.send_sms(TWILIO_TO_NUMBER, msg)

def alert_contractor(self, lead: Lead, contractor_number: str):
    msg = (
        f"New Garage Door Lead - Jacksonville\n"
        f"Job: {lead.signal_summary}\n"
        f"Value: {lead.estimated_value or 'TBD'}\n"
        f"Address: {lead.address or 'Jacksonville FL'}\n"
        f"Phone: {lead.phone or 'check URL'}\n"
        f"LeadForge"
    )
    self.send_sms(contractor_number, msg)

def send_daily_summary(self, stats: dict, leads_today: int):
    msg = (
        f"LeadForge Daily Summary\n"
        f"Today: {leads_today} leads\n"
        f"All time: {stats['total_leads']} leads\n"
        f"Runs: {stats['total_runs']}\n"
        f"Top source: {list(stats['by_source'].keys())[0] if stats['by_source'] else 'none'}"
    )
    self.send_sms(TWILIO_TO_NUMBER, msg)
```

# ================================================================

# AGENT 2 - BRAIN (Claude)

# ================================================================

class BrainAgent:
def **init**(self, memory: MemoryAgent):
self.client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
self.memory = memory

```
def analyze(self, signal: Signal) -> Optional[Tuple[Lead, str]]:
    stats = self.memory.get_stats()
    best = self.memory.get_best_sources()[:3]

    prompt = f"""
```

You are the AI brain of LeadForge - a garage door lead generation
system in Jacksonville, Florida.

Analyze this signal. Determine if it’s a real, high-quality
garage door lead worth acting on.

SYSTEM MEMORY:

- Total leads found so far: {stats[‘total_leads’]}
- Best sources so far: {best if best else ‘still learning’}
- Run #{stats[‘total_runs’]}

SIGNAL:
Source: {signal.source}
URL: {signal.url}
Text: {signal.raw_text[:3000]}

THINK ABOUT:

1. Is this person in Jacksonville / Duval County FL area?
1. Do they need garage door service urgently or soon?
1. What specific job? (spring, opener, new door, cable, panel)
1. Job value estimate?
1. Any contact info present?
1. Real homeowner or business/spam/irrelevant?

SCORE GUIDE:
10 = urgent repair + Jacksonville confirmed + contact info
9  = urgent repair + Jacksonville confirmed
8  = planned install/replacement + high value + Jacksonville
7  = strong intent + likely Jacksonville
6  = possible lead, needs verification
5  = weak signals, might be Jacksonville
1-4 = disqualify

Return ONLY valid JSON - no markdown, no explanation:
{{
“name”: “full name or null”,
“phone”: “phone with area code or null”,
“address”: “address or neighborhood in Jacksonville or null”,
“signal_summary”: “one sentence describing exactly what they need”,
“urgency”: “high | medium | low”,
“score”: integer 1-10,
“estimated_value”: “realistic range like $350-$500”,
“job_type”: “spring repair | opener install | new door | cable repair | panel repair | general repair | unknown”,
“is_jacksonville_lead”: true or false,
“disqualify_reason”: “reason or null”,
“action”: “alert_now | save | discard”
}}

action: alert_now if score>=8 and is_jacksonville_lead,
save if score 5-7,
discard otherwise
“””

```
    try:
        response = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw.strip())

    except Exception as e:
        log.warning(f"Brain failed: {e}")
        return None

    if not data.get("is_jacksonville_lead"):
        return None
    if data.get("disqualify_reason"):
        log.debug(f"Disqualified: {data['disqualify_reason']}")
        return None

    score = int(data.get("score", 0))
    if score < 5:
        return None

    lead = Lead(
        source=signal.source,
        raw_text=signal.raw_text[:500],
        url=signal.url,
        name=data.get("name"),
        phone=data.get("phone"),
        address=data.get("address"),
        signal_summary=data.get("signal_summary", ""),
        urgency=data.get("urgency", "medium"),
        score=score,
        estimated_value=data.get("estimated_value"),
        job_type=data.get("job_type"),
        status="new",
        created_at=now(),
    )

    log.info(
        f"LEAD | {score}/10 | {lead.job_type} | "
        f"{lead.urgency} | {lead.signal_summary[:50]}"
    )
    return lead, data.get("action", "save")
```

# ================================================================

# AGENT 1 - SCOUT

# ================================================================

class ScoutAgent:
def **init**(self, memory: MemoryAgent):
self.memory = memory
self.headers = {
“User-Agent”: “Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)”
}

```
def scan_permits(self) -> List[Signal]:
    log.info("Scout: Permits...")
    signals = []
    try:
        url = "https://data.coj.net/resource/permits.json"
        params = {
            "$limit": 50,
            "$order": "issued_date DESC",
            "$q": "garage door",
        }
        resp = requests.get(
            url, params=params, headers=self.headers, timeout=15)
        if resp.status_code == 200:
            for permit in resp.json():
                address = (permit.get("site_address") or
                           permit.get("address") or "Jacksonville FL")
                permit_no = str(
                    permit.get("permit_number") or
                    permit.get("id") or "unknown"
                )
                signal_id = make_id("permit", permit_no)
                if self.memory.has_seen(signal_id):
                    continue
                raw_text = f"""
```

Duval County Permit - Jacksonville FL
Permit: {permit_no}
Address: {address}
Work: {permit.get(‘description’) or permit.get(‘work_description’, ‘’)}
Date: {permit.get(‘issued_date’, ‘recent’)}
Contractor: {permit.get(‘contractor_name’, ‘unknown’)}
Value: {permit.get(‘job_value’, ‘unknown’)}
“””.strip()
signals.append(Signal(
source=“duval_permit”,
raw_text=raw_text,
url=f”https://data.coj.net/permits/{permit_no}”,
signal_id=signal_id,
scraped_at=now(),
))
except Exception as e:
log.warning(f”Permits error: {e}”)
log.info(f”Permits: {len(signals)} new signals”)
return signals

```
def scan_news(self) -> List[Signal]:
    log.info("Scout: Local news...")
    signals = []
    feeds = [
        "https://www.news4jax.com/rss",
        "https://www.firstcoastnews.com/feeds/syndication/news",
    ]
    keywords = [
        "storm", "hurricane", "wind damage", "tornado",
        "severe weather", "tropical", "damage"
    ]
    for feed_url in feeds:
        try:
            resp = requests.get(
                feed_url, headers=self.headers, timeout=10)
            if resp.status_code != 200:
                continue
            root = ET.fromstring(resp.content)
            channel = root.find("channel")
            if not channel:
                continue
            for item in channel.findall("item"):
                title = item.findtext("title") or ""
                desc = item.findtext("description") or ""
                link = item.findtext("link") or ""
                combined = f"{title} {desc}".lower()
                if not any(k in combined for k in keywords):
                    continue
                signal_id = make_id("news", link or title)
                if self.memory.has_seen(signal_id):
                    continue
                raw_text = f"""
```

Jacksonville News - Potential Storm/Damage Event
Headline: {title}
Summary: {desc[:400]}
URL: {link}
Location: Jacksonville FL
Context: Weather event may have caused garage door damage in area
“””.strip()
signals.append(Signal(
source=“local_news”,
raw_text=raw_text,
url=link,
signal_id=signal_id,
scraped_at=now(),
))
except Exception as e:
log.warning(f”News error: {e}”)
time.sleep(1)
log.info(f”News: {len(signals)} new signals”)
return signals

```
def scan_competitor_reviews(self) -> List[Signal]:
    if not SERP_API_KEY:
        return []
    log.info("Scout: Competitor reviews...")
    signals = []
    competitors = [
        "Precision Door Service Jacksonville FL",
        "AAction Garage Doors Jacksonville",
        "Overhead Door Jacksonville",
        "garage door repair Jacksonville FL",
    ]
    for competitor in competitors:
        try:
            r = requests.get(
                "https://serpapi.com/search",
                params={
                    "engine": "google_maps",
                    "q": competitor,
                    "ll": "@30.3322,-81.6557,12z",
                    "api_key": SERP_API_KEY,
                },
                timeout=15
            )
            if r.status_code != 200:
                continue
            results = r.json().get("local_results", [])
            if not results:
                continue
            place_id = results[0].get("place_id")
            if not place_id:
                continue
            rev = requests.get(
                "https://serpapi.com/search",
                params={
                    "engine": "google_maps_reviews",
                    "place_id": place_id,
                    "sort_by": "newestFirst",
                    "api_key": SERP_API_KEY,
                },
                timeout=15
            )
            for review in rev.json().get("reviews", []):
                if review.get("rating", 5) > 3:
                    continue
                text = review.get("snippet") or review.get("text") or ""
                if len(text) < 30:
                    continue
                signal_id = make_id("review", place_id, text[:40])
                if self.memory.has_seen(signal_id):
                    continue
                raw_text = f"""
```

Unhappy Customer Review - {competitor} - Jacksonville FL
Rating: {review.get(‘rating’)}/5 stars
Review: {text}
Date: {review.get(‘date’, ‘recent’)}
Reviewer: {review.get(‘user’, {}).get(‘name’, ‘Anonymous’)}
This customer is unhappy and likely looking for a better provider.
“””.strip()
signals.append(Signal(
source=“competitor_review”,
raw_text=raw_text,
url=results[0].get(“link”, “”),
signal_id=signal_id,
scraped_at=now(),
))
time.sleep(2)
except Exception as e:
log.warning(f”Review error: {e}”)
log.info(f”Reviews: {len(signals)} new signals”)
return signals

```
def scan_all(self) -> List[Signal]:
    all_signals = []
    all_signals.extend(self.scan_permits())
    all_signals.extend(self.scan_news())
    all_signals.extend(self.scan_competitor_reviews())
    log.info(f"Scout total: {len(all_signals)} new signals")
    return all_signals
```

# ================================================================

# AGENT 4 - CONTACT FINDER

# ================================================================

class ContactAgent:
def enrich(self, lead: Lead) -> Lead:
if lead.phone:
return lead
# Flag for manual skip-trace if no phone found
if lead.address:
log.info(f”No phone found - address available for skip-trace: {lead.address}”)
return lead

# ================================================================

# ORCHESTRATOR

# ================================================================

class LeadForgeOrchestrator:
def **init**(self):
log.info(“Initializing LeadForge 5-Agent System…”)
self.memory  = MemoryAgent()
self.scout   = ScoutAgent(self.memory)
self.brain   = BrainAgent(self.memory)
self.contact = ContactAgent()
self.alert   = AlertAgent()
log.info(“All agents ready “)

```
def run(self):
    log.info("=" * 60)
    log.info("LeadForge Jacksonville - Agent Run")
    log.info(f"Time: {now()}")
    stats = self.memory.get_stats()
    log.info(f"Memory: {stats['total_leads']} total leads | "
             f"Run #{stats['total_runs'] + 1}")
    log.info("=" * 60)

    # Agent 1: Scout
    signals = self.scout.scan_all()

    if not signals:
        log.info("No new signals this run")
        self.memory.record_run(0)
        return 0

    # Agents 2-5: Process each signal
    leads_found = []
    hot_count = 0

    for i, signal in enumerate(signals):
        log.info(f"Analyzing {i+1}/{len(signals)}: {signal.source}")

        result = self.brain.analyze(signal)
        self.memory.mark_seen(signal.signal_id)

        if result is None:
            continue

        lead, action = result
        lead = self.contact.enrich(lead)
        self.memory.record_lead(lead)
        leads_found.append(lead)

        if action == "alert_now" or lead.score >= 8:
            hot_count += 1
            log.info(f"FIRE - Hot lead {lead.score}/10 - SMS sending now")
            self.alert.alert_hot_lead(lead)
        else:
            log.info(f"Lead saved - score {lead.score}/10")

        time.sleep(1.5)

    self.memory.record_run(len(leads_found))

    log.info("=" * 60)
    log.info(f"RUN COMPLETE")
    log.info(f"Signals analyzed : {len(signals)}")
    log.info(f"Leads found      : {len(leads_found)}")
    log.info(f"Hot leads (SMS)  : {hot_count}")
    log.info(f"All time total   : {self.memory.data['total_leads']}")
    log.info("=" * 60)

    for lead in leads_found:
        log.info(
            f"  [{lead.score}/10] {lead.job_type} | "
            f"{lead.urgency.upper()} | {lead.estimated_value} | "
            f"{lead.signal_summary[:60]}"
        )

    return len(leads_found)
```

def run_all_agents():
return LeadForgeOrchestrator().run()

if **name** == “**main**”:
run_all_agents()
