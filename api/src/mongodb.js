import { MongoClient } from "mongodb";

let clientPromise;

function requireUri() {
  const uri = process.env.MONGODB_URI?.trim();
  if (!uri) throw new Error("Missing MONGODB_URI in .env");
  return uri;
}

export function getMongo() {
  if (!clientPromise) {
    const client = new MongoClient(requireUri());
    clientPromise = client.connect();
  }
  return clientPromise;
}

export async function getDb() {
  const client = await getMongo();
  return client.db();
}

export async function featuredJobs(limit) {
  const db = await getDb();
  return db
    .collection("jobs")
    .aggregate([
      { $match: { status: 1 } },
      {
        $lookup: {
          from: "job_analytics",
          localField: "_id",
          foreignField: "_id",
          as: "a",
        },
      },
      { $unwind: { path: "$a", preserveNullAndEmptyArrays: true } },
      {
        $addFields: {
          score: {
            $add: [
              { $ifNull: ["$a.views", 0] },
              { $multiply: [{ $ifNull: ["$a.clicks", 0] }, 2] },
              { $multiply: [{ $ifNull: ["$a.saved", 0] }, 3] },
              { $multiply: [{ $ifNull: ["$a.applications", 0] }, 5] },
            ],
          },
        },
      },
      { $sort: { score: -1, posted_at: -1 } },
      { $limit: limit },
      { $project: { _id: 0, job_id: "$_id", score: 1 } },
    ])
    .toArray();
}

export async function trendingJobs(days, limit) {
  const db = await getDb();
  const since = new Date(Date.now() - days * 86400000);
  return db
    .collection("jobs")
    .aggregate([
      {
        $match: {
          status: 1,
          $or: [{ posted_at: { $gte: since } }, { last_scraped_at: { $gte: since } }],
        },
      },
      {
        $lookup: {
          from: "job_analytics",
          localField: "_id",
          foreignField: "_id",
          as: "a",
        },
      },
      { $unwind: { path: "$a", preserveNullAndEmptyArrays: true } },
      {
        $addFields: {
          score: {
            $add: [
              { $ifNull: ["$a.views", 0] },
              { $multiply: [{ $ifNull: ["$a.clicks", 0] }, 2] },
            ],
          },
        },
      },
      { $sort: { score: -1, posted_at: -1 } },
      { $limit: limit },
      { $project: { _id: 0, job_id: "$_id", score: 1 } },
    ])
    .toArray();
}

export async function trendingSkills(days, limit) {
  const db = await getDb();
  const since = new Date(Date.now() - days * 86400000);
  return db
    .collection("jobs")
    .aggregate([
      {
        $match: {
          status: 1,
          $or: [{ posted_at: { $gte: since } }, { last_scraped_at: { $gte: since } }],
        },
      },
      { $unwind: "$skills" },
      { $group: { _id: "$skills", active_job_count: { $sum: 1 } } },
      { $sort: { active_job_count: -1 } },
      { $limit: limit },
      {
        $project: {
          _id: 0,
          skill_name: "$_id",
          active_job_count: 1,
        },
      },
    ])
    .toArray();
}

export async function getAnalytics(jobId) {
  const db = await getDb();
  const row = await db.collection("job_analytics").findOne({ _id: jobId });
  return (
    row || {
      job_id: jobId,
      views: 0,
      clicks: 0,
      applications: 0,
      saved: 0,
    }
  );
}

export async function incrementAnalytics(jobId, metric) {
  const db = await getDb();
  await db.collection("job_analytics").updateOne(
    { _id: jobId },
    {
      $inc: { [metric]: 1 },
      $set: { job_id: jobId, updated_at: new Date() },
    },
    { upsert: true },
  );
  return getAnalytics(jobId);
}

export async function companyTrends(slug, months) {
  const db = await getDb();
  const since = new Date();
  since.setMonth(since.getMonth() - months);
  const rows = await db
    .collection("jobs")
    .aggregate([
      {
        $match: {
          "company.slug": slug,
          $or: [
            { last_scraped_at: { $gte: since } },
            { posted_at: { $gte: since } },
          ],
        },
      },
      {
        $group: {
          _id: {
            $dateToString: {
              format: "%Y-%m-01",
              date: { $ifNull: ["$last_scraped_at", "$posted_at"] },
            },
          },
          job_count: { $sum: 1 },
          company_name: { $first: "$company.name" },
        },
      },
      { $sort: { _id: 1 } },
    ])
    .toArray();

  return rows.map((r, i) => {
    const prev = i > 0 ? rows[i - 1].job_count : null;
    let growth_percentage = null;
    if (prev) {
      growth_percentage = Math.round(((r.job_count - prev) / prev) * 10000) / 100;
    }
    return {
      company_slug: slug,
      company_name: r.company_name,
      month: r._id,
      job_count: r.job_count,
      growth_percentage,
    };
  });
}
