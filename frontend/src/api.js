// Same-origin by default: the Vite dev server proxies /api, and a local build
// served by FastAPI shares its origin. Override with VITE_API_BASE.
// On Vercel the site is static, so calls go to the FastAPI backend on Render.
const DEPLOYED_API = "https://hindi-search.onrender.com";
const BASE =
  import.meta.env.VITE_API_BASE ??
  (window.location.hostname.endsWith(".vercel.app") ? DEPLOYED_API : "");

async function get(path, params = {}, signal) {
  const url = new URL(BASE + path, window.location.origin);
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null) url.searchParams.set(k, v);
  }
  const res = await fetch(url, { signal });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      /* keep status text */
    }
    throw new Error(detail);
  }
  return res.json();
}

export const api = {
  search: (q, page, size, signal) => get("/api/search", { q, page, size }, signal),
  document: (id, q, signal) => get(`/api/document/${id}`, { q }, signal),
  suggestions: () => get("/api/suggestions"),
  autocomplete: (prefix, signal) => get("/api/autocomplete", { prefix, limit: 8 }, signal),
  index: (term, limit, signal) => get(`/api/index/${encodeURIComponent(term)}`, { limit }, signal),
  stats: () => get("/api/stats"),
  health: (signal) => get("/api/health", {}, signal),
};

export const nf = new Intl.NumberFormat("en-US");

/** Seconds with enough decimals that tiny timings don't round to zero. */
export function formatSeconds(sec) {
  if (sec >= 0.01) return sec.toFixed(3);
  if (sec >= 0.0001) return sec.toFixed(4);
  return sec.toFixed(6);
}
