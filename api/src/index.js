import { serve } from "@hono/node-server";
import { app } from "./app.js";

const port = Number(process.env.API_PORT || 8787);
const hostname = process.env.API_HOST || "127.0.0.1";

serve({ fetch: app.fetch, port, hostname }, (info) => {
  console.log(`[api] listening on http://${hostname}:${info.port}`);
});
