# ats-companies

Tenant lists per ATS for **job-engine**. Every company scraped
lives in one of the JSON files here. New rows here = new companies in the dataset.

One file per ATS, named `{ats}.json`. Each row is
`{"name","slug","url"}`:

```json
[{"name": "Acme Corp", "slug": "acme", "url": "https://acme.greenhouse.io"}]
```

- `name` — display name. Free-form. Used as `Job.company` until the
  scraper resolves a richer value from the live page.
- `slug` — the scraper/API identifier the matching scraper accepts
  (lowercase, deterministic).
- `url` — the canonical public careers URL. User-facing — safe to
  ship to consumers as a link. **Not** guaranteed to be a valid
  scraper input on its own; scraper code parses/rejects case-by-case.

> **Schema migration in flight.** A few files still use the legacy
> two-column shape (`name,url`) where `url` is the bare slug. The
> publisher tolerates both: legacy files get an empty `slug` in the
> aggregated R2 output so the published schema (`ats,name,slug,url`)
> stays uniform.

## URL formats by ATS

| ATS | Example |
|---|---|
| adp | `https://{slug}.m.hrblock.com` / ADP career hosts |
| ashby | `https://jobs.ashbyhq.com/<slug>` |
| avature | `https://<slug>.avature.net` |
| bamboohr | `https://<slug>.bamboohr.com/careers` |
| beisen | `https://<slug>.zhiye.com` |
| beisen_legacy | `https://<slug>.zhiye.com/Social` |
| breezy | `https://<slug>.breezy.hr` |
| cornerstone | `https://<slug>.csod.com` |
| darwinbox | `https://<slug>.darwinbox.{in,com}/ms/candidate/careers` |
| keka | `https://<slug>.keka.com/careers` |
| dayforce | Dayforce career site URL |
| eightfold | `https://<slug>.eightfold.ai/careers` |
| gem | `https://jobs.gem.com/<slug>` |
| greenhouse | `https://job-boards.greenhouse.io/<slug>` |
| herp | `https://herp.careers/v1/<slug>` |
| hrmos | `https://hrmos.co/<slug>` |
| icims | `https://careers-<slug>.icims.com` |
| jazzhr | `https://<slug>.applytojob.com` |
| join_com | `https://join.com/companies/<slug>` |
| lever | `https://jobs.lever.co/<slug>` |
| mercor | seed file only — Mercor exposes no per-company endpoint |
| moka | `https://app.mokahr.com/social-recruitment/<slug>/<site_id>` |
| oracle | `https://<host>/hcmUI/CandidateExperience/...` |
| pageup | career PageUp client URL |
| paycom | `https://www.paycomonline.net/v4/ats/web.php/portal/<slug>/career-page` |
| paylocity | `https://recruiting.paylocity.com/Recruiting/Jobs/All/<slug>` |
| personio | `https://<slug>.jobs.personio.com` |
| phenom | Phenom career search URL (+ locale/country columns) |
| pinpoint | `https://<slug>.pinpointhq.com` |
| recruitee | `https://<slug>.recruitee.com` |
| recruiterbox | `https://<slug>.recruiterbox.com` |
| rippling | `https://ats.rippling.com/<slug>` |
| seek | Seek employer career board URL |
| smartrecruiters | `https://jobs.smartrecruiters.com/<slug>` |
| softgarden | `https://<slug>.career.softgarden.de/` |
| successfactors | `https://career.successfactors.com/...` |
| taleo | `https://<host>.taleo.net/careersection/...` |
| teamtailor | `https://<slug>.teamtailor.com` |
| workable | `https://apply.workable.com/<slug>` |
| workday | `https://<host>.myworkdayjobs.com/<board>` |

> **Phenom is the exception.**
> `phenom.json` carries `url,name,company_code,locale,country` because
> Phenom search endpoints are scoped per `(locale, country)` and we
> want to keep that wiring close to the tenant list.

When in doubt, look at the existing rows in the file you're editing —
the scraper accepts whatever shape is already there.

## Contributing

Open a PR adding the row(s) to the relevant `{ats}.json`. Some
guidelines that keep merges clean:

- **One ATS per PR.** Avoid touching multiple files in one change.
- **Sort matters.** Files are roughly ASCII-sorted by `name` — drop
  your row in the right place to minimise diff churn.
- **No duplicates.** Search the file for the slug first; some
  companies use multiple ATSes (e.g. Eightfold + Workday) but each
  row should appear once per file.
- **CSV-quote names that contain commas** with double quotes:
  `"Foo, Bar Inc",https://foo.bamboohr.com/careers`.
- **One row = one tenant.** A company that runs two separate Workday
  boards (e.g. corporate + retail) gets two rows.

The scrapers also discover tenants automatically from public
indexes — but those passes don't catch everything, and a manual PR is
often the fastest way to add a long-tail company.

## Notes

- These CSVs are currently the source of truth for the public
  pipeline. The scraper code lives in
  [`src/job_engine/fetch/scrapers/`](../../../src/job_engine/fetch/scrapers/).
- A few ATSes (`tesla`, `meta`) require a real browser and don't ship
  a tenant list — they'll come back here once the optional browser
  backend ships in 0.2.
- Public-sector aggregators (`bundesagentur`, `arbetsformedlingen`,
  `eures`, `usajobs`) and direct-posting jobboards (`remoteok`,
  `ycombinator`, `wellfound`, …) are single-tenant — no CSV here.
