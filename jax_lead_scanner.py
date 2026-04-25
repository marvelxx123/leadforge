"""
LeadForge Jacksonville — Full Multi-Agent System
=================================================
5 Agents working together:

AGENT 1 - SCOUT      : Finds raw signals from multiple sources
AGENT 2 - BRAIN      : Claude analyzes, scores, qualifies each lead
AGENT 3 - MEMORY     : Remembers everything, learns what works
AGENT 4 - CONTACT    : Enriches leads with contact info
AGENT 5 - ALERT      : SMS you instantly on hot leads
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

def now() -> str:
    return datetime.now(timezone.utc).isoformat()

def make_id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


class MemoryAgent:
    def __init__(self):
        self.data = self._load()

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
        self.data["last_run"] = now​​​​​​​​​​​​​​​​
