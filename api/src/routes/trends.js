import { Hono } from "hono";
import { getSupabase } from "../supabase.js";
import { COLLECTIONS, getTypesense, pagination } from "../typesense.js";

export const trends = new Hono();

trends.get("/jobs", async (c) => {
  const limit = Math.min(100, Math.max(1, Number(c.req.query("limit")) || 20));
  const days = Math.max(1, Number(c.req.query("days")) || 14);
  const sb = getSupabase();
  const { data, error } = await sb.rpc("trending_jobs", {
    p_days: days,
    p_limit: limit,
  });
  if (error) throw new Error(error.message);
  return c.json({ items: data || [], days });
});

trends.get("/skills", async (c) => {
  const limit = Math.min(100, Math.max(1, Number(c.req.query("limit")) || 20));
  const days = Math.max(1, Number(c.req.query("days")) || 30);
  const sb = getSupabase();
  const { data, error } = await sb.rpc("trending_skills_by_window", {
    p_days: days,
    p_limit: limit,
  });
  if (error) throw new Error(error.message);
  return c.json({ items: data || [], days });
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
