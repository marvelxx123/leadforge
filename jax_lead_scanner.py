"""
LeadForge Jacksonville - Full Multi-Agent System
5 Agents: Scout, Brain, Memory, Contact, Alert
"""

import os
import json
import time
import hashlib
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Optional, List, Tuple

import requests
import anthropic
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("LeadForge")

ANTHROPIC_API_KEY  = os.getenv("ANTHROPIC_API_KEY")
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN  = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER")
TWILIO_TO_NUMBER   = os.getenv("TWILIO_TO_NUMBER")
SERP_API_KEY       = os.getenv("SERP_API_KEY")
MEMORY_FILE        = "leadforge_memory.json"

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

def now():
    return datetime.now(timezone.utc).isoformat()

def make_id(*parts):
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


class MemoryAgent:
    def __init__(self):
        self.data = self._load()

    def _load(self):
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

    def has_seen(self, signal_id):
        return signal_id in self.data["seen_signals"]

    def mark_seen(self, signal_id):
        if signal_id not in self.data["seen_signals"]:
            self.data["seen_signals"].append(signal_id)
            if len(self.data["seen_signals"]) > 5000:
                self.data["seen_signals"] = self.data["seen_signals"][-5000:]
        self._save()

    def record_lead(self, lead):
        self.data["total_leads"] += 1
        source = lead.source
        self.data["leads_by_source"][source] = \
            self.data["leads_by_source"].get(source, 0) + 1
        self._save()

    def record_run(self, leads_found):
        self.data["run_count"] += 1
        self.data["last_run"] = now()
        self._save()

    def get_stats(self):
        return {
            "total_leads": self.data["total_leads"],
            "total_runs": self.data["run_count"],
            "by_source": self.data["leads_by_source"],
            "last_run": self.data["last_run"],
        }

    def get_best_sources(self):
        sources = self.data["leads_by_source"]
        return sorted(sources, key=lambda x: sources[x], reverse=True) if sources else []


class AlertAgent:
    def __init__(self):
        self.enabled = False
        if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
            try:
                from twilio.rest import Client
                self.client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
                self.enabled = True
                log.info("Alert Agent: SMS enabled")
            except ImportError:
                log.warning("Alert Agent: twilio not installed")
        else:
            log.warning("Alert Agent: Twilio keys not set")

    def send_sms(self, to, message):
        if not self.enabled:
            log.info("[SMS DISABLED] " + message[:80])
            return
        try:
            msg = self.client.messages.create(
                body=message,
                from_=TWILIO_FROM_NUMBER,
                to=to
            )
            log.info("SMS sent sid:" + msg.sid)
        except Exception as e:
            log.error("SMS failed: " + str(e))

    def alert_hot_lead(self, lead):
        msg = (
            "HOT LEAD " + str(lead.score) + "/10\n"
            "Job: " + lead.signal_summary + "\n"
            "Type: " + (lead.job_type or "unknown") + "\n"
            "Value: " + (lead.estimated_value or "TBD") + "\n"
            "Address: " + (lead.address or "Jacksonville FL") + "\n"
            "Phone: " + (lead.phone or "not found") + "\n"
            "Source: " + lead.source
        )
        self.send_sms(TWILIO_TO_NUMBER, msg)

    def alert_contractor(self, lead, contractor_number):
        msg = (
            "New Garage Door Lead - Jacksonville\n"
            "Job: " + lead.signal_summary + "\n"
            "Value: " + (lead.estimated_value or "TBD") + "\n"
            "Address: " + (lead.address or "Jacksonville FL") + "\n"
            "Phone: " + (lead.phone or "check URL") + "\n"
            "LeadForge"
        )
        self.send_sms(contractor_number, msg)


class BrainAgent:
    def __init__(self, memory):
        self.client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        self.memory = memory

    def analyze(self, signal):
        stats = self.memory.get_stats()
        best = self.memory.get_best_sources()[:3]

        prompt = (
            "You are the AI brain of LeadForge - a garage door lead generation "
            "system in Jacksonville, Florida.\n\n"
            "Analyze this signal. Determine if it is a real high quality "
            "garage door lead worth acting on.\n\n"
            "SYSTEM MEMORY:\n"
            "- Total leads found so far: " + str(stats["total_leads"]) + "\n"
            "- Best sources so far: " + str(best if best else "still learning") + "\n"
            "- Run number: " + str(stats["total_runs"]) + "\n\n"
            "SIGNAL:\n"
            "Source: " + signal.source + "\n"
            "URL: " + signal.url + "\n"
            "Text: " + signal.raw_text[:3000] + "\n\n"
            "SCORE GUIDE:\n"
            "10 = urgent repair + Jacksonville confirmed + contact info\n"
            "9  = urgent repair + Jacksonville confirmed\n"
            "8  = planned install + high value + Jacksonville\n"
            "7  = strong intent + likely Jacksonville\n"
            "6  = possible lead needs verification\n"
            "5  = weak signals might be Jacksonville\n"
            "1-4 = disqualify\n\n"
            "Return ONLY valid JSON no markdown no explanation:\n"
            "{\n"
            '  "name": "full name or null",\n'
            '  "phone": "phone with area code or null",\n'
            '  "address": "address or neighborhood in Jacksonville or null",\n'
            '  "signal_summary": "one sentence describing exactly what they need",\n'
            '  "urgency": "high | medium | low",\n'
            '  "score": integer 1-10,\n'
            '  "estimated_value": "realistic range like $350-$500",\n'
            '  "job_type": "spring repair | opener install | new door | cable repair | panel repair | general repair | unknown",\n'
            '  "is_jacksonville_lead": true or false,\n'
            '  "disqualify_reason": "reason or null",\n'
            '  "action": "alert_now | save | discard"\n'
            "}\n\n"
            "action: alert_now if score 8 or above and is_jacksonville_lead true\n"
            "        save if score 5 to 7\n"
            "        discard otherwise"
        )

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
            log.warning("Brain failed: " + str(e))
            return None

        if not data.get("is_jacksonville_lead"):
            return None
        if data.get("disqualify_reason"):
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

        log.info("LEAD | " + str(score) + "/10 | " + str(lead.job_type) + " | " + lead.signal_summary[:50])
        return lead, data.get("action", "save")


class ScoutAgent:
    def __init__(self, memory):
        self.memory = memory
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
        }

    def scan_permits(self):
        log.info("Scout: Scanning Duval County permits...")
        signals = []
        try:
            url = "https://data.coj.net/resource/permits.json"
            params = {
                "$limit": 50,
                "$order": "issued_date DESC",
                "$q": "garage door",
            }
            resp = requests.get(url, params=params, headers=self.headers, timeout=15)
            if resp.status_code == 200:
                permits = resp.json()
                log.info("Permits API returned " + str(len(permits)) + " records")
                for permit in permits:
                    address = permit.get("site_address") or permit.get("address") or "Jacksonville FL"
                    permit_no = str(permit.get("permit_number") or permit.get("id") or "unknown")
                    signal_id = make_id("permit", permit_no)
                    if self.memory.has_seen(signal_id):
                        continue
                    raw_text = (
                        "Duval County Permit - Jacksonville FL\n"
                        "Permit: " + permit_no + "\n"
                        "Address: " + address + "\n"
                        "Work: " + str(permit.get("description") or permit.get("work_description", "")) + "\n"
                        "Date: " + str(permit.get("issued_date", "recent")) + "\n"
                        "Contractor: " + str(permit.get("contractor_name", "unknown")) + "\n"
                        "Value: " + str(permit.get("job_value", "unknown"))
                    )
                    signals.append(Signal(
                        source="duval_permit",
                        raw_text=raw_text,
                        url="https://data.coj.net/permits/" + permit_no,
                        signal_id=signal_id,
                        scraped_at=now(),
                    ))
            else:
                log.warning("Permits API returned " + str(resp.status_code))
        except Exception as e:
            log.warning("Permits error: " + str(e))
        log.info("Permits: " + str(len(signals)) + " new signals")
        return signals

    def scan_news(self):
        log.info("Scout: Local news...")
        signals = []
        feeds = [
            "https://www.news4jax.com/rss",
            "https://www.firstcoastnews.com/feeds/syndication/news",
        ]
        keywords = ["storm", "hurricane", "wind damage", "tornado", "severe weather", "tropical", "damage"]
        for feed_url in feeds:
            try:
                resp = requests.get(feed_url, headers=self.headers, timeout=10)
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
                    combined = (title + " " + desc).lower()
                    if not any(k in combined for k in keywords):
                        continue
                    signal_id = make_id("news", link or title)
                    if self.memory.has_seen(signal_id):
                        continue
                    raw_text = (
                        "Jacksonville News - Storm or Weather Damage\n"
                        "Headline: " + title + "\n"
                        "Summary: " + desc[:400] + "\n"
                        "URL: " + link + "\n"
                        "Location: Jacksonville FL"
                    )
                    signals.append(Signal(
                        source="local_news",
                        raw_text=raw_text,
                        url=link,
                        signal_id=signal_id,
                        scraped_at=now(),
                    ))
            except Exception as e:
                log.warning("News error: " + str(e))
            time.sleep(1)
        log.info("News: " + str(len(signals)) + " new signals")
        return signals

    def scan_competitor_reviews(self):
        if not SERP_API_KEY:
            log.info("Scout: No SerpAPI key - skipping reviews")
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
                    raw_text = (
                        "Unhappy Customer Review - " + competitor + " - Jacksonville FL\n"
                        "Rating: " + str(review.get("rating")) + "/5 stars\n"
                        "Review: " + text + "\n"
                        "Date: " + str(review.get("date", "recent")) + "\n"
                        "This customer is unhappy and likely looking for a better provider."
                    )
                    signals.append(Signal(
                        source="competitor_review",
                        raw_text=raw_text,
                        url=results[0].get("link", ""),
                        signal_id=signal_id,
                        scraped_at=now(),
                    ))
                time.sleep(2)
            except Exception as e:
                log.warning("Review error: " + str(e))
        log.info("Reviews: " + str(len(signals)) + " new signals")
        return signals

    def scan_all(self):
        all_signals = []
        all_signals.extend(self.scan_permits())
        all_signals.extend(self.scan_news())
        all_signals.extend(self.scan_competitor_reviews())
        log.info("Scout total: " + str(len(all_signals)) + " new signals")
        return all_signals


class ContactAgent:
    def enrich(self, lead):
        if lead.phone:
            return lead
        if lead.address:
            log.info("No phone found - address for skip-trace: " + lead.address)
        return lead


class LeadForgeOrchestrator:
    def __init__(self):
        log.info("Initializing LeadForge 5-Agent System...")
        self.memory  = MemoryAgent()
        self.scout   = ScoutAgent(self.memory)
        self.brain   = BrainAgent(self.memory)
        self.contact = ContactAgent()
        self.alert   = AlertAgent()
        log.info("All 5 agents ready")

    def run(self):
        log.info("LeadForge Jacksonville - Agent Run Starting")
        log.info("Time: " + now())
        stats = self.memory.get_stats()
        log.info("Total leads so far: " + str(stats["total_leads"]) + " | Run #" + str(stats["total_runs"] + 1))

        signals = self.scout.scan_all()

        if not signals:
            log.info("No new signals this run")
            self.memory.record_run(0)
            return 0

        leads_found = []
        hot_count = 0

        for i, signal in enumerate(signals):
            log.info("Analyzing " + str(i+1) + "/" + str(len(signals)) + ": " + signal.source)
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
                log.info("HOT LEAD " + str(lead.score) + "/10 - SMS sending now")
                self.alert.alert_hot_lead(lead)
            else:
                log.info("Lead saved - score " + str(lead.score) + "/10")

            time.sleep(1.5)

        self.memory.record_run(len(leads_found))

        log.info("RUN COMPLETE")
        log.info("Signals analyzed: " + str(len(signals)))
        log.info("Leads found: " + str(len(leads_found)))
        log.info("Hot leads SMS: " + str(hot_count))
        log.info("All time total: " + str(self.memory.data["total_leads"]))

        for lead in leads_found:
            log.info("[" + str(lead.score) + "/10] " + str(lead.job_type) + " | " + lead.urgency.upper() + " | " + str(lead.estimated_value) + " | " + lead.signal_summary[:60])

        return len(leads_found)


def run_all_agents():
    return LeadForgeOrchestrator().run()


if __name__ == "__main__":
    run_all_agents()

