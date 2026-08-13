-- Product API RPCs: analytics increments, dashboard aggregates, trending,
-- similarity, recommendations, and location rollups.

begin;

-- ---------------------------------------------------------------------------
-- Analytics: atomic counter increment (insert-once row if missing)
-- ---------------------------------------------------------------------------
create or replace function public.increment_job_analytics(p_job_id text, p_metric text)
returns void
language plpgsql
security definer
as $$
begin
  if p_metric not in ('views', 'clicks', 'applications', 'saved') then
    raise exception 'invalid metric: %', p_metric;
  end if;

  insert into public.job_analytics (job_id)
  values (p_job_id)
  on conflict (job_id) do nothing;

  execute format(
    'update public.job_analytics set %I = %I + 1, updated_at = now() where job_id = $1',
    p_metric, p_metric
  ) using p_job_id;
end;
$$;

-- ---------------------------------------------------------------------------
-- Dashboard aggregates
-- ---------------------------------------------------------------------------
create or replace function public.dashboard_stats()
returns jsonb
language sql
stable
as $$
  select jsonb_build_object(
    'total_jobs',      (select count(*) from public.jobs),
    'active_jobs',     (select count(*) from public.jobs where status = 1),
    'companies',       (select count(*) from public.companies),
    'skills',          (select count(*) from public.skills),
    'locations',       (select count(*) from public.locations),
    'todays_new_jobs', (select count(*) from public.jobs
                        where coalesce(posted_at, created_at)::date = current_date)
  );
$$;

-- ---------------------------------------------------------------------------
-- Trending skills over a recent window (active jobs only)
-- ---------------------------------------------------------------------------
create or replace function public.trending_skills_by_window(
  p_days int default 30,
  p_limit int default 20
)
returns table (skill_id bigint, skill_name text, active_job_count bigint)
language sql
stable
as $$
  select s.id, s.name, count(distinct js.job_id) as active_job_count
  from public.job_skills js
  join public.jobs j on j.id = js.job_id
  join public.skills s on s.id = js.skill_id
  where j.status = 1
    and coalesce(j.posted_at, j.last_scraped_at) >= now() - make_interval(days => p_days)
  group by s.id, s.name
  order by active_job_count desc
  limit p_limit;
$$;

-- ---------------------------------------------------------------------------
-- Similar jobs by shared-skill overlap
-- ---------------------------------------------------------------------------
create or replace function public.similar_jobs(p_job_id text, p_limit int default 20)
returns table (job_id text, shared_skills bigint)
language sql
stable
as $$
  select js2.job_id, count(*) as shared_skills
  from public.job_skills js1
  join public.job_skills js2
    on js2.skill_id = js1.skill_id
   and js2.job_id <> js1.job_id
  join public.jobs j on j.id = js2.job_id and j.status = 1
  where js1.job_id = p_job_id
  group by js2.job_id
  order by shared_skills desc
  limit p_limit;
$$;

-- ---------------------------------------------------------------------------
-- Featured jobs: engagement-weighted analytics score
-- ---------------------------------------------------------------------------
create or replace function public.featured_jobs(p_limit int default 20)
returns table (job_id text, score bigint)
language sql
stable
as $$
  select j.id,
         (a.views + a.clicks * 2 + a.saved * 3 + a.applications * 5)::bigint as score
  from public.jobs j
  join public.job_analytics a on a.job_id = j.id
  where j.status = 1
  order by score desc, j.posted_at desc nulls last
  limit p_limit;
$$;

-- ---------------------------------------------------------------------------
-- Trending jobs: recent activity window + engagement
-- ---------------------------------------------------------------------------
create or replace function public.trending_jobs(p_days int default 14, p_limit int default 20)
returns table (job_id text, score bigint)
language sql
stable
as $$
  select j.id,
         (coalesce(a.views, 0) + coalesce(a.clicks, 0) * 2)::bigint as score
  from public.jobs j
  left join public.job_analytics a on a.job_id = j.id
  where j.status = 1
    and coalesce(j.posted_at, j.last_scraped_at) >= now() - make_interval(days => p_days)
  order by score desc, j.posted_at desc nulls last
  limit p_limit;
$$;

-- ---------------------------------------------------------------------------
-- Recommendations: jobs ranked by user-skill overlap
-- ---------------------------------------------------------------------------
create or replace function public.recommend_jobs_by_skills(
  p_skills text[],
  p_country text default null,
  p_work_mode smallint default null,
  p_experience_min smallint default null,
  p_limit int default 20
)
returns table (job_id text, matched_skills bigint)
language sql
stable
as $$
  select j.id, count(distinct s.id) as matched_skills
  from public.jobs j
  join public.job_skills js on js.job_id = j.id
  join public.skills s on s.id = js.skill_id
  left join public.locations l on l.id = j.location_id
  where j.status = 1
    and s.normalized_name = any (p_skills)
    and (p_country is null or l.country ilike p_country)
    and (p_work_mode is null or j.work_mode = p_work_mode)
    and (p_experience_min is null
         or j.min_experience is null
         or j.min_experience <= p_experience_min)
  group by j.id
  order by matched_skills desc, max(coalesce(j.posted_at, j.last_scraped_at)) desc nulls last
  limit p_limit;
$$;

-- ---------------------------------------------------------------------------
-- Related skills via co-occurrence graph
-- ---------------------------------------------------------------------------
create or replace function public.related_skills(p_skills text[], p_limit int default 20)
returns table (skill_id bigint, skill_name text, total_weight numeric)
language sql
stable
as $$
  select s2.id, s2.name, sum(r.weight) as total_weight
  from public.skills s1
  join public.skill_relations r on r.skill_id = s1.id
  join public.skills s2 on s2.id = r.related_skill_id
  where s1.normalized_name = any (p_skills)
    and not (s2.normalized_name = any (p_skills))
  group by s2.id, s2.name
  order by total_weight desc
  limit p_limit;
$$;

-- ---------------------------------------------------------------------------
-- Location rollups (active jobs only)
-- ---------------------------------------------------------------------------
create or replace function public.popular_locations(p_limit int default 20)
returns table (
  location_id bigint,
  country text,
  state text,
  city text,
  formatted text,
  active_job_count bigint
)
language sql
stable
as $$
  select l.id, l.country, l.state, l.city, l.formatted, count(j.id) as active_job_count
  from public.locations l
  join public.jobs j on j.location_id = l.id and j.status = 1
  group by l.id, l.country, l.state, l.city, l.formatted
  order by active_job_count desc
  limit p_limit;
$$;

create or replace function public.location_countries()
returns table (country text, active_job_count bigint)
language sql
stable
as $$
  select l.country, count(j.id) as active_job_count
  from public.locations l
  join public.jobs j on j.location_id = l.id and j.status = 1
  where l.country is not null
  group by l.country
  order by active_job_count desc;
$$;

create or replace function public.location_states(p_country text)
returns table (state text, active_job_count bigint)
language sql
stable
as $$
  select l.state, count(j.id) as active_job_count
  from public.locations l
  join public.jobs j on j.location_id = l.id and j.status = 1
  where l.country ilike p_country
    and l.state is not null
  group by l.state
  order by active_job_count desc;
$$;

create or replace function public.location_cities(p_country text, p_state text default null)
returns table (city text, active_job_count bigint)
language sql
stable
as $$
  select l.city, count(j.id) as active_job_count
  from public.locations l
  join public.jobs j on j.location_id = l.id and j.status = 1
  where l.country ilike p_country
    and (p_state is null or l.state ilike p_state)
    and l.city is not null
  group by l.city
  order by active_job_count desc;
$$;

commit;
