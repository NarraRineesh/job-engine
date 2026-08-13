-- Normalized job schema (greenfield). No legacy flat jobs layout.
-- Drops prior skill-intelligence / browse objects if present, then recreates.

begin;

-- ---------------------------------------------------------------------------
-- Drop old / prior objects (order matters for FKs)
-- ---------------------------------------------------------------------------
drop table if exists public.skill_trends cascade;
drop table if exists public.skill_relations cascade;
drop table if exists public.unknown_skills cascade;
drop table if exists public.skill_aliases cascade;
drop table if exists public.job_skills cascade;
drop table if exists public.company_trends cascade;
drop table if exists public.job_analytics cascade;
drop table if exists public.jobs cascade;
drop table if exists public.locations cascade;
drop table if exists public.companies cascade;
drop table if exists public.skills cascade;

-- ---------------------------------------------------------------------------
-- companies
-- ---------------------------------------------------------------------------
create table public.companies (
  id          bigserial primary key,
  slug        text unique not null,
  name        text not null,
  logo        text,
  website     text,
  industry    text,
  size        text,
  type        text,
  verified    boolean not null default false,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- locations
-- ---------------------------------------------------------------------------
create table public.locations (
  id            bigserial primary key,
  location_key  text unique not null,
  country       text,
  state         text,
  city          text,
  formatted     text,
  latitude      double precision,
  longitude     double precision,
  created_at    timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- jobs
-- ---------------------------------------------------------------------------
create table public.jobs (
  id                text primary key,
  company_id        bigint references public.companies(id),
  location_id       bigint references public.locations(id),
  title             text not null,
  normalized_title  text not null,
  department        text,
  team              text,
  summary           text,
  description       text,
  employment_type   smallint,
  work_mode         smallint,
  seniority         smallint,
  min_experience    smallint,
  max_experience    smallint,
  salary_currency   char(3),
  salary_min        integer,
  salary_max        integer,
  salary_period     smallint,
  salary_visible    boolean not null default false,
  vacancies         smallint not null default 1,
  apply_url         text,
  detail_api_url    text,
  ats               smallint,
  external_id       text,
  posted_at         timestamptz,
  updated_at        timestamptz,
  last_scraped_at   timestamptz,
  status            smallint,
  expired           boolean not null default false,
  language          varchar(10),
  search_vector     tsvector,
  created_at        timestamptz not null default now(),
  constraint jobs_employment_type_chk check (employment_type is null or employment_type between 1 and 6),
  constraint jobs_work_mode_chk check (work_mode is null or work_mode between 1 and 3),
  constraint jobs_seniority_chk check (seniority is null or seniority between 1 and 10),
  constraint jobs_status_chk check (status is null or status between 1 and 4),
  constraint jobs_salary_period_chk check (salary_period is null or salary_period between 1 and 3)
);

create or replace function public.jobs_search_vector_update()
returns trigger
language plpgsql
as $$
begin
  new.search_vector :=
    setweight(to_tsvector('english', coalesce(new.title, '')), 'A') ||
    setweight(to_tsvector('english', coalesce(new.normalized_title, '')), 'A') ||
    setweight(to_tsvector('english', coalesce(new.summary, '')), 'B') ||
    setweight(to_tsvector('english', coalesce(new.department, '')), 'C');
  return new;
end;
$$;

create trigger jobs_search_vector_trg
  before insert or update of title, normalized_title, summary, department
  on public.jobs
  for each row
  execute function public.jobs_search_vector_update();

create index idx_jobs_title on public.jobs (normalized_title);
create index idx_jobs_company on public.jobs (company_id);
create index idx_jobs_location on public.jobs (location_id);
create index idx_jobs_work_mode on public.jobs (work_mode);
create index idx_jobs_employment on public.jobs (employment_type);
create index idx_jobs_experience on public.jobs (min_experience);
create index idx_jobs_posted on public.jobs (posted_at desc nulls last);
create index idx_jobs_status on public.jobs (status);
create index idx_jobs_ats on public.jobs (ats);
create index idx_jobs_last_scraped on public.jobs (last_scraped_at);
create index idx_jobs_search on public.jobs using gin (search_vector);

-- ---------------------------------------------------------------------------
-- skills + job_skills
-- ---------------------------------------------------------------------------
create table public.skills (
  id               bigserial primary key,
  name             text unique not null,
  normalized_name  text unique not null,
  job_count        integer not null default 0,
  trend_score      numeric(10, 2) default 0,
  importance_score integer default 50 check (importance_score >= 0 and importance_score <= 100),
  last_seen        timestamptz,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now()
);

create table public.job_skills (
  job_id    text not null references public.jobs(id) on delete cascade,
  skill_id  bigint not null references public.skills(id) on delete cascade,
  source    text not null default 'llm',
  created_at timestamptz not null default now(),
  primary key (job_id, skill_id)
);

create index idx_job_skills_skill on public.job_skills (skill_id);
create index idx_job_skills_job on public.job_skills (job_id);

-- ---------------------------------------------------------------------------
-- job_analytics
-- ---------------------------------------------------------------------------
create table public.job_analytics (
  job_id        text primary key references public.jobs(id) on delete cascade,
  views         integer not null default 0,
  clicks        integer not null default 0,
  applications  integer not null default 0,
  saved         integer not null default 0,
  updated_at    timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- skill intelligence (BIGINT FKs)
-- ---------------------------------------------------------------------------
create table public.skill_aliases (
  id         bigserial primary key,
  skill_id   bigint not null references public.skills(id) on delete cascade,
  alias      text not null unique,
  created_at timestamptz not null default now()
);

create index skill_aliases_skill_id_idx on public.skill_aliases (skill_id);

create table public.unknown_skills (
  id          bigserial primary key,
  skill_name  text not null unique,
  first_seen  timestamptz not null default now(),
  last_seen   timestamptz not null default now(),
  seen_count  integer not null default 1,
  status      text not null default 'pending'
    check (status in ('pending', 'processing', 'classified', 'rejected'))
);

create index unknown_skills_status_idx
  on public.unknown_skills (status)
  where status = 'pending';

create table public.skill_relations (
  skill_id         bigint not null references public.skills(id) on delete cascade,
  related_skill_id bigint not null references public.skills(id) on delete cascade,
  weight           numeric(4, 3) not null default 0.5 check (weight >= 0 and weight <= 1),
  created_at       timestamptz not null default now(),
  primary key (skill_id, related_skill_id),
  check (skill_id <> related_skill_id)
);

create table public.skill_trends (
  id                bigserial primary key,
  skill_id          bigint not null references public.skills(id) on delete cascade,
  month             date not null,
  job_count         integer not null default 0,
  growth_percentage numeric(10, 2) default 0,
  unique (skill_id, month)
);

create index skill_trends_skill_month_idx
  on public.skill_trends (skill_id, month desc);

-- ---------------------------------------------------------------------------
-- company_trends
-- ---------------------------------------------------------------------------
create table public.company_trends (
  id                bigserial primary key,
  company_id        bigint not null references public.companies(id) on delete cascade,
  month             date not null,
  job_count         integer not null default 0,
  growth_percentage numeric(10, 2) default 0,
  unique (company_id, month)
);

create index company_trends_company_month_idx
  on public.company_trends (company_id, month desc);

create index company_trends_month_growth_idx
  on public.company_trends (month, growth_percentage desc);

commit;
