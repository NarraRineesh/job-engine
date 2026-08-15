/**
 * Sync MongoDB jobs / companies / skills into Typesense.
 *
 * Usage: npm run index
 * Env:
 *   INDEX_RECREATE=1  drop+recreate collections (default 0)
 *   INDEX_PAGE=80     jobs per batch
 *   INDEX_AFTER_ID=   resume after this job _id (exclusive)
 */
import { getDb } from "../src/mongodb.js";
import {
  COLLECTIONS,
  ensureCollections,
  getTypesense,
} from "../src/typesense.js";

const PAGE = Math.min(500, Math.max(20, Number(process.env.INDEX_PAGE) || 80));

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

async function indexJobs(db, ts, skillCounts, companyCounts) {
  let total = 0;
  let lastId = process.env.INDEX_AFTER_ID || null;
  const coll = db.collection("jobs");
  for (;;) {
    const filter = lastId != null ? { _id: { $gt: lastId } } : {};
    const data = await coll.find(filter).sort({ _id: 1 }).limit(PAGE).toArray();
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
    if (total % 400 === 0 || data.length < PAGE) {
      console.log(`[index] jobs ${total} last=${lastId}`);
    }
    if (data.length < PAGE) break;
  }
  return total;
}

async function indexCompanies(db, ts, companyCounts) {
  let total = 0;
  let lastId = null;
  const coll = db.collection("companies");
  for (;;) {
    const filter = lastId != null ? { _id: { $gt: lastId } } : {};
    const rows = await coll.find(filter).sort({ _id: 1 }).limit(PAGE).toArray();
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
    if (rows.length < PAGE) break;
  }
  console.log(`[index] companies ${total}`);
  return total;
}

async function indexSkills(db, ts, skillCounts) {
  let total = 0;
  let lastId = null;
  const coll = db.collection("skills");
  for (;;) {
    const filter = lastId != null ? { _id: { $gt: lastId } } : {};
    const rows = await coll.find(filter).sort({ _id: 1 }).limit(PAGE).toArray();
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
    if (rows.length < PAGE) break;
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

async function main() {
  const db = await getDb();
  const ts = getTypesense();
  const recreate = process.env.INDEX_RECREATE === "1";
  const skipJobs = process.env.INDEX_SKIP_JOBS === "1";

  await ensureCollections(ts, { recreate: recreate && !skipJobs });

  let companyCounts = new Map();
  const skillCounts = new Map();
  let jobs = 0;
  if (skipJobs) {
    companyCounts = await companyCountsFromTypesense(ts);
  } else {
    console.log(`[index] paging jobs (page=${PAGE})…`);
    jobs = await indexJobs(db, ts, skillCounts, companyCounts);
  }

  const companies = await indexCompanies(db, ts, companyCounts);
  const skills = await indexSkills(db, ts, skillCounts);

  console.log(
    `[index] done jobs=${jobs} companies=${companies} skills=${skills}`,
  );
  process.exit(0);
}

main().catch((err) => {
  console.error("[index] failed:", err);
  process.exit(1);
});
