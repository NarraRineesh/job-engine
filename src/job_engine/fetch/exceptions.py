"""Exception hierarchy for scrapers."""


class ATSScrapersError(Exception):
    """Base class for all scraper errors."""


class ScraperError(ATSScrapersError):
    """Raised when an ATS scraper fails to fetch or parse jobs."""


class CompanyNotFoundError(ScraperError):
    """Raised when a company is not present on the requested ATS."""
