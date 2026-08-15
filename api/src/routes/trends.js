import { Hono } from "hono";
import { COLLECTIONS, getTypesense, pagination } from "../typesense.js";
import { trendingJobs, trendingSkills } from "../mongodb.js";

export const trends = new Hono();

trends.get("/jobs", async (c) => {
  const limit = Math.min(100, Math.max(1, Number(c.req.query("limit")) || 20));
  const days = Math.max(1, Number(c.req.query("days")) || 14);
  const items = await trendingJobs(days, limit);
  return c.json({ items, days });
});

trends.get("/skills", async (c) => {
  const limit = Math.min(100, Math.max(1, Number(c.req.query("limit")) || 20));
  const days = Math.max(1, Number(c.req.query("days")) || 30);
  const items = await trendingSkills(days, limit);
  return c.json({ items, days });
});

/** Ranked companies by active_job_count (from Typesense index). */
trends.get("/companies", async (c) => {
  const { limit, page } = pagination(c.req.query());
  const client = getTypesense();
  const result = await client
    .collections(COLLECTIONS.companies)
    .documents()
    .search({
      q: "*",
      query_by: "name",
      per_page: limit,
      page,
      sort_by: "active_job_count:desc",
    });
  return c.json({
    items: (result.hits || []).map((h) => ({
      company_slug: h.document.slug,
      company_name: h.document.name,
      job_count: h.document.active_job_count ?? 0,
      industry: h.document.industry ?? null,
    })),
    found: result.found ?? 0,
    page: result.page ?? page,
    limit,
  });
});
