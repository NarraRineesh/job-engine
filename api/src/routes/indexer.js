import { timingSafeEqual } from "node:crypto";
import { Hono } from "hono";
import { getIndexStatus, startIndex } from "../indexer.js";

export const indexer = new Hono();

function adminKey() {
  return (process.env.INDEX_API_KEY || process.env.API_ADMIN_KEY || "").trim();
}

function requireAdmin(c) {
  const expected = adminKey();
  if (!expected) {
    return c.json({ error: "INDEX_API_KEY is not configured" }, 503);
  }
  const header = c.req.header("authorization") || "";
  const token = header.toLowerCase().startsWith("bearer ")
    ? header.slice(7).trim()
    : (c.req.header("x-index-key") || "").trim();
  const a = Buffer.from(token);
  const b = Buffer.from(expected);
  if (a.length !== b.length || !timingSafeEqual(a, b)) {
    return c.json({ error: "unauthorized" }, 401);
  }
  return null;
}

indexer.get("/index", (c) => {
  const denied = requireAdmin(c);
  if (denied) return denied;
  return c.json(getIndexStatus());
});

indexer.post("/index", async (c) => {
  const denied = requireAdmin(c);
  if (denied) return denied;
  let body = {};
  try {
    body = await c.req.json();
  } catch {
    body = {};
  }
  try {
    const status = startIndex({
      recreate: body.recreate === true,
      skipJobs: body.skip_jobs === true,
      page: body.page,
      afterId: body.after_id || null,
    });
    return c.json(status, 202);
  } catch (err) {
    if (err.status === 409) {
      return c.json({ error: err.message, ...err.current }, 409);
    }
    throw err;
  }
});
