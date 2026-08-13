"""ATS parser registry."""

from __future__ import annotations

from job_engine.parsers.amazon import AmazonParser
from job_engine.parsers.ashby import AshbyParser
from job_engine.parsers.base import BaseAtsParser
from job_engine.parsers.beisen import BeisenParser
from job_engine.parsers.darwinbox import DarwinboxParser
from job_engine.parsers.greenhouse import GreenhouseParser
from job_engine.parsers.keka import KekaParser
from job_engine.parsers.lever import LeverParser
from job_engine.parsers.phenom import PhenomParser
from job_engine.parsers.seek import SeekParser
from job_engine.parsers.smartrecruiters import SmartRecruitersParser
from job_engine.parsers.workable import WorkableParser
from job_engine.parsers.workday import WorkdayParser

# Lightweight dedicated parsers for remaining common boards
class BamboohrParser(BaseAtsParser):
    ats = "bamboohr"


class RecruiteeParser(BaseAtsParser):
    ats = "recruitee"


class TeamtailorParser(BaseAtsParser):
    ats = "teamtailor"


class BreezyParser(BaseAtsParser):
    ats = "breezy"


class PinpointParser(BaseAtsParser):
    ats = "pinpoint"


class GoogleParser(BaseAtsParser):
    ats = "google"


class GenericParser(BaseAtsParser):
    ats = "custom"


_REGISTRY: dict[str, BaseAtsParser] = {
    "greenhouse": GreenhouseParser(),
    "lever": LeverParser(),
    "ashby": AshbyParser(),
    "workable": WorkableParser(),
    "workday": WorkdayParser(),
    "smartrecruiters": SmartRecruitersParser(),
    "bamboohr": BamboohrParser(),
    "recruitee": RecruiteeParser(),
    "teamtailor": TeamtailorParser(),
    "breezy": BreezyParser(),
    "breezyhr": BreezyParser(),
    "pinpoint": PinpointParser(),
    "darwinbox": DarwinboxParser(),
    "keka": KekaParser(),
    "seek": SeekParser(),
    "phenom": PhenomParser(),
    "amazon": AmazonParser(),
    "beisen": BeisenParser(),
    "google": GoogleParser(),
}

_DEFAULT = GenericParser()


def get_parser(ats: str) -> BaseAtsParser:
    key = (ats or "custom").strip().lower()
    return _REGISTRY.get(key, _DEFAULT)
