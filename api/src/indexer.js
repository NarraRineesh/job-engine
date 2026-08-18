/**
 * Sync MongoDB jobs / companies / skills into Typesense.
 * Used by POST /v1/index and `npm run index`.
 */
import { getDb } from "./mongodb.js";
import { COLLECTIONS, ensureCollections, getTypesense } from "./typesense.js";

const DEFAULT_PAGE = 80;

let run = {
  status: "idle",
  started_at: null,
  finished_at: null,
  jobs: 0,
  companies: 0,
  skills: 0,
  last_id: null,
  error: null,
};

let inflight = null;

function pageSize(page) {
  return Math.min(500, Math.max(20, Number(page) || DEFAULT_PAGE));
}

function toUnix(value) {
  if (!value) return 0;
  const ms = value instanceof Date ? value.getTime() : Date.parse(value);
  return Number.isFinite(ms) ? Math.floor(ms / 1000) : 0;
}

function omitNull(obj) {
  const out = {};
  for (const [k, v] of Object.entries(obj)) {
    if (v !== null && v !== undefined) out[k] = v;
  }
  return out;
}

export function getIndexStatus() {
  return { ...run };
}

export function startIndex(opts = {}) {
  if (inflight) {
    const err = new Error("index already running");
    err.status = 409;
    err.current = getIndexStatus();
    throw err;
  }
  inflight = runIndex(opts).finally(() => {
    inflight = null;
  });
  return getIndexStatus();
}

export async function runIndex({
  recreate = false,
  skipJobs = false,
  page = DEFAULT_PAGE,
  afterId = null,
} = {}) {
  run = {
    status: "running",
    started_at: new Date().toISOString(),
    finished_at: null,
    jobs: 0,
    companies: 0,
    skills: 0,
    last_id: afterId,
    error: null,
  };
  const size = pageSize(page);
  try {
    const db = await getDb();
    const ts = getTypesense();
    await ensureCollections(ts, { recreate: recreate && !skipJobs });

    const companyCounts = new Map();
    const skillCounts = new Map();
    if (skipJobs) {
      const counts = await companyCountsFromTypesense(ts);
      for (const [k, v] of counts) companyCounts.set(k, v);
    } else {
      console.log(`[index] paging jobs (page=${size})…`);
      run.jobs = await indexJobs(db, ts, skillCounts, companyCounts, size, afterId);
    }

    run.companies = await indexCompanies(db, ts, companyCounts, size);
    run.skills = await indexSkills(db, ts, skillCounts, size);
    run.status = "done";
    run.finished_at = new Date().toISOString();
    console.log(
      `[index] done jobs=${run.jobs} companies=${run.companies} skills=${run.skills}`,
    );
    return getIndexStatus();
  } catch (err) {
    run.status = "error";
    run.error = err?.message || String(err);
    run.finished_at = new Date().toISOString();
    console.error("[index] failed:", err);
    throw err;
  }
}

async function indexJobs(db, ts, skillCounts, companyCounts, size, afterId) {
  let total = 0;
  let lastId = afterId || null;
  const coll = db.collection("jobs");
  for (;;) {
    const filter = lastId != null ? { _id: { $gt: lastId } } : {};
    const data = await coll.find(filter).sort({ _id: 1 }).limit(size).toArray();
    if (!data.length) break;

    const docs = data.map((j) => {
      const slug = j.company?.slug || "unknown";
      if (j.status === 1) {
        companyCounts.set(slug, (companyCounts.get(slug) || 0) + 1);
      }
      const skills = Array.isArray(j.skills) ? j.skills : [];
      for (const n of skills) {
        skillCounts.set(n, (skillCounts.get(n) || 0) + 1);
      }
      return omitNull({
        id: j._id,
        title: j.title || "",
        normalized_title: j.normalized_title || "",
        company_slug: slug,
        company_name: j.company?.name || null,
        ats: j.ats ?? null,
        employment_type: j.employment_type ?? null,
        work_mode: j.work_mode ?? null,
        seniority: j.seniority ?? null,
        country: j.location?.country || null,
        state: j.location?.state || null,
        city: j.location?.city || null,
        skills,
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
    lastId = data[data.length - 1]._id;
    run.jobs = total;
    run.last_id = lastId;
    if (total % 400 === 0 || data.length < size) {
      console.log(`[index] jobs ${total} last=${lastId}`);
    }
    if (data.length < size) break;
  }
  return total;
}

async function indexCompanies(db, ts, companyCounts, size) {
  let total = 0;
  let lastId = null;
  const coll = db.collection("companies");
  for (;;) {
    const filter = lastId != null ? { _id: { $gt: lastId } } : {};
    const rows = await coll.find(filter).sort({ _id: 1 }).limit(size).toArray();
    if (!rows.length) break;
    const docs = rows.map((c) =>
      omitNull({
        id: c.slug || c._id,
        slug: c.slug || c._id,
        name: c.name || c.slug || c._id,
        industry: c.industry || null,
        website: c.website || null,
        logo: c.logo || null,
        active_job_count: companyCounts.get(c.slug || c._id) || 0,
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
    lastId = rows[rows.length - 1]._id;
    run.companies = total;
    if (rows.length < size) break;
  }
  console.log(`[index] companies ${total}`);
  return total;
}

async function indexSkills(db, ts, skillCounts, size) {
  let total = 0;
  let lastId = null;
  const coll = db.collection("skills");
  for (;;) {
    const filter = lastId != null ? { _id: { $gt: lastId } } : {};
    const rows = await coll.find(filter).sort({ _id: 1 }).limit(size).toArray();
    if (!rows.length) break;
    const docs = rows.map((s) => {
      const normalized = (s.normalized_name || s.name || s._id || "").toLowerCase();
      return {
        id: normalized,
        name: s.name || normalized,
        normalized_name: normalized,
        active_job_count: skillCounts.get(normalized) || 0,
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
    lastId = rows[rows.length - 1]._id;
    run.skills = total;
    if (rows.length < size) break;
  }
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
