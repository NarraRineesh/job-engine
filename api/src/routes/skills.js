import { Hono } from "hono";
import {
  COLLECTIONS,
  escapeFilterValue,
  getTypesense,
  pagination,
} from "../typesense.js";
import { trendingSkills } from "../mongodb.js";

export const skills = new Hono();

function mapSkill(doc) {
  if (!doc) return null;
  return {
    id: doc.id,
    name: doc.name,
    normalized_name: doc.normalized_name,
    active_job_count: doc.active_job_count ?? 0,
  };
}

skills.get("/trending", async (c) => {
  const limit = Math.min(100, Math.max(1, Number(c.req.query("limit")) || 20));
  const days = Math.max(1, Number(c.req.query("days")) || 30);
  const items = await trendingSkills(days, limit);
  return c.json({ items, days });
});

skills.get("/", async (c) => {
  const q = c.req.query("q") || "*";
  const { limit, page } = pagination(c.req.query());
  const client = getTypesense();
  const result = await client.collections(COLLECTIONS.skills).documents().search({
    q,
    query_by: "name,normalized_name",
    per_page: limit,
    page,
    sort_by: "active_job_count:desc",
  });
  return c.json({
    items: (result.hits || []).map((h) => mapSkill(h.document)),
    found: result.found ?? 0,
    page: result.page ?? page,
    limit,
  });
});

skills.get("/:name", async (c) => {
  const name = c.req.param("name").toLowerCase();
  const client = getTypesense();
  try {
    const doc = await client
      .collections(COLLECTIONS.skills)
      .documents(name)
      .retrieve();
    return c.json({ skill: mapSkill(doc) });
  } catch (err) {
    if (err?.httpStatus === 404) {
      const result = await client
        .collections(COLLECTIONS.skills)
        .documents()
        .search({
          q: name,
          query_by: "normalized_name,name",
          filter_by: `normalized_name:=\`${escapeFilterValue(name)}\``,
          per_page: 1,
        });
      const hit = result.hits?.[0]?.document;
      if (!hit) return c.json({ error: "not_found" }, 404);
      return c.json({ skill: mapSkill(hit) });
    }
    throw err;
  }
});

skills.get("/:name/jobs", async (c) => {
  const name = c.req.param("name").toLowerCase();
  const q = c.req.query("q") || "*";
  const { limit, page } = pagination(c.req.query());
  const client = getTypesense();
  const result = await client.collections(COLLECTIONS.jobs).documents().search({
    q,
    query_by: "title,normalized_title,company_name",
    filter_by: `skills:=\`${escapeFilterValue(name)}\` && status:=1`,
    per_page: limit,
    page,
    sort_by: "posted_at:desc",
  });
  return c.json({
    items: (result.hits || []).map((h) => h.document),
    found: result.found ?? 0,
    page: result.page ?? page,
    limit,
  });
});
