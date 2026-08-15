import { Hono } from "hono";
import {
  COLLECTIONS,
  escapeFilterValue,
  getTypesense,
  pagination,
} from "../typesense.js";
import {
  featuredJobs,
  getAnalytics,
  incrementAnalytics,
  trendingJobs,
} from "../mongodb.js";
import {
  labelAts,
  labelEmployment,
  labelStatus,
  labelWorkMode,
  toAts,
  toStatus,
  toWorkMode,
} from "../enums.js";

export const jobs = new Hono();

function mapJobHit(doc) {
  if (!doc) return null;
  return {
    id: doc.id,
    title: doc.title,
    normalized_title: doc.normalized_title ?? null,
    company_slug: doc.company_slug,
    company_name: doc.company_name ?? null,
    department: doc.department ?? null,
    team: doc.team ?? null,
    ats: doc.ats ?? null,
    ats_label: labelAts(doc.ats),
    employment_type: doc.employment_type ?? null,
    employment_type_label: labelEmployment(doc.employment_type),
    work_mode: doc.work_mode ?? null,
    work_mode_label: labelWorkMode(doc.work_mode),
    seniority: doc.seniority ?? null,
    country: doc.country ?? null,
    state: doc.state ?? null,
    city: doc.city ?? null,
    skills: doc.skills ?? [],
    status: doc.status ?? null,
    status_label: labelStatus(doc.status),
    posted_at: doc.posted_at ? new Date(doc.posted_at * 1000).toISOString() : null,
    apply_url: doc.apply_url ?? null,
  };
}

function buildJobFilter(query) {
  const parts = [];
  const status = toStatus(query.status ?? "active");
  if (status != null) parts.push(`status:=${status}`);

  const ats = toAts(query.ats);
  if (ats != null) parts.push(`ats:=${ats}`);

  const workMode = toWorkMode(query.work_mode);
  if (workMode != null) parts.push(`work_mode:=${workMode}`);

  if (query.company) {
    parts.push(`company_slug:=\`${escapeFilterValue(query.company)}\``);
  }
  if (query.country) {
    parts.push(`country:=\`${escapeFilterValue(query.country)}\``);
  }
  if (query.skill) {
    parts.push(`skills:=\`${escapeFilterValue(query.skill)}\``);
  }
  return parts.length ? parts.join(" && ") : undefined;
}

jobs.get("/featured", async (c) => {
  const limit = Math.min(100, Math.max(1, Number(c.req.query("limit")) || 20));
  const items = await featuredJobs(limit);
  return c.json({ items });
});

jobs.get("/trending", async (c) => {
  const limit = Math.min(100, Math.max(1, Number(c.req.query("limit")) || 20));
  const days = Math.max(1, Number(c.req.query("days")) || 14);
  const items = await trendingJobs(days, limit);
  return c.json({ items, days });
});

jobs.get("/", async (c) => {
  const q = c.req.query("q") || "*";
  const { limit, page } = pagination(c.req.query());
  const filter_by = buildJobFilter(c.req.query());
  const client = getTypesense();
  const result = await client.collections(COLLECTIONS.jobs).documents().search({
    q,
    query_by: "title,normalized_title,company_name,skills",
    filter_by,
    per_page: limit,
    page,
    sort_by: "posted_at:desc",
  });
  return c.json({
    items: (result.hits || []).map((h) => mapJobHit(h.document)),
    found: result.found ?? 0,
    page: result.page ?? page,
    limit,
  });
});

jobs.get("/:id", async (c) => {
  const id = c.req.param("id");
  const client = getTypesense();
  let doc;
  try {
    doc = await client.collections(COLLECTIONS.jobs).documents(id).retrieve();
  } catch (err) {
    if (String(err?.httpStatus || err?.message).includes("404") || err?.httpStatus === 404) {
      return c.json({ error: "not_found" }, 404);
    }
    throw err;
  }

  const analytics = await getAnalytics(id);

  return c.json({
    job: mapJobHit(doc),
    analytics: {
      job_id: analytics.job_id || analytics._id || id,
      views: analytics.views || 0,
      clicks: analytics.clicks || 0,
      applications: analytics.applications || 0,
      saved: analytics.saved || 0,
      updated_at: analytics.updated_at || null,
    },
  });
});

jobs.get("/:id/similar", async (c) => {
  const id = c.req.param("id");
  const limit = Math.min(100, Math.max(1, Number(c.req.query("limit")) || 20));
  const client = getTypesense();

  let doc;
  try {
    doc = await client.collections(COLLECTIONS.jobs).documents(id).retrieve();
  } catch (err) {
    if (err?.httpStatus === 404) return c.json({ error: "not_found" }, 404);
    throw err;
  }

  const skillFilter =
    Array.isArray(doc.skills) && doc.skills.length
      ? `skills:=[${doc.skills
          .slice(0, 8)
          .map((s) => `\`${escapeFilterValue(s)}\``)
          .join(",")}]`
      : undefined;

  const result = await client.collections(COLLECTIONS.jobs).documents().search({
    q: doc.title || "*",
    query_by: "title,skills,normalized_title",
    filter_by: [skillFilter, `id:!=\`${escapeFilterValue(id)}\``, "status:=1"]
      .filter(Boolean)
      .join(" && "),
    per_page: limit,
    page: 1,
  });

  return c.json({
    items: (result.hits || []).map((h) => mapJobHit(h.document)),
    found: result.found ?? 0,
  });
});

jobs.get("/:id/analytics", async (c) => {
  const id = c.req.param("id");
  const data = await getAnalytics(id);
  return c.json({
    job_id: data.job_id || data._id || id,
    views: data.views || 0,
    clicks: data.clicks || 0,
    applications: data.applications || 0,
    saved: data.saved || 0,
    updated_at: data.updated_at || null,
  });
});

jobs.post("/:id/analytics", async (c) => {
  const id = c.req.param("id");
  const body = await c.req.json().catch(() => ({}));
  const metric = String(body.metric || "").toLowerCase();
  if (!["views", "clicks", "applications", "saved"].includes(metric)) {
    return c.json(
      { error: "metric must be views|clicks|applications|saved" },
      400,
    );
  }
  const data = await incrementAnalytics(id, metric);
  return c.json({
    job_id: data.job_id || data._id || id,
    views: data.views || 0,
    clicks: data.clicks || 0,
    applications: data.applications || 0,
    saved: data.saved || 0,
    updated_at: data.updated_at || null,
  });
});
