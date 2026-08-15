import Typesense from "typesense";

export const COLLECTIONS = {
  jobs: "jobs",
  companies: "companies",
  skills: "skills",
};

export function getTypesense() {
  const host = process.env.TYPESENSE_HOST || "localhost";
  const port = Number(process.env.TYPESENSE_PORT || 8108);
  const protocol = process.env.TYPESENSE_PROTOCOL || "http";
  const apiKey = process.env.TYPESENSE_API_KEY?.trim();
  if (!apiKey) throw new Error("Missing TYPESENSE_API_KEY in .env");

  return new Typesense.Client({
    nodes: [{ host, port, protocol }],
    apiKey,
    connectionTimeoutSeconds: 60,
  });
}

export const JOBS_SCHEMA = {
  name: COLLECTIONS.jobs,
  fields: [
    { name: "title", type: "string" },
    { name: "normalized_title", type: "string", optional: true },
    { name: "company_slug", type: "string", facet: true },
    { name: "company_name", type: "string", optional: true },
    { name: "ats", type: "int32", facet: true, optional: true },
    { name: "employment_type", type: "int32", facet: true, optional: true },
    { name: "work_mode", type: "int32", facet: true, optional: true },
    { name: "seniority", type: "int32", facet: true, optional: true },
    { name: "country", type: "string", facet: true, optional: true },
    { name: "state", type: "string", facet: true, optional: true },
    { name: "city", type: "string", facet: true, optional: true },
    { name: "skills", type: "string[]", facet: true, optional: true },
    { name: "status", type: "int32", facet: true, optional: true },
    { name: "posted_at", type: "int64" },
    { name: "apply_url", type: "string", optional: true, index: false },
    { name: "department", type: "string", optional: true },
    { name: "team", type: "string", optional: true },
  ],
  default_sorting_field: "posted_at",
};

export const COMPANIES_SCHEMA = {
  name: COLLECTIONS.companies,
  fields: [
    { name: "slug", type: "string" },
    { name: "name", type: "string" },
    { name: "industry", type: "string", facet: true, optional: true },
    { name: "website", type: "string", optional: true, index: false },
    { name: "logo", type: "string", optional: true, index: false },
    { name: "active_job_count", type: "int32" },
  ],
  default_sorting_field: "active_job_count",
};

export const SKILLS_SCHEMA = {
  name: COLLECTIONS.skills,
  fields: [
    { name: "name", type: "string" },
    { name: "normalized_name", type: "string" },
    { name: "active_job_count", type: "int32" },
  ],
  default_sorting_field: "active_job_count",
};

export async function ensureCollections(client, { recreate = false } = {}) {
  for (const schema of [JOBS_SCHEMA, COMPANIES_SCHEMA, SKILLS_SCHEMA]) {
    let exists = false;
    try {
      await client.collections(schema.name).retrieve();
      exists = true;
    } catch {
      exists = false;
    }
    if (exists && recreate) {
      await client.collections(schema.name).delete();
      exists = false;
      console.log(`[typesense] dropped collection ${schema.name}`);
    }
    if (!exists) {
      await client.collections().create(schema);
      console.log(`[typesense] created collection ${schema.name}`);
    }
  }
}

export function pagination(query) {
  const limit = Math.min(100, Math.max(1, Number(query.limit) || 20));
  const page = Math.max(1, Number(query.page) || 1);
  return { limit, page };
}

export function escapeFilterValue(value) {
  return String(value).replace(/\\/g, "\\\\").replace(/`/g, "\\`");
}
