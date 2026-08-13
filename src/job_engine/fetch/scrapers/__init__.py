"""ATS scrapers — one class per platform.

Each scraper is a thin, dependency-light fetch+parse layer that returns
`Job` instances. Discovery, enrichment, deduplication, and publishing are
kept outside the public scraper API so each scraper stays usable on its own.

>>> from job_engine.fetch.scrapers import GreenhouseScraper
>>> jobs = GreenhouseScraper("anthropic").fetch()
"""

from job_engine.fetch.scrapers.amazon import AmazonScraper
from job_engine.fetch.scrapers.apple import AppleScraper
from job_engine.fetch.scrapers.arbetsformedlingen import ArbetsformedlingenScraper
from job_engine.fetch.scrapers.ashby import AshbyScraper
from job_engine.fetch.scrapers.avature import AvatureScraper
from job_engine.fetch.scrapers.bamboohr import BambooHRScraper
from job_engine.fetch.scrapers.base import BaseScraper, ScraperRegistry, get_scraper
from job_engine.fetch.scrapers.beisen import BeisenScraper
from job_engine.fetch.scrapers.beisen_legacy import BeisenLegacyScraper
from job_engine.fetch.scrapers.breezy import BreezyScraper
from job_engine.fetch.scrapers.builtin import BuiltInScraper
from job_engine.fetch.scrapers.bundesagentur import BundesagenturScraper
from job_engine.fetch.scrapers.bytedance import BytedanceScraper
from job_engine.fetch.scrapers.cornerstone import CornerstoneScraper
from job_engine.fetch.scrapers.darwinbox import DarwinboxScraper
from job_engine.fetch.scrapers.dayforce import DayforceScraper
from job_engine.fetch.scrapers.eightfold import EightfoldScraper
from job_engine.fetch.scrapers.eures import EuresScraper
from job_engine.fetch.scrapers.gem import GemScraper
from job_engine.fetch.scrapers.getonbrd import GetOnBrdScraper
from job_engine.fetch.scrapers.google import GoogleScraper
from job_engine.fetch.scrapers.greenhouse import GreenhouseScraper
from job_engine.fetch.scrapers.gupy import GupyScraper
from job_engine.fetch.scrapers.icims import iCIMSScraper
from job_engine.fetch.scrapers.infojobs_es import InfoJobsSpainScraper
from job_engine.fetch.scrapers.jazzhr import JazzHRScraper
from job_engine.fetch.scrapers.jobbankca import JobBankCAScraper
from job_engine.fetch.scrapers.jobs_cz import JobsCzScraper
from job_engine.fetch.scrapers.jobsch import JobsChScraper
from job_engine.fetch.scrapers.jobvite import JobviteScraper
from job_engine.fetch.scrapers.join_com import JoinComScraper
from job_engine.fetch.scrapers.keka import KekaScraper
from job_engine.fetch.scrapers.lever import LeverScraper
from job_engine.fetch.scrapers.manfred import ManfredScraper
from job_engine.fetch.scrapers.mercor import MercorScraper
from job_engine.fetch.scrapers.meta import MetaScraper
from job_engine.fetch.scrapers.moka import MokaScraper
from job_engine.fetch.scrapers.oracle import OracleScraper
from job_engine.fetch.scrapers.pageup import PageUpScraper
from job_engine.fetch.scrapers.personio import PersonioScraper
from job_engine.fetch.scrapers.phenom import PhenomScraper
from job_engine.fetch.scrapers.pinpoint import PinpointScraper
from job_engine.fetch.scrapers.programathor import ProgramathorScraper
from job_engine.fetch.scrapers.recruitee import RecruiteeScraper
from job_engine.fetch.scrapers.recruiterbox import RecruiterboxScraper
from job_engine.fetch.scrapers.remoteok import RemoteOKScraper
from job_engine.fetch.scrapers.rippling import RipplingScraper
from job_engine.fetch.scrapers.seek import SeekScraper
from job_engine.fetch.scrapers.smartrecruiters import SmartRecruitersScraper
from job_engine.fetch.scrapers.successfactors import SuccessFactorsScraper
from job_engine.fetch.scrapers.taleo import TaleoScraper
from job_engine.fetch.scrapers.teamtailor import TeamtailorScraper
from job_engine.fetch.scrapers.tesla import TeslaScraper
from job_engine.fetch.scrapers.thehub import TheHubScraper
from job_engine.fetch.scrapers.tiktok import TikTokScraper
from job_engine.fetch.scrapers.uber import UberScraper
from job_engine.fetch.scrapers.ukg import UKGProScraper
from job_engine.fetch.scrapers.usajobs import USAJobsScraper
from job_engine.fetch.scrapers.wanted import WantedScraper
from job_engine.fetch.scrapers.welcometothejungle import WTTJScraper
from job_engine.fetch.scrapers.wellfound import WellfoundScraper
from job_engine.fetch.scrapers.weworkremotely import WeWorkRemotelyScraper
from job_engine.fetch.scrapers.workable import WorkableScraper
from job_engine.fetch.scrapers.workday import WorkdayScraper
from job_engine.fetch.scrapers.ycombinator import YCombinatorScraper

__all__ = [
    "AmazonScraper",
    "AppleScraper",
    "ArbetsformedlingenScraper",
    "AshbyScraper",
    "AvatureScraper",
    "BambooHRScraper",
    "BaseScraper",
    "BeisenLegacyScraper",
    "BeisenScraper",
    "BreezyScraper",
    "BuiltInScraper",
    "BundesagenturScraper",
    "BytedanceScraper",
    "CornerstoneScraper",
    "DarwinboxScraper",
    "DayforceScraper",
    "EightfoldScraper",
    "EuresScraper",
    "GemScraper",
    "GetOnBrdScraper",
    "GoogleScraper",
    "GreenhouseScraper",
    "GupyScraper",
    "InfoJobsSpainScraper",
    "JazzHRScraper",
    "JobBankCAScraper",
    "JobsChScraper",
    "JobsCzScraper",
    "JobviteScraper",
    "JoinComScraper",
    "KekaScraper",
    "LeverScraper",
    "ManfredScraper",
    "MercorScraper",
    "MetaScraper",
    "MokaScraper",
    "OracleScraper",
    "PageUpScraper",
    "PersonioScraper",
    "PhenomScraper",
    "PinpointScraper",
    "ProgramathorScraper",
    "RecruiteeScraper",
    "RecruiterboxScraper",
    "RemoteOKScraper",
    "RipplingScraper",
    "ScraperRegistry",
    "SeekScraper",
    "SmartRecruitersScraper",
    "SuccessFactorsScraper",
    "TaleoScraper",
    "TeamtailorScraper",
    "TeslaScraper",
    "TheHubScraper",
    "TikTokScraper",
    "UKGProScraper",
    "USAJobsScraper",
    "UberScraper",
    "WTTJScraper",
    "WantedScraper",
    "WeWorkRemotelyScraper",
    "WellfoundScraper",
    "WorkableScraper",
    "WorkdayScraper",
    "YCombinatorScraper",
    "get_scraper",
    "iCIMSScraper",
]
