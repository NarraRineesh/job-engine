import { Hono } from "hono";
import {
  COLLECTIONS,
  escapeFilterValue,
  getTypesense,
  pagination,
} from "../typesense.js";
import { companyTrends } from "../mongodb.js";

export const companies = new Hono();

function mapCompany(doc) {
  if (!doc) return null;
  return {
    id: doc.id,
    slug: doc.slug,
    name: doc.name,
    industry: doc.industry ?? null,
    website: doc.website ?? null,
    logo: doc.logo ?? null,
    active_job_count: doc.active_job_count ?? 0,
  };
}

companies.get("/", async (c) => {
  const q = c.req.query("q") || "*";
  const { limit, page } = pagination(c.req.query());
  const client = getTypesense();
  const result = await client
    .collections(COLLECTIONS.companies)
    .documents()
    .search({
      q,
      query_by: "name,slug,industry",
      per_page: limit,
      page,
      sort_by: "active_job_count:desc",
    });
  return c.json({
    items: (result.hits || []).map((h) => mapCompany(h.document)),
    found: result.found ?? 0,
    page: result.page ?? page,
    limit,
  });
});

companies.get("/:slug", async (c) => {
  const slug = c.req.param("slug");
  const client = getTypesense();
  try {
    const doc = await client
      .collections(COLLECTIONS.companies)
      .documents(slug)
      .retrieve();
    return c.json({ company: mapCompany(doc) });
  } catch (err) {
    if (err?.httpStatus === 404) return c.json({ error: "not_found" }, 404);
    throw err;
  }
});

companies.get("/:slug/jobs", async (c) => {
  const slug = c.req.param("slug");
  const q = c.req.query("q") || "*";
  const { limit, page } = pagination(c.req.query());
  const client = getTypesense();
  const result = await client.collections(COLLECTIONS.jobs).documents().search({
    q,
    query_by: "title,normalized_title,skills",
    filter_by: `company_slug:=\`${escapeFilterValue(slug)}\` && status:=1`,
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

companies.get("/:slug/trends", async (c) => {
  const slug = c.req.param("slug");
  const months = Math.min(24, Math.max(1, Number(c.req.query("months")) || 6));
  const items = await companyTrends(slug, months);
  return c.json({ items, slug, months });
});
