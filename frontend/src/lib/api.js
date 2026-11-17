// Fetch helpers and formatters. Errors carry the server's own reason, because
// here the reason for a refusal is the point.

import { useCallback, useEffect, useState } from "react";
import { API_BASE_URL, actorName, authHeaders } from "../config.js";

export async function api(path, { method = "GET", body, signal } = {}) {
  const opts = { method, headers: { Accept: "application/json", ...authHeaders() }, signal };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(`${API_BASE_URL}${path}`, opts);
  let payload = null;
  try { payload = await res.json(); } catch { /* empty body */ }
  if (!res.ok) {
    const detail = payload?.detail;
    const msg = typeof detail === "string" ? detail
      : Array.isArray(detail) ? detail.map((d) => d.msg).join("; ")
      : `HTTP ${res.status} ${res.statusText}`;
    const err = new Error(msg);
    err.status = res.status;
    throw err;
  }
  return payload;
}

// Mutating calls: every write site greppable, the actor applied in one place.
export function apiWrite(path, body = {}) {
  return fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json", "X-Actor": actorName(), ...authHeaders() },
    body: JSON.stringify(body),
  }).then(async (res) => {
    let payload = null;
    try { payload = await res.json(); } catch { /* empty */ }
    if (!res.ok) {
      const err = new Error(typeof payload?.detail === "string" ? payload.detail : `HTTP ${res.status}`);
      err.status = res.status;
      throw err;
    }
    return payload;
  });
}

// Load-on-mount with a reload handle.
export function useApi(path) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!path) return undefined;
    const ctl = new AbortController();
    setError(null);
    api(path, { signal: ctl.signal }).then(setData).catch((e) => {
      if (e.name !== "AbortError") setError(e);
    });
    return () => ctl.abort();
  }, [path, tick]);
  const reload = useCallback(() => setTick((n) => n + 1), []);
  return { data, error, reload };
}

export function fmtAud(value, { decimals = 0, short = false, signed = false } = {}) {
  if (value == null || Number.isNaN(Number(value))) return "-";
  const v = Number(value);
  const sign = v < 0 ? "-" : signed && v > 0 ? "+" : "";
  const a = Math.abs(v);
  if (short && a >= 1_000_000) return `${sign}$${(a / 1_000_000).toFixed(2)}M`;
  if (short && a >= 10_000) return `${sign}$${(a / 1_000).toFixed(1)}k`;
  return `${sign}$${a.toLocaleString("en-AU", { maximumFractionDigits: decimals, minimumFractionDigits: decimals })}`;
}

export function fmtInt(value) {
  if (value == null || Number.isNaN(Number(value))) return "-";
  return Number(value).toLocaleString("en-AU", { maximumFractionDigits: 0 });
}

export function fmtNum(value, digits = 2) {
  if (value == null || Number.isNaN(Number(value))) return "-";
  return Number(value).toLocaleString("en-AU", { maximumFractionDigits: digits, minimumFractionDigits: digits });
}

function parse(value) {
  if (!value) return null;
  // Timestamps carry no zone; read
  // them as written rather than letting the browser shift them.
  const s = String(value).replace(" ", "T");
  const m = s.match(/^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2})(?::(\d{2})(?:\.(\d+))?)?)?/);
  if (!m) return null;
  return { y: m[1], mo: m[2], d: m[3], h: m[4], mi: m[5], s: m[6], f: m[7] };
}

export function fmtDate(value) {
  const p = parse(value);
  return p ? `${p.d}/${p.mo}/${p.y}` : "-";
}

export function fmtDay(value) {
  const p = parse(value);
  if (!p) return "-";
  const names = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  const dow = new Date(Number(p.y), Number(p.mo) - 1, Number(p.d)).getDay();
  return `${names[dow]} ${p.d}/${p.mo}`;
}

export function fmtTime(value, { ms = false, seconds = true } = {}) {
  const p = parse(value);
  if (!p || !p.h) return "-";
  let out = `${p.h}:${p.mi}`;
  if (seconds) out += `:${p.s || "00"}`;
  if (ms) out += `.${(p.f || "000").slice(0, 3)}`;
  return out;
}

export function fmtDateTime(value, opts) {
  return `${fmtDate(value)} ${fmtTime(value, opts)}`;
}

export function fmtMs(value) {
  if (value == null || Number.isNaN(Number(value))) return "-";
  const v = Number(value);
  if (Math.abs(v) >= 10_000) return `${(v / 1000).toFixed(1)} s`;
  if (Math.abs(v) >= 100) return `${Math.round(v).toLocaleString("en-AU")} ms`;
  return `${v.toFixed(1)} ms`;
}

export function fmtDuration(seconds) {
  if (seconds == null || Number.isNaN(Number(seconds))) return "-";
  const s = Number(seconds);
  if (s < 60) return `${s.toFixed(s < 10 ? 1 : 0)} s`;
  const m = Math.floor(s / 60);
  const r = Math.round(s % 60);
  if (m < 60) return r ? `${m} min ${r} s` : `${m} min`;
  return `${Math.floor(m / 60)} h ${m % 60} min`;
}

export function pct(value, digits = 1) {
  if (value == null || Number.isNaN(Number(value))) return "-";
  return `${(Number(value) * 100).toFixed(digits)}%`;
}

export const CHECK_LABEL = {
  identity: "Client identity",
  evidence: "Evidence of delivery",
  screening: "Worker screening",
  overlap: "One place at a time",
  plan_dates: "Funding in force",
  item: "Right item",
  price: "Price limit",
  duration: "Time evidenced",
  budget: "Budget left",
};

export const CONTROL_LABEL = {
  ...CHECK_LABEL,
  dedupe_events: "Event de-duplication",
  mask_notes: "Note masking",
  all_controls_off: "Every control off",
};

export const CATEGORY_LABEL = {
  no_show: "No-show",
  missing_checkout: "Missing check-out",
  hours_overclaimed: "Hours over-claimed",
  price_above_limit: "Above price limit",
  wrong_time_band: "Wrong time band",
  worker_overlap: "Worker overlap",
  unknown_client: "Unknown client",
  screening_lapsed: "Screening lapsed",
  plan_lapsed: "Plan lapsed",
  budget_exhausted: "Budget exhausted",
  contract_change: "Source changed shape",
  short_notice_cancellation: "Short notice cancellation",
  duplicate_shift: "Rostered twice",
  valid_service: "Valid service",
  unknown: "Unknown",
};

export const ACTION_LABEL = {
  cancel_claim: "Cancel the claim",
  confirm_with_worker: "Confirm with the worker",
  claim_evidenced_time: "Claim the evidenced time",
  reprice_to_limit: "Reprice to the limit",
  reprice_to_correct_item: "Reprice to the right item",
  escalate_to_coordinator: "Escalate to the coordinator",
  propose_client_match: "Propose the matching client",
  escalate_to_compliance: "Escalate to compliance",
  hold_until_plan_renewed: "Hold until the plan is renewed",
  route_to_plan_review: "Send to the plan review",
  propose_contract_update: "Propose a contract update",
  claim_cancellation: "Claim as a cancellation",
  claim_as_rostered: "Claim as rostered",
};

export const STATUS_LABEL = {
  claimable: "Claimable",
  claimable_cancellation: "Claimable cancellation",
  not_claimable: "Cancelled with notice",
  held: "Held",
};

// Coordinator hours a quarter on held services, from counts in the data and
// handling times that are assumptions. One function so pages cannot disagree.
export function timeModel(held, a) {
  const today = (held * a.investigate_exception_today_min) / 60;
  const after = (held * a.investigate_with_first_read_min) / 60;
  return { today, after, saved: today - after, savedAud: (today - after) * a.coordinator_cost_per_hour_aud };
}
