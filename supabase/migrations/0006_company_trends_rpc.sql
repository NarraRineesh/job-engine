-- Live company trends derived from jobs (company_trends table may be empty).
-- p_slug null  → top 100 companies by active job count (current month label).
-- p_slug set   → monthly series for that company with MoM growth.

begin;

create or replace function public.company_trends_live(
  p_slug text default null,
  p_months int default 6
)
returns table (
  company_id bigint,
  company_slug text,
  company_name text,
  month date,
  job_count bigint,
  growth_percentage numeric
)
language plpgsql
stable
as $$
declare
  months int := greatest(1, least(coalesce(p_months, 6), 24));
begin
  if p_slug is null then
    return query
    select
      c.id,
      c.slug,
      c.name,
      date_trunc('month', now())::date,
      count(*)::bigint,
      null::numeric
    from public.jobs j
    join public.companies c on c.id = j.company_id
    where j.status = 1
    group by c.id, c.slug, c.name
    order by count(*) desc
    limit 100;
    return;
  end if;

  return query
  with monthly as (
    select
      c.id as company_id,
      c.slug as company_slug,
      c.name as company_name,
      date_trunc('month', coalesce(j.last_scraped_at, j.created_at))::date as month,
      count(*)::bigint as job_count
    from public.jobs j
    join public.companies c on c.id = j.company_id
    where c.slug = p_slug
      and coalesce(j.last_scraped_at, j.created_at)
          >= date_trunc('month', now()) - make_interval(months => months)
    group by c.id, c.slug, c.name,
             date_trunc('month', coalesce(j.last_scraped_at, j.created_at))::date
  ),
  with_growth as (
    select
      m.*,
      lag(m.job_count) over (order by m.month) as prev_count
    from monthly m
  )
  select
    company_id,
    company_slug,
    company_name,
    month,
    job_count,
    case
      when prev_count is null or prev_count = 0 then null
      else round(((job_count - prev_count)::numeric / prev_count::numeric) * 100, 2)
    end
  from with_growth
  order by month;
end;
$$;

grant execute on function public.company_trends_live(text, int) to anon, authenticated, service_role;

commit;
