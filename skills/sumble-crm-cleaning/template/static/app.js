/* CRM-cleaning review UI. Vanilla JS, no build step.
   State: findings (read-only, from analyze.py) + decisions (persisted via
   POST /api/decide on every click). */

"use strict";

const state = {
  findings: null,
  decisions: {},
  tab: "duplicates",
  confidence: new Set(), // empty = all
  status: new Set(), // empty = all; values: undecided|accept|reject|skip
  search: "",
};

const $ = (sel) => document.querySelector(sel);
const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));

async function init() {
  const resp = await fetch("/api/data");
  const data = await resp.json();
  state.findings = data.findings;
  state.decisions = data.decisions || {};
  const company = state.findings.meta.company;
  if (company) $("#company-name").textContent = ` — ${company}`;
  renderSummary();
  renderChips();
  bindToolbar();
  render();
}

/* ---------- data helpers ---------- */

function tabItems(tab) {
  const f = state.findings;
  if (tab === "duplicates") return f.duplicates;
  if (tab === "parent_sub") return f.parent_sub;
  if (tab === "parent_not_in_crm") return f.parent_not_in_crm;
  return f.unmatched.map((a, i) => ({
    id: `um_${i}`,
    confidence: "info",
    accounts: [a],
    unmatched: true,
  }));
}

function decisionOf(id) {
  return (state.decisions[id] || {}).decision || "undecided";
}

function reviewable() {
  const f = state.findings;
  return [...f.duplicates, ...f.parent_sub, ...f.parent_not_in_crm];
}

function findingText(item) {
  const parts = [];
  const push = (a) => {
    if (!a) return;
    parts.push(
      a.crm_account_id, a.crm_name, a.crm_domain, a.sumble_name,
      a.crm_city, a.crm_state, a.crm_country
    );
  };
  (item.accounts || []).forEach(push);
  push(item.child);
  push(item.suggested_parent);
  push(item.current_parent);
  if (item.parent_org) parts.push(item.parent_org.name, item.parent_org.domain);
  (item.children || []).forEach(push);
  return parts.join(" ").toLowerCase();
}

/* ---------- rendering ---------- */

function renderSummary() {
  const m = state.findings.meta;
  const cards = [
    [m.accounts_total, "CRM accounts"],
    [m.accounts_matched, "matched to Sumble"],
    [m.duplicate_clusters, "duplicate clusters"],
    [m.parent_sub_findings, "hierarchy gaps"],
    [m.parents_not_in_crm, "parents not in CRM"],
    [m.accounts_unmatched, "unmatched"],
  ];
  $("#summary").innerHTML = cards
    .map(
      ([num, label]) =>
        `<div class="card"><div class="num">${num}</div>` +
        `<div class="label">${label}</div></div>`
    )
    .join("");
  document.querySelectorAll(".tab").forEach((btn) => {
    const n = tabItems(btn.dataset.tab).length;
    btn.innerHTML = `${btn.textContent.replace(/\d+$/, "")}` +
      `<span class="count">${n}</span>`;
  });
  renderProgress();
}

function renderProgress() {
  const all = reviewable();
  const done = all.filter((f) => decisionOf(f.id) !== "undecided").length;
  $("#progress").textContent = `${done} of ${all.length} reviewed`;
}

function renderChips() {
  const conf = ["high", "medium", "low", "info"];
  $("#confidence-chips").innerHTML = conf
    .map((c) => `<button class="chip" data-conf="${c}">${c}</button>`)
    .join("");
  const stat = ["undecided", "accept", "reject", "skip"];
  $("#status-chips").innerHTML = stat
    .map((s) => `<button class="chip" data-status="${s}">${s}</button>`)
    .join("");
}

function bindToolbar() {
  document.querySelectorAll(".tab").forEach((btn) =>
    btn.addEventListener("click", () => {
      state.tab = btn.dataset.tab;
      document
        .querySelectorAll(".tab")
        .forEach((b) => b.classList.toggle("active", b === btn));
      render();
    })
  );
  $("#confidence-chips").addEventListener("click", (e) => {
    const c = e.target.dataset?.conf;
    if (!c) return;
    state.confidence.has(c) ? state.confidence.delete(c) : state.confidence.add(c);
    e.target.classList.toggle("active");
    render();
  });
  $("#status-chips").addEventListener("click", (e) => {
    const s = e.target.dataset?.status;
    if (!s) return;
    state.status.has(s) ? state.status.delete(s) : state.status.add(s);
    e.target.classList.toggle("active");
    render();
  });
  $("#search").addEventListener("input", (e) => {
    state.search = e.target.value.toLowerCase();
    render();
  });
  $("#export-btn").addEventListener("click", () => {
    window.location.href = "/api/export";
  });
}

function render() {
  const items = tabItems(state.tab).filter((item) => {
    if (state.confidence.size && !state.confidence.has(item.confidence)) return false;
    if (!item.unmatched && state.status.size && !state.status.has(decisionOf(item.id)))
      return false;
    if (state.search && !findingText(item).includes(state.search)) return false;
    return true;
  });
  const main = $("#findings");
  if (!items.length) {
    main.innerHTML = `<div class="empty">Nothing to show with the current filters.</div>`;
    return;
  }
  main.innerHTML = items.map(renderFinding).join("");
  bindFindingEvents(main);
}

/* One line under the finding head listing every DISTINCT Sumble org the
   finding's accounts matched — org name links to sumble_url, Sumble's own
   domain in parens. Keeps the table CRM-only while the match stays visible. */
function sumbleMatchLine(item) {
  const accts = [
    ...(item.accounts || []),
    item.child,
    item.suggested_parent,
    item.current_parent,
    ...(item.children || []),
  ].filter(Boolean);
  const orgs = new Map();
  let unmatched = 0;
  accts.forEach((a) => {
    if (a.org_id) {
      if (!orgs.has(a.org_id)) orgs.set(a.org_id, a);
    } else unmatched += 1;
  });
  if (!orgs.size) return "";
  const parts = [...orgs.values()].map((a) => {
    const name = a.sumble_url
      ? `<a href="${esc(a.sumble_url)}" target="_blank" rel="noopener">` +
        `${esc(a.sumble_name)} ↗</a>`
      : esc(a.sumble_name);
    const dom = a.sumble_domain
      ? ` <span class="dim">(${esc(a.sumble_domain)})</span>`
      : "";
    return `<span>${name}${dom}${altLine(a)}</span>`;
  });
  const tail = unmatched
    ? ` <span class="dim">· ${unmatched} account${unmatched > 1 ? "s" : ""} not matched</span>`
    : "";
  const label = orgs.size > 1 ? "Sumble matches" : "Sumble match";
  return `<div class="sumble-match">${label}: ${parts.join(" · ")}${tail}</div>`;
}

/* Alternate names/domains Sumble knows for a matched org (from the optional
   org_alternates.json sidecar) — shown dim, truncated, full list on hover. */
function altLine(a) {
  const fmt = (list, label, max) => {
    if (!list || !list.length) return "";
    const shown = list.slice(0, max).map(esc).join(", ");
    const more = list.length > max ? ` +${list.length - max} more` : "";
    const title = esc(list.join(", "));
    return `<span title="${title}">${label} ${shown}${more}</span>`;
  };
  const names = fmt(a.sumble_name_alternates, "aka", 5);
  const doms = fmt(a.sumble_url_alternates, "alt domains:", 4);
  if (!names && !doms) return "";
  return ` <span class="dim">— ${[names, doms].filter(Boolean).join(" · ")}</span>`;
}

function acctCells(a) {
  const emp = a.employee_count_int
    ? Number(a.employee_count_int).toLocaleString()
    : "";
  const loc = [a.crm_city, a.crm_state, a.crm_country].filter(Boolean).join(", ");
  const mod = (a.crm_last_modified || "").slice(0, 10);
  const li = a.crm_linkedin_url
    ? `<a href="${esc(a.crm_linkedin_url)}" target="_blank" rel="noopener">LinkedIn ↗</a>`
    : "";
  const metaLine =
    li || mod
      ? `<div class="dim">${li}${li && mod ? " · " : ""}` +
        `${mod ? `modified ${esc(mod)}` : ""}</div>`
      : "";
  const name = a.crm_url
    ? `<a href="${esc(a.crm_url)}" target="_blank" rel="noopener">` +
      `<b>${esc(a.crm_name)}</b> ↗</a>`
    : `<b>${esc(a.crm_name)}</b>`;
  return (
    `<td>${name}` +
    `<div class="dim">${esc(a.crm_account_id)}</div>${metaLine}</td>` +
    `<td class="dim">${esc(a.crm_domain)}</td>` +
    `<td class="dim">${esc(loc)}</td>` +
    `<td class="dim">${esc(a.owner || "")}${a.is_customer ? " · customer" : ""}</td>` +
    `<td class="dim">${emp}</td>` +
    `<td class="dim">${esc(a.headquarters_country)}</td>`
  );
}

const ACCT_HEAD =
  `<tr><th>CRM account</th><th>CRM domain</th><th>CRM location</th><th>Owner</th>` +
  `<th>Employees</th><th>Sumble HQ</th></tr>`;

function renderFinding(item) {
  if (state.tab === "unmatched") return renderUnmatched(item);
  const dec = decisionOf(item.id);
  const head =
    `<div class="finding-head">` +
    `<span class="badge ${item.confidence}">${item.confidence}</span>` +
    `<span class="finding-title">${titleOf(item)}</span>` +
    (item.evidence || [])
      .map((e) => `<span class="badge evidence">${esc(e)}</span>`)
      .join("") +
    `<span class="finding-id">${item.id}</span></div>`;
  const note = item.note
    ? `<div class="note-line">${esc(item.note)}</div>`
    : "";
  let body = "";
  if (state.tab === "duplicates") body = dupBody(item);
  else if (state.tab === "parent_sub") body = psBody(item);
  else body = pxBody(item);
  return (
    `<div class="finding decided-${dec}" data-id="${item.id}">` +
    head + sumbleMatchLine(item) + note + body + decideRow(item, dec) + `</div>`
  );
}

function titleOf(item) {
  if (state.tab === "duplicates")
    return `${item.accounts.length} accounts look like the same company`;
  if (state.tab === "parent_sub")
    return item.type === "parent_conflict"
      ? "CRM parent conflicts with Sumble hierarchy"
      : "Missing parent link";
  return `Parent company not in CRM — ${esc(item.parent_org.name)}`;
}

function dupBody(item) {
  const chosen =
    (state.decisions[item.id] || {}).survivor_crm_id ||
    item.suggested_survivor_crm_id;
  const rows = item.accounts
    .map((a) => {
      const checked = a.crm_account_id === chosen ? "checked" : "";
      return (
        `<tr><td><input type="radio" class="survivor-pick" name="sv_${item.id}" ` +
        `value="${esc(a.crm_account_id)}" ${checked} title="Keep this record" /></td>` +
        acctCells(a) + `</tr>`
      );
    })
    .join("");
  return (
    `<table class="acct-table"><tr><th title="Record to keep">Keep</th>` +
    ACCT_HEAD.slice(4) + rows + `</table>` +
    `<div class="dim chain">Accepting merges every other record into the ` +
    `selected survivor.</div>`
  );
}

function psBody(item) {
  const rows = [
    ["child", "Child", item.child],
    ["parent", "Suggested parent", item.suggested_parent],
    ["conflict", "Current CRM parent", item.current_parent],
  ]
    .filter(([, , a]) => a)
    .map(
      ([cls, label, a]) =>
        `<tr><td><span class="role-tag ${cls}">${label}</span></td>` +
        acctCells(a) + `</tr>`
    )
    .join("");
  const chain = item.chain && item.chain.length
    ? `<div class="chain">Sumble hierarchy: <b>${item.chain.map(esc).join(" → ")}</b></div>`
    : "";
  return `${chain}<table class="acct-table"><tr><th></th>${ACCT_HEAD.slice(4)}${rows}</table>`;
}

function pxBody(item) {
  const p = item.parent_org;
  const emp = p.employee_count_int
    ? Number(p.employee_count_int).toLocaleString()
    : "";
  const head =
    `<div class="chain">Suggested new parent account: <b>${esc(p.name)}</b> ` +
    `(${esc(p.domain)}${emp ? `, ${emp} employees` : ""}) ` +
    (p.sumble_url
      ? `<a href="${esc(p.sumble_url)}" target="_blank" rel="noopener">Sumble ↗</a>`
      : "") +
    altLine({
      sumble_name_alternates: p.name_alternates,
      sumble_url_alternates: p.url_alternates,
    }) +
    `</div>`;
  const rows = item.children
    .map(
      (a) =>
        `<tr><td><span class="role-tag child">Child</span></td>` +
        acctCells(a) + `</tr>`
    )
    .join("");
  return `${head}<table class="acct-table"><tr><th></th>${ACCT_HEAD.slice(4)}${rows}</table>`;
}

function renderUnmatched(item) {
  const a = item.accounts[0];
  const name = a.crm_url
    ? `<a href="${esc(a.crm_url)}" target="_blank" rel="noopener">` +
      `${esc(a.crm_name)} ↗</a>`
    : esc(a.crm_name);
  return (
    `<div class="finding"><div class="finding-head">` +
    `<span class="badge info">no match</span>` +
    `<span class="finding-title">${name}</span>` +
    `<span class="finding-id">${esc(a.crm_account_id)}</span></div>` +
    `<div class="dim chain">${esc(a.crm_domain || "no domain")} — not matched to ` +
    `any Sumble org (often shells, typos, or very small entities; also worth a ` +
    `look when cleaning).</div></div>`
  );
}

function decideRow(item, dec) {
  const note = esc((state.decisions[item.id] || {}).note || "");
  return (
    `<div class="decide">` +
    `<button class="btn accept ${dec === "accept" ? "on" : ""}" data-d="accept">Accept</button>` +
    `<button class="btn reject ${dec === "reject" ? "on" : ""}" data-d="reject">Reject</button>` +
    `<button class="btn skip ${dec === "skip" ? "on" : ""}" data-d="skip">Skip</button>` +
    `<input class="note-input" placeholder="Note (optional)" value="${note}" />` +
    `</div>`
  );
}

/* ---------- events ---------- */

function bindFindingEvents(main) {
  main.querySelectorAll(".finding[data-id]").forEach((el) => {
    const id = el.dataset.id;
    el.querySelectorAll(".decide .btn").forEach((btn) =>
      btn.addEventListener("click", () => {
        const current = decisionOf(id);
        const next = current === btn.dataset.d ? null : btn.dataset.d;
        decide(id, { decision: next });
      })
    );
    const noteEl = el.querySelector(".note-input");
    if (noteEl)
      noteEl.addEventListener("change", () =>
        decide(id, { decision: decisionOf(id), note: noteEl.value }, false)
      );
    el.querySelectorAll(".survivor-pick").forEach((radio) =>
      radio.addEventListener("change", () =>
        decide(id, { decision: decisionOf(id), survivor_crm_id: radio.value }, false)
      )
    );
  });
}

async function decide(id, payload, rerender = true) {
  if (payload.decision === "undecided") payload.decision = null;
  const resp = await fetch("/api/decide", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ finding_id: id, ...payload }),
  });
  const data = await resp.json();
  if (data.decisions) state.decisions = data.decisions;
  renderProgress();
  if (rerender) render();
}

init();
