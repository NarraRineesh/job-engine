/**
 * Sync Supabase jobs / companies / skills into Typesense.
 *
 * Usage: npm run index
 */
import { getSupabaseIndexer } from "../src/supabase.js";
import {
  COLLECTIONS,
  ensureCollections,
  getTypesense,
} from "../src/typesense.js";

const PAGE = 500;

function toUnix(iso) {
  if (!iso) return 0;
  const ms = Date.parse(iso);
  return Number.isFinite(ms) ? Math.floor(ms / 1000) : 0;
}

async function fetchAllJobSkillNames(sb) {
  /** @type {Map<string, string[]>} */
  const byJob = new Map();
  let from = 0;
  for (;;) {
    const { data, error } = await sb
      .from("job_skills")
      .select("job_id, skills(normalized_name, name)")
      .range(from, from + PAGE - 1);
    if (error) throw new Error(`job_skills: ${error.message}`);
    if (!data?.length) break;
    for (const row of data) {
      const name =
        row.skills?.normalized_name || row.skills?.name || null;
      if (!name) continue;
      const list = byJob.get(row.job_id) || [];
      list.push(String(name).toLowerCase());
      byJob.set(row.job_id, list);
    }
    if (data.length < PAGE) break;
    from += PAGE;
  }
  for (const [jid, list] of byJob) {
    byJob.set(jid, [...new Set(list)]);
  }
  return byJob;
}

async function indexJobs(sb, ts, skillMap) {
  let from = 0;
  let total = 0;
  for (;;) {
    const { data, error } = await sb
      .from("jobs")
      .select(
        "id,title,normalized_title,department,team,ats,employment_type,work_mode,seniority,status,posted_at,apply_url,company_id,location_id,companies(slug,name),locations(country,state,city)",
      )
      .range(from, from + PAGE - 1);
    if (error) throw new Error(`jobs: ${error.message}`);
    if (!data?.length) break;

    const docs = data.map((j) => ({
      id: j.id,
      title: j.title || "",
      normalized_title: j.normalized_title || "",
      company_slug: j.companies?.slug || `company:${j.company_id || "unknown"}`,
      company_name: j.companies?.name || null,
      ats: j.ats ?? null,
      employment_type: j.employment_type ?? null,
      work_mode: j.work_mode ?? null,
      seniority: j.seniority ?? null,
      country: j.locations?.country || null,
      state: j.locations?.state || null,
      city: j.locations?.city || null,
      skills: skillMap.get(j.id) || [],
      status: j.status ?? 1,
      posted_at: toUnix(j.posted_at),
      apply_url: j.apply_url || null,
      department: j.department || null,
      team: j.team || null,
    }));

    const result = await ts
      .collections(COLLECTIONS.jobs)
      .documents()
      .import(docs, { action: "upsert" });
    const rows = Array.isArray(result) ? result : [];
    const failed = rows.filter((r) => r && r.success === false);
    if (failed.length) {
      console.warn(`[index] jobs batch failures: ${failed.length}`, failed[0]);
    }
    total += docs.length;
    console.log(`[index] jobs ${total}`);
    if (data.length < PAGE) break;
    from += PAGE;
  }
  return total;
}

async function indexCompanies(sb, ts) {
  /** active job counts by company_id */
  const counts = new Map();
  let from = 0;
  for (;;) {
    const { data, error } = await sb
      .from("jobs")
      .select("company_id")
      .eq("status", 1)
      .not("company_id", "is", null)
      .range(from, from + PAGE - 1);
    if (error) throw new Error(`jobs count: ${error.message}`);
    if (!data?.length) break;
    for (const row of data) {
      counts.set(row.company_id, (counts.get(row.company_id) || 0) + 1);
    }
    if (data.length < PAGE) break;
    from += PAGE;
  }

  from = 0;
  let total = 0;
  for (;;) {
    const { data, error } = await sb
      .from("companies")
      .select("id,slug,name,industry,website,logo")
      .range(from, from + PAGE - 1);
    if (error) throw new Error(`companies: ${error.message}`);
    if (!data?.length) break;

    const docs = data.map((c) => ({
      id: c.slug,
      slug: c.slug,
      name: c.name || c.slug,
      industry: c.industry || null,
      website: c.website || null,
      logo: c.logo || null,
      active_job_count: counts.get(c.id) || 0,
    }));

    await ts
      .collections(COLLECTIONS.companies)
      .documents()
      .import(docs, { action: "upsert" });
    total += docs.length;
    console.log(`[index] companies ${total}`);
    if (data.length < PAGE) break;
    from += PAGE;
  }
  return total;
}

async function indexSkills(sb, ts) {
  /** active job counts by skill_id */
  const counts = new Map();
  let from = 0;
  for (;;) {
    const { data, error } = await sb
      .from("job_skills")
      .select("skill_id, jobs!inner(status)")
      .eq("jobs.status", 1)
      .range(from, from + PAGE - 1);
    if (error) {
      // fallback without inner join filter
      const res = await sb
        .from("job_skills")
        .select("skill_id")
        .range(from, from + PAGE - 1);
      if (res.error) throw new Error(`job_skills skills: ${res.error.message}`);
      if (!res.data?.length) break;
      for (const row of res.data) {
        counts.set(row.skill_id, (counts.get(row.skill_id) || 0) + 1);
      }
      if (res.data.length < PAGE) break;
      from += PAGE;
      continue;
    }
    if (!data?.length) break;
    for (const row of data) {
      counts.set(row.skill_id, (counts.get(row.skill_id) || 0) + 1);
    }
    if (data.length < PAGE) break;
    from += PAGE;
  }

  from = 0;
  let total = 0;
  for (;;) {
    const { data, error } = await sb
      .from("skills")
      .select("id,name,normalized_name")
      .range(from, from + PAGE - 1);
    if (error) throw new Error(`skills: ${error.message}`);
    if (!data?.length) break;

    const docs = data.map((s) => {
      const normalized = (s.normalized_name || s.name || "").toLowerCase();
      return {
        id: normalized,
        name: s.name || normalized,
        normalized_name: normalized,
        active_job_count: counts.get(s.id) || 0,
      };
    });

    await ts
      .collections(COLLECTIONS.skills)
      .documents()
      .import(docs, { action: "upsert" });
    total += docs.length;
    console.log(`[index] skills ${total}`);
    if (data.length < PAGE) break;
    from += PAGE;
  }
  return total;
}

async function main() {
  const sb = getSupabaseIndexer();
  const ts = getTypesense();
  await ensureCollections(ts);

  console.log("[index] loading job_skills…");
  const skillMap = await fetchAllJobSkillNames(sb);
  console.log(`[index] jobs with skills: ${skillMap.size}`);

  const jobs = await indexJobs(sb, ts, skillMap);
  const companies = await indexCompanies(sb, ts);
  const skills = await indexSkills(sb, ts);

  console.log(
    `[index] done jobs=${jobs} companies=${companies} skills=${skills}`,
  );
}

main().catch((err) => {
  console.error("[index] failed:", err);
  process.exit(1);
});
