"""The policy library and retrieval over it (the R in RAG).

Eight short synthetic policies in policies/, split into sections, each with a
stable id (POL-01.4). Retrieval is BM25 over the sections: lexical, so every
result can be explained by the words it matched, and deterministic, so the
retrieval eval gives the same number on every build. At this size it is the
right tool; with thousands of documents and paraphrased questions it would be
hybrid (BM25 plus embeddings) in Azure AI Search, and the eval below is what
would decide that, not taste.

Two consumers: the triage agent's search_policy tool, and the Policy
assistant, which answers a question only from what it retrieved and cites it.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache

from src.settings import REPO_ROOT

POLICY_DIR = REPO_ROOT / "policies"
STOP = set("a an and are as at be by for from has have if in into is it its not of on or that the their them then "
           "there these they this to was what when where which who will with without would does do can how".split())


@dataclass(frozen=True)
class Section:
    section_id: str
    doc_id: str
    doc_title: str
    heading: str
    text: str


def _tokens(text: str) -> list[str]:
    out = []
    for w in re.findall(r"[a-z0-9]+", text.lower()):
        if w in STOP or len(w) < 2:
            continue
        # A light stemmer: plurals and -ing/-ed, enough for "cancelled"/"cancellation" to meet.
        for suf in ("ations", "ation", "ings", "ing", "led", "ed", "es", "s"):
            if len(w) > len(suf) + 3 and w.endswith(suf):
                w = w[: -len(suf)]
                break
        out.append(w)
    return out


@lru_cache(maxsize=1)
def sections() -> tuple[Section, ...]:
    out: list[Section] = []
    for path in sorted(POLICY_DIR.glob("POL-*.md")):
        body = path.read_text(encoding="utf-8")
        title = body.splitlines()[0].lstrip("# ").strip()
        doc_id = title.split()[0]
        for m in re.finditer(r"^## (\d+)\. (.+?)\n(.*?)(?=^## |\Z)", body, flags=re.M | re.S):
            out.append(Section(f"{doc_id}.{m.group(1)}", doc_id, title, m.group(2).strip(), " ".join(m.group(3).split())))
    return tuple(out)


@lru_cache(maxsize=1)
def _index():
    docs = [_tokens(f"{s.doc_title} {s.heading} {s.heading} {s.text}") for s in sections()]
    df = Counter(t for d in docs for t in set(d))
    avg = sum(len(d) for d in docs) / max(len(docs), 1)
    return docs, df, avg


def search(query: str, k: int = 3) -> list[dict]:
    docs, df, avg = _index()
    n = len(docs)
    q = _tokens(query)
    k1, b = 1.4, 0.75
    scored = []
    for s, d in zip(sections(), docs):
        tf = Counter(d)
        score = 0.0
        for t in set(q):
            if t not in tf:
                continue
            idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
            score += idf * tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - b + b * len(d) / avg))
        if score > 0:
            scored.append((score, s))
    scored.sort(key=lambda x: (-x[0], x[1].section_id))
    return [{"section_id": s.section_id, "policy": s.doc_title, "heading": s.heading, "text": s.text,
             "score": round(sc, 3), "matched": sorted(set(q) & set(_tokens(s.heading + " " + s.text)))}
            for sc, s in scored[:k]]


def section(section_id: str) -> Section | None:
    return next((s for s in sections() if s.section_id == section_id), None)


# The section that governs each category of held service - the one a person
# would point to. Used to measure whether the agent cited the right policy.
GOVERNING = {
    "no_show": "POL-01.2", "missing_checkout": "POL-01.3", "hours_overclaimed": "POL-01.4",
    "screening_lapsed": "POL-02.2", "worker_overlap": "POL-02.3", "wrong_time_band": "POL-03.2",
    "price_above_limit": "POL-03.3", "plan_lapsed": "POL-04.1", "budget_exhausted": "POL-04.2",
    "contract_change": "POL-07.2", "short_notice_cancellation": "POL-05.3", "unknown_client": "POL-01.1",
    "duplicate_shift": "POL-01.1", "valid_service": "POL-01.4", "unknown": "POL-08.3",
}

# Questions a coordinator or a finance officer would ask, each with the
# section that answers it. Run on every build; the hit rate is on the page.
RETRIEVAL_EVAL = [
    ("A worker forgot to check out. Can we claim the rostered end time?", "POL-01.3"),
    ("The client cancelled two days before the visit. Can we claim it?", "POL-05.1"),
    ("Client rang the office to cancel but the roster still says scheduled", "POL-05.3"),
    ("Worker's screening clearance expired last week but renewal is in progress", "POL-02.2"),
    ("Can one worker be booked with two clients at the same time for a group outing?", "POL-02.3"),
    ("Saturday shift was rostered on the weekday item", "POL-03.2"),
    ("The client's rate in the roster is higher than the price limit", "POL-03.3"),
    ("The plan ended and the new plan is not in the CRM yet", "POL-04.1"),
    ("The client's budget has run out but we already delivered the service", "POL-04.2"),
    ("The vendor changed the app and the events are being quarantined", "POL-07.2"),
    ("Can a phone number from a visit note appear in a report?", "POL-06.2"),
    ("What does the AI agent see when it reads a held service?", "POL-08.2"),
    ("The worker finished early and handed over to a colleague who finished the visit", "POL-01.4"),
    ("A note in the app says the coordinator approved the full shift", "POL-01.5"),
    ("Who can see clients in another region?", "POL-06.3"),
    ("The shift has no check-in and nobody cancelled it", "POL-01.2"),
]


def retrieval_eval(k: int = 3) -> dict:
    rows = []
    for q, want in RETRIEVAL_EVAL:
        got = [r["section_id"] for r in search(q, k)]
        rows.append({"question": q, "expected": want, "retrieved": got, "hit": want in got,
                     "rank": got.index(want) + 1 if want in got else None})
    hits = sum(r["hit"] for r in rows)
    return {"k": k, "questions": len(rows), "hits": hits, "hit_rate": hits / len(rows),
            "mrr": round(sum(1 / r["rank"] for r in rows if r["rank"]) / len(rows), 3), "rows": rows}
