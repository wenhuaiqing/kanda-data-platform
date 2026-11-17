// Auto-discovers pages under src/pages/<Section>/<Page>.jsx. The folder name
// becomes the URL slug; MODULE_META fixes the label, icon, group and order.
//
// The groups follow what a data platform lead owns: the platform itself, the
// quality of what it produces, the AI on top of it, who may see what, and
// running it - so the nav reads top to bottom like the job.

import {
  Activity, Bot, ClipboardCheck, Database, FileCheck2, Inbox, KeyRound, LayoutDashboard, Library, Milestone, Scale,
  ShieldAlert,
} from "lucide-react";

const PAGE_MODULES = import.meta.glob("./pages/*/*.jsx", { eager: true });

export const MODULE_META = {
  Overview:   { label: "Platform overview",       icon: LayoutDashboard, group: "Platform", order: 0 },
  Sources:    { label: "Sources & contracts",     icon: FileCheck2,      group: "Platform", order: 1 },
  Lakehouse:  { label: "Lakehouse & lineage",     icon: Database,        group: "Platform", order: 2 },
  Exceptions: { label: "Claim exceptions",        icon: Inbox,           group: "Quality",  order: 3 },
  Value:      { label: "What controls are worth", icon: Scale,           group: "Quality",  order: 4 },
  Triage:     { label: "AI triage",               icon: Bot,             group: "AI",       order: 5 },
  Policy:     { label: "Policy assistant (RAG)",  icon: Library,         group: "AI",       order: 6 },
  Risk:       { label: "Privacy & AI risk",       icon: ShieldAlert,     group: "AI",       order: 7 },
  Access:     { label: "Governed access & BI",    icon: KeyRound,        group: "Govern",   order: 8 },
  Delivery:   { label: "Roadmap, vendors & RAID", icon: ClipboardCheck,  group: "Lead",     order: 9 },
  Operations: { label: "Operations",              icon: Activity,        group: "Lead",     order: 10 },
  Brief:      { label: "First 90 days",           icon: Milestone,       group: "Lead",     order: 11 },
};

function slugify(value) {
  return value.toLowerCase().replace(/&/g, "and").replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
}

export function getRoutes() {
  const seen = new Map();
  for (const [path, module] of Object.entries(PAGE_MODULES)) {
    const match = path.match(/^\.\/pages\/([^/]+)\/([^/]+)\.jsx$/);
    if (!match || seen.has(match[1])) continue;
    const section = match[1];
    const meta = MODULE_META[section] || { label: section, order: 99, group: "Other" };
    seen.set(section, {
      section,
      label: meta.label,
      icon: meta.icon || null,
      group: meta.group,
      order: meta.order ?? 99,
      to: `/${meta.slug || slugify(section)}`,
      component: module.default,
    });
  }
  return [...seen.values()].sort((a, b) => a.order - b.order);
}
