import { Hono } from "hono";
import { cors } from "hono/cors";
import { jobs } from "./routes/jobs.js";
import { companies } from "./routes/companies.js";
import { skills } from "./routes/skills.js";
import { trends } from "./routes/trends.js";
import { analytics } from "./routes/analytics.js";

export const app = new Hono();

app.use("*", cors());

app.get("/health", (c) => c.json({ ok: true }));

app.route("/v1/jobs", jobs);
app.route("/v1/companies", companies);
app.route("/v1/skills", skills);
app.route("/v1/trends", trends);
app.route("/v1", analytics);

app.notFound((c) => c.json({ error: "not_found" }, 404));
app.onError((err, c) => {
  console.error("[api]", err);
  return c.json(
    { error: err?.message || "internal_error" },
    err?.status && Number.isInteger(err.status) ? err.status : 500,
  );
});
