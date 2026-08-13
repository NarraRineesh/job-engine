/** Enum maps matching src/job_engine/enums.py (SMALLINT codecs). */

export const EMPLOYMENT_TYPE = {
  full_time: 1,
  part_time: 2,
  intern: 3,
  internship: 3,
  contract: 4,
  temporary: 5,
  freelance: 6,
};

export const WORK_MODE = {
  remote: 1,
  hybrid: 2,
  onsite: 3,
};

export const STATUS = {
  active: 1,
  closed: 2,
  draft: 3,
  expired: 4,
};

export const ATS = {
  greenhouse: 1,
  lever: 2,
  ashby: 3,
  workday: 4,
  smartrecruiters: 5,
  bamboohr: 6,
  icims: 7,
  jobvite: 8,
  recruitee: 9,
  teamtailor: 10,
  oracle: 11,
  successfactors: 12,
  sap_successfactors: 12,
  rippling: 13,
  personio: 14,
  breezy: 15,
  breezyhr: 15,
  workable: 16,
  pinpoint: 17,
  darwinbox: 18,
  keka: 24,
  phenom: 19,
  seek: 20,
  amazon: 21,
  gem: 22,
  google: 23,
  adp: 25,
  herp: 26,
  hrmos: 27,
  paycom: 28,
  paylocity: 29,
  softgarden: 30,
  avature: 31,
  beisen: 32,
  beisen_legacy: 33,
  builtin: 34,
  bundesagentur: 35,
  bytedance: 36,
  cornerstone: 37,
  dayforce: 38,
  eightfold: 39,
  eures: 40,
  getonbrd: 41,
  gupy: 42,
  infojobs_es: 43,
  jazzhr: 44,
  jobbankca: 45,
  jobs_cz: 46,
  jobsch: 47,
  join_com: 48,
  manfred: 49,
  mercor: 50,
  meta: 51,
  moka: 52,
  pageup: 53,
  recruiterbox: 54,
  remoteok: 55,
  taleo: 56,
  tesla: 57,
  thehub: 58,
  tiktok: 59,
  uber: 60,
  ukg: 61,
  usajobs: 62,
  wanted: 63,
  welcometothejungle: 64,
  wellfound: 65,
  weworkremotely: 66,
  ycombinator: 67,
  apple: 68,
  arbetsformedlingen: 69,
};

function invert(map) {
  const out = {};
  for (const [k, v] of Object.entries(map)) {
    if (out[v] === undefined) out[v] = k;
  }
  return out;
}

export const EMPLOYMENT_TYPE_LABEL = invert(EMPLOYMENT_TYPE);
export const WORK_MODE_LABEL = invert(WORK_MODE);
export const STATUS_LABEL = invert(STATUS);
export const ATS_LABEL = invert(ATS);

export function toEmploymentType(value) {
  if (value == null || value === "" || value === "unknown") return null;
  if (typeof value === "number") return value;
  return EMPLOYMENT_TYPE[String(value).toLowerCase().replace(/-/g, "_")] ?? null;
}

export function toWorkMode(value) {
  if (value == null || value === "" || value === "unknown") return null;
  if (typeof value === "number") return value;
  return WORK_MODE[String(value).toLowerCase().replace(/-/g, "_")] ?? null;
}

export function toStatus(value) {
  if (value == null || value === "") return STATUS.active;
  if (typeof value === "number") return value;
  return STATUS[String(value).toLowerCase()] ?? STATUS.active;
}

export function toAts(value) {
  if (value == null || value === "") return null;
  if (typeof value === "number") return value;
  return ATS[String(value).toLowerCase().replace(/-/g, "_")] ?? null;
}

export function labelEmployment(n) {
  return EMPLOYMENT_TYPE_LABEL[n] ?? null;
}

export function labelWorkMode(n) {
  return WORK_MODE_LABEL[n] ?? null;
}

export function labelStatus(n) {
  return STATUS_LABEL[n] ?? null;
}

export function labelAts(n) {
  return ATS_LABEL[n] ?? null;
}
