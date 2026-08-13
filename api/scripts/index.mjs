/**
 * Sync Supabase jobs / companies / skills into Typesense.
 *
 * Usage: npm run index
 * Env:
 *   INDEX_RECREATE=1  drop+recreate collections (default 1 on first clean run; set 0 to resume)
 *   INDEX_SKIP_JOBS=1 only refresh companies/skills (reuse existing jobs docs)
 */
import { getSupabaseIndexer } from "../src/supabase.js";
import {
  COLLECTIONS,
  ensureCollections,
  getTypesense,
} from "../src/typesense.js";

const PAGE = 200;

function toUnix(iso) {
  if (!iso) return 0;
  const ms = Date.parse(iso);
  return Number.isFinite(ms) ? Math.floor(ms / 1000) : 0;
}

function omitNull(obj) {
  const out = {};
  for (const [k, v] of Object.entries(obj)) {
    if (v !== null && v !== undefined) out[k] = v;
  }
  return out;
}

async function pageOrdered(sb, table, select, onRows) {
  let lastId = null;
  let total = 0;
  for (;;) {
    let q = sb.from(table).select(select).order("id", { ascending: true }).limit(PAGE);
    if (lastId != null) q = q.gt("id", lastId);
    const { data, error } = await q;
    if (error) throw new Error(`${table}: ${error.message}`);
    if (!data?.length) break;
    await onRows(data);
    total += data.length;
    lastId = data[data.length - 1].id;
    if (data.length < PAGE) break;
  }
  return total;
}

async function fetchAllJobSkillNames(sb) {
  /** @type {Map<string, string[]>} */
  const byJob = new Map();
  let from = 0;
  for (;;) {
    const { data, error } = await sb
      .from("job_skills")
      .select("job_id,skill_id,skills(normalized_name,name)")
      .order("job_id", { ascending: true })
      .order("skill_id", { ascending: true })
      .range(from, from + PAGE - 1);
    if (error) throw new Error(`job_skills: ${error.message}`);
    if (!data?.length) break;
    for (const row of data) {
      const name = row.skills?.normalized_name || row.skills?.name || null;
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

async function indexJobs(sb, ts, skillMap, companyCounts) {
  let total = 0;
  let lastId = null;
  for (;;) {
    let q = sb
      .from("jobs")
      .select(
        "id,title,normalized_title,department,team,ats,employment_type,work_mode,seniority,status,posted_at,apply_url,company_id,companies(slug,name),locations(country,state,city)",
      )
      .order("id", { ascending: true })
      .limit(PAGE);
    if (lastId != null) q = q.gt("id", lastId);
    const { data, error } = await q;
    if (error) throw new Error(`jobs: ${error.message}`);
    if (!data?.length) break;

    const docs = data.map((j) => {
      const slug = j.companies?.slug || `company:${j.company_id || "unknown"}`;
      if (j.status === 1) {
        companyCounts.set(slug, (companyCounts.get(slug) || 0) + 1);
      }
      return omitNull({
        id: j.id,
        title: j.title || "",
        normalized_title: j.normalized_title || "",
        company_slug: slug,
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
      });
    });

    try {
      await ts.collections(COLLECTIONS.jobs).documents().import(docs, {
        action: "upsert",
      });
    } catch (err) {
      const first = (err.importResults || []).find((r) => r && r.success === false);
      console.warn(`[index] jobs import @${lastId}:`, first?.error || err.message);
    }

    total += docs.length;
    lastId = data[data.length - 1].id;
    if (total % 2000 === 0 || data.length < PAGE) {
      console.log(`[index] jobs ${total}`);
    }
    if (data.length < PAGE) break;
  }
  return total;
}

async function indexCompanies(sb, ts, companyCounts) {
  let total = 0;
  await pageOrdered(sb, "companies", "id,slug,name,industry,website,logo", async (rows) => {
    const docs = rows.map((c) =>
      omitNull({
        id: c.slug,
        slug: c.slug,
        name: c.name || c.slug,
        industry: c.industry || null,
        website: c.website || null,
        logo: c.logo || null,
        active_job_count: companyCounts.get(c.slug) || 0,
      }),
    );
    try {
      await ts.collections(COLLECTIONS.companies).documents().import(docs, {
        action: "upsert",
      });
    } catch (err) {
      console.warn(`[index] companies import:`, err.message);
    }
    total += docs.length;
  });
  console.log(`[index] companies ${total}`);
  return total;
}

async function indexSkills(sb, ts, skillMap) {
  const counts = new Map();
  for (const names of skillMap.values()) {
    for (const n of names) {
      counts.set(n, (counts.get(n) || 0) + 1);
    }
  }

  let total = 0;
  await pageOrdered(sb, "skills", "id,name,normalized_name", async (rows) => {
    const docs = rows.map((s) => {
      const normalized = (s.normalized_name || s.name || "").toLowerCase();
      return {
        id: normalized,
        name: s.name || normalized,
        normalized_name: normalized,
        active_job_count: counts.get(normalized) || 0,
      };
    });
    try {
      await ts.collections(COLLECTIONS.skills).documents().import(docs, {
        action: "upsert",
      });
    } catch (err) {
      console.warn(`[index] skills import:`, err.message);
    }
    total += docs.length;
  });
  console.log(`[index] skills ${total}`);
  return total;
}

async function companyCountsFromTypesense(ts) {
  const counts = new Map();
  const result = await ts.collections(COLLECTIONS.jobs).documents().search({
    q: "*",
    query_by: "title",
    filter_by: "status:=1",
    facet_by: "company_slug",
    max_facet_values: 250000,
    per_page: 0,
  });
  for (const f of result.facet_counts || []) {
    if (f.field_name !== "company_slug") continue;
    for (const c of f.counts || []) {
      counts.set(c.value, c.count);
    }
  }
  console.log(`[index] company facets from typesense: ${counts.size}`);
  return counts;
}

async function main() {
  const sb = getSupabaseIndexer();
  const ts = getTypesense();
  const recreate = process.env.INDEX_RECREATE !== "0";
  const skipJobs = process.env.INDEX_SKIP_JOBS === "1";

  await ensureCollections(ts, { recreate: recreate && !skipJobs });

  console.log("[index] loading job_skills…");
  const skillMap = await fetchAllJobSkillNames(sb);
  console.log(`[index] jobs with skills: ${skillMap.size}`);

  /** @type {Map<string, number>} */
  let companyCounts = new Map();
  let jobs = 0;
  if (skipJobs) {
    companyCounts = await companyCountsFromTypesense(ts);
  } else {
    jobs = await indexJobs(sb, ts, skillMap, companyCounts);
  }

  const companies = await indexCompanies(sb, ts, companyCounts);
  const skills = await indexSkills(sb, ts, skillMap);

  console.log(
    `[index] done jobs=${jobs} companies=${companies} skills=${skills}`,
  );
}

main().catch((err) => {
  console.error("[index] failed:", err);
  process.exit(1);
});
