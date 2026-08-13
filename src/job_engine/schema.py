"""India-ats nested job schema (Pydantic)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

EmploymentType = Literal[
    "full_time", "part_time", "contract", "intern", "temporary", "freelance", "unknown"
]
WorkMode = Literal["remote", "hybrid", "onsite", "unknown"]
SalaryPeriod = Literal["hour", "day", "week", "month", "year"] | None
Status = Literal["active", "closed", "draft", "expired"]


class Source(BaseModel):
    ats: str
    companySlug: str = ""
    externalId: str = ""
    applyUrl: str = ""
    detailApiUrl: str = ""


class Company(BaseModel):
    id: str = ""
    name: str = ""
    slug: str = ""


class Experience(BaseModel):
    min: int | None = None
    max: int | None = None


class Salary(BaseModel):
    currency: str | None = None
    min: float | None = None
    max: float | None = None
    period: SalaryPeriod = None


class Location(BaseModel):
    formatted: str = ""
    countryCode: str | None = None
    country: str | None = None
    state: str | None = None
    city: str | None = None


class Skills(BaseModel):
    required: list[str] = Field(default_factory=list)
    preferred: list[str] = Field(default_factory=list)


class Analytics(BaseModel):
    views: int = 0
    clicks: int = 0
    applications: int = 0
    saved: int = 0


class NestedJob(BaseModel):
    """Canonical job-engine nested job."""

    id: str
    source: Source
    company: Company
    title: str
    titleTokens: list[str] = Field(default_factory=list)
    department: str | None = None
    team: str | None = None
    employmentType: EmploymentType = "unknown"
    workMode: WorkMode = "unknown"
    experience: Experience = Field(default_factory=Experience)
    salary: Salary = Field(default_factory=Salary)
    location: Location = Field(default_factory=Location)
    skills: Skills = Field(default_factory=Skills)
    description: str | None = None
    postedAt: str = ""
    updatedAt: str = ""
    scrapedAt: str = ""
    status: Status = "active"
    analytics: Analytics = Field(default_factory=Analytics)
