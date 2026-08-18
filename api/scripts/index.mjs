/**
 * Sync MongoDB jobs / companies / skills into Typesense.
 *
 * Usage: npm run index
 * Env:
 *   INDEX_RECREATE=1  drop+recreate collections (default 0)
 *   INDEX_PAGE=80     jobs per batch
 *   INDEX_AFTER_ID=   resume after this job _id (exclusive)
 *   INDEX_SKIP_JOBS=1 skip job docs (recompute company counts from Typesense)
 */
import { runIndex } from "../src/indexer.js";

const result = await runIndex({
  recreate: process.env.INDEX_RECREATE === "1",
  skipJobs: process.env.INDEX_SKIP_JOBS === "1",
  page: process.env.INDEX_PAGE,
  afterId: process.env.INDEX_AFTER_ID || null,
});
if (result.status === "error") process.exit(1);
process.exit(0);
