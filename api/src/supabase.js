import { createClient } from "@supabase/supabase-js";

function env(...names) {
  for (const name of names) {
    const v = process.env[name]?.trim();
    if (v) return v;
  }
  return "";
}

function requireEnv(...names) {
  const v = env(...names);
  if (!v) throw new Error(`Missing ${names.join(" or ")} in .env`);
  return v;
}

/** Read client (publishable / anon). Used by HTTP routes. */
export function getSupabase() {
  return createClient(
    requireEnv("SUPABASE_URL"),
    requireEnv("SUPABASE_PUBLISHABLE_KEY", "SUPABASE_ANON_KEY"),
    {
      auth: { persistSession: false, autoRefreshToken: false },
    },
  );
}

/** Prefer secret / service role for bulk index; fall back to publishable. */
export function getSupabaseIndexer() {
  const url = requireEnv("SUPABASE_URL");
  const key = requireEnv(
    "SUPABASE_SECRET_KEY",
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_PUBLISHABLE_KEY",
    "SUPABASE_ANON_KEY",
  );
  return createClient(url, key, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
}

export function getJwksUrl() {
  return env("SUPABASE_JWKS_URL");
}
