"""Job board fetch layer (HTTP scrapers + Job model)."""

from job_engine._version import __version__
from job_engine.fetch.exceptions import ATSScrapersError, ScraperError
from job_engine.fetch.fetch import Fetcher, FetchResponse, MalformedJSONError
from job_engine.fetch.models import ATSType, EmploymentType, Job, Salary, SalaryPeriod

__all__ = [
    "ATSScrapersError",
    "ATSType",
    "EmploymentType",
    "FetchResponse",
    "Fetcher",
    "Job",
    "MalformedJSONError",
    "Salary",
    "SalaryPeriod",
    "ScraperError",
    "__version__",
]
