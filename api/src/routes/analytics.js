import { Hono } from "hono";
import { COLLECTIONS, getTypesense } from "../typesense.js";

export const analytics = new Hono();

analytics.get("/stats", async (c) => {
  const client = getTypesense();
  const [jobs, companies, skills, active] = await Promise.all([
    client.collections(COLLECTIONS.jobs).retrieve(),
    client.collections(COLLECTIONS.companies).retrieve(),
    client.collections(COLLECTIONS.skills).retrieve(),
    client.collections(COLLECTIONS.jobs).documents().search({
      q: "*",
      query_by: "title",
      filter_by: "status:=1",
      per_page: 0,
    }),
  ]);
  return c.json({
    total_jobs: jobs.num_documents ?? 0,
    active_jobs: active.found ?? 0,
    companies: companies.num_documents ?? 0,
    skills: skills.num_documents ?? 0,
    source: "typesense",
  });
});
