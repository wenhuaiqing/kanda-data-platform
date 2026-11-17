// Drive the operator's path in a real browser: refusals, a decision, a
// contract approval that reprocesses the quarter, a replay, a triage run, a
// policy search, a query as a role, then reset.
//
//   BASE=http://localhost:5271 TOKEN=<DEMO_WRITE_TOKEN> node evals/flow.mjs

import { chromium } from "playwright";

const BASE = process.env.BASE || "http://localhost:5271";
const TOKEN = process.env.TOKEN || "";
const CHANNEL = process.env.BROWSER_CHANNEL || undefined;
const OUT = process.env.OUT || "./page-shots";
const browser = await chromium.launch(CHANNEL ? { channel: CHANNEL } : {});
const page = await (await browser.newContext({ viewport: { width: 1500, height: 1000 } })).newPage();
const steps = [];
const expect = async (name, locator) => {
  await locator.first().waitFor({ timeout: 30_000 });
  steps.push(name);
  console.log(`ok   ${name}`);
};

await page.goto(`${BASE}/exceptions?write_token=${TOKEN}`, { waitUntil: "networkidle" });
await expect("the token is scrubbed from the URL", page.getByText("Operator: writes enabled"));
if (page.url().includes("write_token")) throw new Error("token still in the URL");

await page.getByLabel("Check").selectOption("screening");
await page.locator("tbody tr").first().click();
await page.getByLabel("Decision").selectOption("claim_as_rostered");
await page.getByLabel("Note").fill("renewal in progress");
await page.getByRole("button", { name: "Record the decision" }).click();
await expect("claiming a screening hold is refused", page.getByText("can only be escalated to compliance"));
await page.getByLabel("Decision").selectOption("escalate_to_compliance");
await page.getByRole("button", { name: "Record the decision" }).click();
await expect("escalating it is recorded", page.getByText("Escalate to compliance, by Claims officer"));

await page.goto(`${BASE}/sources`, { waitUntil: "networkidle" });
await page.getByLabel("Acting as").first().fill("contract-monitor");
await page.getByRole("button", { name: "Approve and reprocess" }).click();
await expect("the proposer cannot approve", page.getByText("cannot also decide it"));
await page.getByLabel("Acting as").first().fill("Data platform lead");
await page.getByRole("button", { name: "Approve and reprocess" }).click();
await expect("approval reprocesses from the landing zone", page.getByText("Reprocessed from the landing zone"));
await page.screenshot({ path: `${OUT}/flow-approved.png`, fullPage: true });

await page.goto(`${BASE}/lakehouse`, { waitUntil: "networkidle" });
await page.getByRole("button", { name: "Re-run and compare" }).click();
await expect("the re-run matches after the approval", page.getByText("Every digest matches."));

await page.goto(`${BASE}/triage`, { waitUntil: "networkidle" });
await page.getByRole("button", { name: "Run the runbook" }).click();
await expect("the runbook triages a held service", page.getByText("Evidence grounded"));

await page.goto(`${BASE}/policy`, { waitUntil: "networkidle" });
await page.getByRole("button", { name: "Retrieval only" }).click();
await expect("retrieval returns policy sections", page.getByText("POL-01.3"));

await page.goto(`${BASE}/access`, { waitUntil: "networkidle" });
await page.getByRole("button", { name: "Run", exact: true }).click();
await expect("a coordinator's query runs on their views", page.getByText("Result, as coordinator_bn"));
await page.getByRole("button", { name: "Try reading another region" }).click();
await expect("reading another region is refused", page.getByText("Not available to this role"));

await page.goto(`${BASE}/operations`, { waitUntil: "networkidle" });
await expect("refusals are in the audit log", page.getByText("refused"));
await page.getByRole("button", { name: "Reset the demo" }).click();
await page.waitForTimeout(800);
await browser.close();
console.log(`\n${steps.length} steps passed`);
