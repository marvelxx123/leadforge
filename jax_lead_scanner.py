"""
GaragePulse - Jacksonville Lead Generation System
5 Agents: Scout, Brain, Memory, Contact, Alert
"""

import os
import json
import time
import hashlib
import logging
import smtplib
import xml.etree.ElementTree as ET
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
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
log = logging.getLogger("GaragePulse")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
EMAIL_ADDRESS     = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD    = os.getenv("EMAIL_PASSWORD")
SERP_API_KEY      = os.getenv("SERP_API_KEY")
MEMORY_FILE       = "garagepulse_memory.json"

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
    created_at:​​​​​​​​​​​​​​​​
