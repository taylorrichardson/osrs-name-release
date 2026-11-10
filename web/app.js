// ---------------------------------------------------------------------------
// Release schedule (official batch list, published Nov 5). Each batch opens at
// 06:00 EST on its day. Update `released` here if Jagex delays a batch.
// ---------------------------------------------------------------------------
const SCHEDULE = [
  ["a", "2026-11-05"], ["b", "2026-11-06"], ["c", "2026-11-09"], ["d", "2026-11-10"],
  ["ef", "2026-11-11"], ["gh", "2026-11-12"], ["ij", "2026-11-13"], ["kl", "2026-11-16"],
  ["m", "2026-11-17"], ["no", "2026-11-18"], ["pq", "2026-11-19"], ["r", "2026-11-20"],
  ["s", "2026-11-23"], ["tu", "2026-11-24"], ["vwx", "2026-11-25"], ["yz012", "2026-11-26"],
  ["345", "2026-11-27"], ["6789", "2026-11-30"],
].map(([chars, day], i) => ({ n: i + 1, chars, at: new Date(`${day}T06:00:00-05:00`) }));
const BATCH_OF = {};
for (const b of SCHEDULE) for (const c of b.chars) BATCH_OF[c] = b;
const FIRST_RELEASE = SCHEDULE[0].at;
const isReleased = (b) => Date.now() >= b.at;
const nextBatch = () => SCHEDULE.find((b) => !isReleased(b));
const ORDER = "abcdefghijklmnopqrstuvwxyz0123456789".split("");
const PAGE = 600;
const VALUE_RANK = { extreme: 4, high: 3, medium: 2, low: 1 };
const VALUE_Q = { extreme: 90, high: 70, medium: 52, low: 25 }; // fallback if a row has no quality score
const quality = (r) => r.q ?? VALUE_Q[r.v];

const $ = (s) => document.querySelector(s);
// Hosted copy (claude.ai artifact): static snapshot, no live-check server and no printing.
const HOSTED = !["127.0.0.1", "localhost", "[::1]"].includes(location.hostname);
if (HOSTED) document.documentElement.classList.add("hosted");
// localStorage can be missing or throw inside a sandboxed frame
const store = {
  get: (k) => { try { return store.get(k); } catch { return null; } },
  set: (k, v) => { try { store.set(k, v); } catch {} },
};

// Name types. A name can match several (e.g. "axe" is 3 letters, an OSRS term and a word), so each
// name is filed under its first matching type in this order for the multi-select filter.
const TYPES = [
  ["short", "1–2 characters"], ["three", "3 letters"], ["osrs", "OSRS terms"], ["cool", "Cool words"],
  ["first", "First names"], ["word", "English words"], ["digits", "Has numbers"], ["other", "Other"],
];
const ALL_TYPES = TYPES.map(([k]) => k);
function primaryType(r) {
  if (r._pt) return r._pt;
  const t = r.types || [];
  return (r._pt = ALL_TYPES.find((k) => t.includes(k)) || "other");
}
// a dropdown of checkboxes; onChange(Set of checked keys)
function setupMulti(el, checked, onChange, options = TYPES) {
  const menu = el.querySelector(".multi-menu");
  let opts = options, cur = new Set(checked), boxes = [];
  const sync = (set) => {
    cur = new Set(set);
    boxes.forEach((b) => (b.checked = cur.has(b.value)));
    const keys = opts.map(([k]) => k), n = keys.filter((k) => cur.has(k)).length;
    el.querySelector(".multi-sum").textContent = n === keys.length ? "All" : n === 0 ? "None"
      : n <= 2 ? opts.filter(([k]) => cur.has(k)).map(([, l, short]) => short || l).join(", ") : `${n} of ${keys.length}`;
  };
  const draw = (o) => {
    opts = o;
    menu.innerHTML = `<div class="multi-acts"><a href="#" data-all>All</a> · <a href="#" data-none>None</a></div>` +
      opts.map(([k, label]) => `<label><input type="checkbox" value="${k}"> ${label}</label>`).join("");
    boxes = [...menu.querySelectorAll("input")];
    sync(cur);
  };
  const fire = () => { const set = new Set(boxes.filter((b) => b.checked).map((b) => b.value)); sync(set); onChange(set); };
  menu.addEventListener("change", fire);
  menu.addEventListener("click", (e) => {
    if (e.target.matches("[data-all],[data-none]")) {
      e.preventDefault(); boxes.forEach((b) => (b.checked = e.target.matches("[data-all]"))); fire();
    }
  });
  document.addEventListener("click", (e) => { if (!el.contains(e.target)) el.open = false; });
  draw(options);
  sync.setOptions = draw;
  return sync;
}

// "Seen" marker: names added after this moment show a NEW badge. Until you first press
// "Mark all seen", it defaults to the start of the list expansion (Nov 3, 1 PM EST).
const SEEN_KEY = "nrp.seenAt";
const DEFAULT_SEEN = "2026-11-03T18:00:00Z";
let seenAt = store.get(SEEN_KEY) || DEFAULT_SEEN;
const addedMs = (r) => (r.added ? Date.parse(r.added) : 0);
const isNew = (r) => addedMs(r) > Date.parse(seenAt);
function fmtAdded(iso) {
  if (!iso) return "–";
  const d = new Date(iso);
  return d.toLocaleDateString([], { month: "short", day: "numeric" }) + " " + d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}
function updateSeenBtn() {
  const n = ALL.filter(isNew).length;
  $("#markSeen").textContent = n ? `Mark all seen (${n.toLocaleString()} new)` : "Mark all seen";
  $("#markSeen").disabled = !n;
}
let ALL = [];
let shown = PAGE;

function batchKey(name) { return String(BATCH_OF[name[0]]?.n ?? 99); }
function batchInfo(key) {
  const b = SCHEDULE[+key - 1];
  if (!b) return { title: "Other", when: "" };
  const day = b.at.toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" });
  const time = b.at.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  const released = isReleased(b);
  return {
    title: b.chars.toUpperCase().split("").join(", "),
    when: `Batch ${b.n} · ${day} · ${time} your time`,
    released,
    first: b === nextBatch(), // highlight the next batch to open
  };
}
function batchBadge(b) {
  return b.first ? '<span class="badge">NEXT UP</span>' : b.released ? '<span class="badge rel">RELEASED</span>' : "";
}
function releaseRank(name) { return +batchKey(name); }

// ---------------------------------------------------------------------------
async function load() {
  try {
    const res = await fetch("data.json", { cache: "no-store" });
    const data = await res.json();
    const T = data.texts;
    if (T) for (const r of data.names) { r.why = (r.why || []).map((i) => T[i]); r.vWhy = T[r.vWhy]; }
    RAW = data.names.filter((r) => r.t !== "error");
    $("#stats").dataset.generated = data.generated;
    SCANNED = data.scanned || data.names.length;
  } catch {
    $("#results").innerHTML = `<div class="empty">Couldn't load data.json. Start the app with <code>python nrp.py serve</code> and open the URL it prints.</div>`;
    return;
  }
  applyReleased();
  setInterval(renderStats, 30_000);
}

// Released batches live in their own tab ("Released"); the other views only show upcoming batches.
let RAW = [];
let SCANNED = 0;
var view = "all"; // all | released | shortlist
// [key, menu label, short label for the summary] for every batch that has names in view
function batchOptions() {
  const keys = [...new Set(ALL.map((r) => batchKey(r.n)))].sort((a, b) => a - b);
  return keys.map((k) => {
    const b = batchInfo(k), day = SCHEDULE[+k - 1]?.at.toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" }) || "";
    return [k, `<b>${b.title}</b> <span class="muted">${day}${b.released ? " · released" : b.first ? " · next" : ""}</span>`, b.title];
  });
}
// batches are stored as the ones you switched OFF, so new batches start switched on
const inBatches = (hidden) => (r) => !hidden.has(batchKey(r.n));
const checkedFromHidden = (hidden) => new Set(SCHEDULE.map((b) => String(b.n)).filter((k) => !hidden.has(k)));
const hiddenFromChecked = (set) => new Set(SCHEDULE.map((b) => String(b.n)).filter((k) => !set.has(k)));
function applyReleased() {
  const rel = view === "released";
  ALL = RAW.filter((r) => batchInfo(batchKey(r.n)).released === rel);
  const opts = batchOptions();
  syncBatch.setOptions(opts); syncBatch(checkedFromHidden(BATCH_HIDE));
  if (typeof syncSlBatches === "function") { syncSlBatches.setOptions(opts); syncSlBatches(checkedFromHidden(SL.hideBatches)); }
  renderStats();
  updateSeenBtn();
  shown = PAGE;
  render();
  if (view === "shortlist") renderShortlist();
  if (typeof updateSlCount === "function") updateSlCount();
}

function renderStats() {
  const c = (t) => ALL.filter((r) => r.t === t).length;
  const nb = nextBatch();
  const nextKey = nb ? String(nb.n) : null;
  const nextLikely = ALL.filter((r) => batchKey(r.n) === nextKey && r.t === "likely").length;
  const claimed = ALL.filter((r) => r.post === "claimed").length;
  const prime = ALL.filter((r) => r.t === "likely" && (r.v === "extreme" || r.v === "high")).length;
  const ms = nb ? nb.at - Date.now() : 0;
  let cd = "All released";
  if (ms > 0) {
    const h = Math.floor(ms / 3.6e6), m = Math.floor((ms % 3.6e6) / 6e4);
    cd = h >= 24 ? `${Math.floor(h / 24)}d ${h % 24}h ${m}m` : `${h}h ${m}m`;
  }
  const gen = $("#stats").dataset.generated;
  $("#stats").innerHTML = `
    <div class="stat countdown"><b>${cd}</b><span>${nb ? `until batch ${nb.n} (${batchInfo(nextKey).title}) · ${nb.at.toLocaleString([], { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}` : "every batch is out"}</span></div>
    <div class="stat"><b>${SCANNED.toLocaleString()}</b><span>names scanned (${ALL.length.toLocaleString()} shown)</span></div>
    <div class="stat"><b style="color:var(--likely)">${c("likely").toLocaleString()}</b><span>likely</span></div>
    <div class="stat"><b style="color:var(--possible)">${c("possible").toLocaleString()}</b><span>possible</span></div>
    ${nb ? `<div class="stat"><b style="color:var(--gold)">${nextLikely.toLocaleString()}</b><span>likely in next batch (${batchInfo(nextKey).title})</span></div>` : ""}
    ${claimed ? `<div class="stat"><b style="color:var(--error)">${claimed.toLocaleString()}</b><span>detected claimed since release</span></div>` : ""}
    <div class="stat"><b style="color:var(--v-extreme)">${prime.toLocaleString()}</b><span>likely + high/extreme value</span></div>
    <div class="stat"><b>${gen ? new Date(gen).toLocaleDateString() : "–"}</b><span>data updated</span></div>`;
}

// ---------------------------------------------------------------------------
function matcher(q) {
  q = q.trim().toLowerCase().replace(/[_-]/g, " ");
  if (!q) return () => true;
  if (q.startsWith("^") && q.endsWith("$")) { const s = q.slice(1, -1); return (n) => n === s; }
  if (q.startsWith("^")) { const s = q.slice(1); return (n) => n.startsWith(s); }
  if (q.endsWith("$")) { const s = q.slice(0, -1); return (n) => n.endsWith(s); }
  return (n) => n.includes(q);
}

function filtered() {
  const q = $("#q").value;
  const m = matcher(q);
  const tiers = new Set([...document.querySelectorAll("#tiers input:checked")].map((i) => i.value));
  const values = new Set([...document.querySelectorAll("#values input:checked")].map((i) => i.value));
  const inBatch = inBatches(BATCH_HIDE);
  const types = TYPE_FILTER;
  const added = $("#added").value;
  const post = $("#post").value;
  const now = Date.now();
  const addedOk = (r) => !added || (added === "unseen" ? isNew(r)
    : now - addedMs(r) <= (added === "24h" ? 864e5 : 7 * 864e5));
  const maxlen = +$("#maxlen").value;
  let hidden = 0;
  const rows = ALL.filter((r) => {
    if (!m(r.n) || r.n.length > maxlen || !inBatch(r) || !values.has(r.v)) return false;
    if (!types.has(primaryType(r))) return false;
    if (!addedOk(r)) return false;
    if (post === "hide" ? r.post === "claimed" : post && r.post !== post) return false;
    if (!tiers.has(r.t)) { hidden++; return false; }
    return true;
  });
  const sort = $("#sort").value;
  const byName = (a, b) => a.n.length - b.n.length || a.n.localeCompare(b.n);
  if (sort === "release") rows.sort((a, b) => releaseRank(a.n) - releaseRank(b.n) || a.n.localeCompare(b.n));
  else if (sort === "score") rows.sort((a, b) => b.s - a.s || VALUE_RANK[b.v] - VALUE_RANK[a.v] || byName(a, b));
  else if (sort === "value") rows.sort((a, b) => quality(b) - quality(a) || b.s - a.s || byName(a, b));
  else if (sort === "best") rows.sort((a, b) => b.s * quality(b) - a.s * quality(a) || byName(a, b));
  else if (sort === "newest") rows.sort((a, b) => addedMs(b) - addedMs(a) || b.s * quality(b) - a.s * quality(a));
  else rows.sort((a, b) => byName(a, b) || b.s - a.s);
  return { rows, hidden, q: q.trim() };
}

const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const tierColor = { likely: "var(--likely)", possible: "var(--possible)", unlikely: "var(--unlikely)", active: "var(--active)" };

function hl(name, q) {
  const s = q.replace(/^\^|\$$/g, "").toLowerCase().replace(/[_-]/g, " ");
  const i = s ? name.indexOf(s) : -1;
  if (i < 0) return esc(name);
  return esc(name.slice(0, i)) + "<mark>" + esc(name.slice(i, i + s.length)) + "</mark>" + esc(name.slice(i + s.length));
}

function signals(r) {
  const out = [];
  if (r.osrs == null && r.rs3 == null) out.push(`<span class="sig">no hiscores</span>`);
  if (r.osrsM || r.rs3M) out.push(`<span class="sig m">ex-member</span>`);
  if (r.rm && r.rm !== "PUBLIC") out.push(`<span class="sig">RM: ${esc(r.rm.toLowerCase().replace(/_/g, " "))}</span>`);
  if (r.wom && r.wom !== "none") out.push(`<span class="sig">WOM: ${esc(r.wom)}</span>`);
  return out.join("");
}

const POST = {
  claimed: ["taken", "TAKEN", "Re-checked after release: a different account is on the hiscores with this name now"],
  active: ["playing", "STILL PLAYING", "Re-checked after release: the same account gained XP since the scan, so the owner is active and the name won't release"],
  freed: ["freed", "FREED", "Re-checked after release: the old account is gone from the hiscores, so the name was released (it may still be free)"],
};
function postBadge(r) {
  const p = POST[r.post];
  return p ? ` <span class="postb ${p[0]}" title="${p[2]}">${p[1]}</span>` : "";
}

function rowHtml(r, q) {
  const pinned = SL.pins.has(r.n);
  return `<tr class="r" data-n="${esc(r.n)}">
    <td class="pincell"><button class="pin${pinned ? " on" : ""}" data-pin="${esc(r.n)}" title="${pinned ? "Unpin" : "Pin to shortlist"}">${pinned ? "★" : "☆"}</button></td>
    <td class="name">${hl(r.n, q)}${postBadge(r)}${isNew(r) ? ' <span class="newb">NEW</span>' : ""}</td>
    <td class="num">${r.n.length}</td>
    <td><span class="val ${r.v}" title="${esc(r.vWhy || "")}">${r.v} <b class="q">${quality(r)}</b></span></td>
    <td><span class="bar"><i style="width:${r.s}%;background:${tierColor[r.t]}"></i></span><span class="num">${r.s}</span>
        <span class="pill ${r.t}">${r.t}</span></td>
    <td class="num hide-sm">${r.osrs ?? "–"}</td>
    <td class="num hide-sm">${r.rs3 ?? "–"}</td>
    <td class="hide-sm">${signals(r)}</td>
    <td class="num hide-sm added">${fmtAdded(r.added)}</td></tr>`;
}
const THEAD = `<thead><tr><th></th><th>Name</th><th>Len</th><th>Value</th><th>Likelihood</th><th class="hide-sm">OSRS total</th><th class="hide-sm">RS3 total</th><th class="hide-sm">Signals</th><th class="hide-sm">Added</th></tr></thead>`;

function outcomeCounts(k) {
  const rows = ALL.filter((r) => batchKey(r.n) === k);
  const n = (st) => rows.filter((r) => r.post === st).length;
  const checked = rows.filter((r) => r.post).length;
  if (!checked) return ` · <span class="muted">not re-checked yet</span>`;
  return ` · <b class="out-taken">${n("claimed")} taken</b> · <b class="out-freed">${n("freed")} freed</b>`;
}

function render() {
  const { rows, hidden, q } = filtered();
  const page = rows.slice(0, shown);
  let html = "";
  if (!rows.length) {
    html = `<div class="empty">No matches${hidden ? ` (${hidden} hidden by the tier filters, <a href="#" id="showAll">show all tiers</a>)` : ""}.
      ${q && $("#live").classList.contains("offline") === false ? `<br>Not in the dataset? Use “Check any name live” above.` : ""}</div>`;
  } else if ($("#sort").value === "release") {
    const groups = new Map();
    for (const r of page) { const k = batchKey(r.n); (groups.get(k) || groups.set(k, []).get(k)).push(r); }
    const totals = new Map();
    for (const r of rows) totals.set(batchKey(r.n), (totals.get(batchKey(r.n)) || 0) + 1);
    for (const [k, list] of groups) {
      const b = batchInfo(k);
      html += `<section class="group${b.first ? " first" : ""}${b.released ? " released" : ""}"><h2>${batchBadge(b)}
        ${b.title} <span class="when">${b.when}</span><span class="count">${totals.get(k).toLocaleString()} names${b.released ? outcomeCounts(k) : ""}</span></h2>
        <table>${THEAD}<tbody>${list.map((r) => rowHtml(r, q)).join("")}</tbody></table></section>`;
    }
  } else {
    html = `<section class="group"><table>${THEAD}<tbody>${page.map((r) => rowHtml(r, q)).join("")}</tbody></table></section>`;
  }
  if (rows.length && hidden) html = `<p class="muted">${hidden.toLocaleString()} more matches hidden by the tier filters · <a href="#" id="showAll">show all tiers</a></p>` + html;
  $("#results").innerHTML = html;
  const more = $("#more");
  more.hidden = rows.length <= shown;
  more.textContent = `Show more (${(rows.length - shown).toLocaleString()} remaining)`;
}

// ---------------------------------------------------------------------------
document.addEventListener("click", (e) => {
  const pin = e.target.closest("[data-pin]");
  if (pin) {
    togglePin(pin.dataset.pin);
    const on = SL.pins.has(pin.dataset.pin);
    document.querySelectorAll(`[data-pin="${CSS.escape(pin.dataset.pin)}"]`).forEach((b) => {
      b.classList.toggle("on", on); b.textContent = on ? "★" : "☆"; b.title = on ? "Unpin" : "Pin to shortlist";
    });
    return;
  }
  if (e.target.closest("#shortlistView")) return; // handled by shortlist handler
  if (e.target.id === "showAll") {
    e.preventDefault();
    document.querySelectorAll("#tiers input").forEach((i) => (i.checked = true));
    shown = PAGE; render();
    return;
  }
  const tr = e.target.closest("tr.r");
  if (!tr) return;
  const next = tr.nextElementSibling;
  if (next?.classList.contains("detail")) { next.remove(); return; }
  const r = ALL.find((x) => x.n === tr.dataset.n);
  if (!r) return;
  const d = document.createElement("tr");
  d.className = "detail";
  const extra = [];
  if (r.rmLast) extra.push(`Last RS3 activity: ${new Date(r.rmLast).toLocaleDateString()}`);
  if (r.womChanged) extra.push(`Wise Old Man last XP change: ${new Date(r.womChanged).toLocaleDateString()}`);
  if (r.vWhy) extra.push(`Value: ${esc(r.v)}, quality ${quality(r)}/100 (${esc(r.vWhy)})`);
  if (r.src) extra.push(`From list: ${esc(r.src)}`);
  if (r.at) extra.push(`Checked: ${new Date(r.at).toLocaleString()}`);
  if (r.post) extra.push(`After release (${new Date(r.postAt).toLocaleString()}): ${esc(POST[r.post]?.[2] || "no change on the hiscores")}`);
  d.innerHTML = `<td colspan="9" class="why"><ul>${r.why.map((w) => `<li>${esc(w)}</li>`).join("")}</ul>${extra.join(" · ")}</td>`;
  tr.after(d);
});

let t;
const rerender = () => { shown = PAGE; clearTimeout(t); t = setTimeout(render, 120); };
$("#q").addEventListener("input", rerender);
let BATCH_HIDE = new Set();
const syncBatch = setupMulti($("#batch"), new Set(), (set) => { BATCH_HIDE = hiddenFromChecked(set); rerender(); }, []);
let TYPE_FILTER = new Set(ALL_TYPES);
setupMulti($("#type"), TYPE_FILTER, (set) => { TYPE_FILTER = set; rerender(); });
["#added", "#post", "#maxlen", "#sort"].forEach((s) => $(s).addEventListener("change", rerender));
$("#tiers").addEventListener("change", rerender);
$("#values").addEventListener("change", rerender);
$("#markSeen").addEventListener("click", () => {
  const latest = ALL.reduce((m, r) => Math.max(m, addedMs(r)), 0);
  seenAt = new Date(Math.max(latest, Date.now())).toISOString();
  store.set(SEEN_KEY, seenAt);
  updateSeenBtn(); rerender();
  if (view === "shortlist") renderShortlist();
});
$("#more").addEventListener("click", () => { shown += PAGE; render(); });

$("#checkForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const name = $("#checkName").value.trim();
  $("#checkMsg").textContent = "Looking up… (Wise Old Man can take a few seconds)";
  $("#checkResult").innerHTML = "";
  try {
    const res = await fetch(`/api/check?name=${encodeURIComponent(name)}`);
    const r = await res.json();
    if (!res.ok) throw new Error(r.error || res.statusText);
    $("#checkMsg").textContent = `${batchInfo(batchKey(r.n)).when}`;
    const i = ALL.findIndex((x) => x.n === r.n);
    if (i >= 0) ALL[i] = r; else ALL.push(r);
    $("#checkResult").innerHTML = `<table>${THEAD}<tbody>${rowHtml(r, "")}</tbody></table>`;
    $("#checkResult tr.r").click();
  } catch (err) {
    $("#checkMsg").textContent = `Lookup failed: ${err.message}`;
  }
});

// ---------------------------------------------------------------------------
// Shortlist: top picks per batch + pinned names, with copy buttons and
// per-name status, saved in localStorage.
// ---------------------------------------------------------------------------
const SL_KEY = "nrp.shortlist.v1";
const STATUSES = {
  claimed: { label: "✓ <span class=lbl>Claimed</span>", title: "I got this name" },
  taken: { label: "✗ <span class=lbl>Taken</span>", title: "Checked: someone else has it / not available" },
  notyet: { label: "⏳ <span class=lbl>Not yet</span>", title: "Not released yet: try again in a later batch or day" },
};
const SL = (() => {
  let raw = {};
  try { raw = JSON.parse(store.get(SL_KEY)) || {}; } catch {}
  return {
    pins: new Set(raw.pins || []),
    dismissed: new Set(raw.dismissed || []),
    status: raw.status || {},
    per: raw.per || 25,
    pinnedOnly: !!raw.pinnedOnly,
    hideDone: !!raw.hideDone,
    types: new Set(raw.types || (raw.type ? [raw.type] : ALL_TYPES)),
    hideBatches: new Set(raw.hideBatches || []),
    values: new Set(raw.values || ["extreme", "high", "medium", "low"]),
  };
})();
function saveSL() {
  store.set(SL_KEY, JSON.stringify({
    pins: [...SL.pins], dismissed: [...SL.dismissed], status: SL.status,
    per: SL.per, pinnedOnly: SL.pinnedOnly, hideDone: SL.hideDone, types: [...SL.types], hideBatches: [...SL.hideBatches], values: [...SL.values],
  }));
  updateSlCount();
}
function togglePin(n) {
  if (SL.pins.has(n)) SL.pins.delete(n); else { SL.pins.add(n); SL.dismissed.delete(n); }
  saveSL();
  if (view === "shortlist") renderShortlist();
}
const best = (r) => r.s * quality(r);

function shortlistGroups() {
  const byKey = new Map();
  for (const r of ALL) {
    const k = batchKey(r.n);
    (byKey.get(k) || byKey.set(k, []).get(k)).push(r);
  }
  const keys = [...byKey.keys()].sort((a, b) => a - b);
  const groups = [];
  for (const k of keys) {
    if (SL.hideBatches.has(k)) continue;
    const cands = byKey.get(k);
    const pinned = cands.filter((r) => SL.pins.has(r.n)).sort((a, b) => best(b) - best(a));
    let auto = [];
    if (!SL.pinnedOnly) {
      auto = cands
        .filter((r) => !SL.pins.has(r.n) && !SL.dismissed.has(r.n) && (r.t === "likely" || r.t === "possible")
          && SL.types.has(primaryType(r)) && SL.values.has(r.v))
        .sort((a, b) => best(b) - best(a) || a.n.length - b.n.length || a.n.localeCompare(b.n))
        .slice(0, Math.max(SL.per - pinned.length, 0));
    }
    let list = [...pinned, ...auto];
    if (SL.hideDone) list = list.filter((r) => SL.status[r.n] !== "taken" && r.post !== "claimed");
    if (list.length) groups.push({ k, list });
  }
  return groups;
}

function slRowHtml(r, i) {
  const st = SL.status[r.n] || "";
  const pinned = SL.pins.has(r.n);
  return `<tr class="sl-row ${st}" data-n="${esc(r.n)}">
    <td class="num">${i + 1}</td>
    <td class="name">${esc(r.n)}${postBadge(r)}${isNew(r) ? ' <span class="newb">NEW</span>' : ""}</td>
    <td class="noprint"><button class="copy" data-copy="${esc(r.n)}" title="Copy name">Copy</button></td>
    <td><span class="val ${r.v}" title="${esc(r.vWhy || "")}">${r.v} <b class="q">${quality(r)}</b></span></td>
    <td><span class="num">${r.s}</span> <span class="pill ${r.t}">${r.t}</span></td>
    <td class="status">${Object.entries(STATUSES).map(([k, s]) =>
      `<button class="st st-${k}${st === k ? " on" : ""}" data-status="${k}" title="${s.title}">${s.label}</button>`).join("")}
      <span class="printbox">☐</span></td>
    <td class="noprint actions">
      <button class="pin${pinned ? " on" : ""}" data-pin="${esc(r.n)}" title="${pinned ? "Unpin" : "Pin (always keep in shortlist)"}">${pinned ? "★" : "☆"}</button>
      ${pinned ? "" : `<button class="dismiss" data-dismiss="${esc(r.n)}" title="Remove from shortlist">✕</button>`}
    </td></tr>`;
}

function renderShortlist() {
  $("#slPer").value = String(SL.per);
  $("#slPinnedOnly").checked = SL.pinnedOnly;
  $("#slHideDone").checked = SL.hideDone;
  syncSlTypes(SL.types);
  document.querySelectorAll("#slValues input").forEach((i) => (i.checked = SL.values.has(i.value)));
  const groups = shortlistGroups();
  if (!groups.length) {
    $("#shortlist").innerHTML = `<div class="empty">Nothing here yet. Pin names with ☆ in the All names view${SL.pinnedOnly ? ", or untick “Pinned only”" : ""}.</div>`;
    return;
  }
  // remember which batches are expanded
  const open = new Set([...document.querySelectorAll("#shortlist details[open]")].map((d) => d.dataset.k));
  const firstRender = !$("#shortlist details");
  $("#shortlist").innerHTML = groups.map(({ k, list }) => {
    const b = batchInfo(k);
    const done = list.filter((r) => SL.status[r.n]).length;
    const claimed = list.filter((r) => SL.status[r.n] === "claimed").length;
    const isOpen = firstRender ? (b.first || list.some((r) => SL.pins.has(r.n))) : open.has(k);
    return `<details class="group sl-group${b.first ? " first" : ""}${b.released ? " released" : ""}" data-k="${esc(k)}" ${isOpen ? "open" : ""}>
      <summary><h2>${batchBadge(b)} ${b.title}
        <span class="when">${b.when}</span>
        <span class="count">${done}/${list.length} checked${claimed ? ` · <b class="gold">${claimed} claimed</b>` : ""}</span>
        <button class="copyall noprint" data-copyall="${esc(k)}" title="Copy all unchecked names in this batch, one per line">Copy unchecked</button>
      </h2></summary>
      <table><thead><tr><th>#</th><th>Name</th><th class="noprint"></th><th>Value</th><th>Likelihood</th><th>Result</th><th class="noprint"></th></tr></thead>
      <tbody>${list.map(slRowHtml).join("")}</tbody></table></details>`;
  }).join("");
}

function updateSlCount() {
  const n = SL.pins.size;
  $("#slCount").textContent = n ? `${n} pinned` : "";
}

async function copyText(text, btn) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const ta = Object.assign(document.createElement("textarea"), { value: text });
    document.body.append(ta); ta.select(); document.execCommand("copy"); ta.remove();
  }
  if (btn) {
    const old = btn.textContent;
    btn.textContent = "Copied!"; btn.classList.add("ok");
    setTimeout(() => { btn.textContent = old; btn.classList.remove("ok"); }, 1100);
  }
}

$("#shortlistView").addEventListener("click", (e) => {
  const t = e.target;
  if (t.dataset.copy) return copyText(t.dataset.copy, t);
  if (t.dataset.copyall) {
    e.preventDefault(); // don't toggle the <details>
    const g = shortlistGroups().find((g) => g.k === t.dataset.copyall);
    const names = g ? g.list.filter((r) => !SL.status[r.n]).map((r) => r.n) : [];
    return copyText(names.join("\n"), t);
  }
  if (t.dataset.status) {
    const n = t.closest("tr").dataset.n;
    if (SL.status[n] === t.dataset.status) delete SL.status[n]; else SL.status[n] = t.dataset.status;
    saveSL(); renderShortlist();
    return;
  }
  if (t.dataset.dismiss) {
    SL.dismissed.add(t.dataset.dismiss);
    saveSL(); renderShortlist();
  }
});

$("#slPer").addEventListener("change", (e) => { SL.per = +e.target.value; saveSL(); renderShortlist(); });
$("#slValues").addEventListener("change", (e) => {
  if (e.target.checked) SL.values.add(e.target.value); else SL.values.delete(e.target.value);
  saveSL(); renderShortlist();
});
const syncSlBatches = setupMulti($("#slBatch"), checkedFromHidden(SL.hideBatches),
  (set) => { SL.hideBatches = hiddenFromChecked(set); saveSL(); renderShortlist(); }, []);
const syncSlTypes = setupMulti($("#slType"), SL.types, (set) => { SL.types = set; saveSL(); renderShortlist(); });
$("#slPinnedOnly").addEventListener("change", (e) => { SL.pinnedOnly = e.target.checked; saveSL(); renderShortlist(); });
$("#slHideDone").addEventListener("change", (e) => { SL.hideDone = e.target.checked; saveSL(); renderShortlist(); });
$("#slRestore").addEventListener("click", () => { SL.dismissed.clear(); saveSL(); renderShortlist(); });
let clearArmed = null;
$("#slClear").addEventListener("click", (e) => {
  // two-click confirm instead of a blocking dialog
  if (!clearArmed) {
    e.target.textContent = "Click again to clear all";
    clearArmed = setTimeout(() => { e.target.textContent = "Clear statuses"; clearArmed = null; }, 3000);
    return;
  }
  clearTimeout(clearArmed); clearArmed = null;
  e.target.textContent = "Clear statuses";
  SL.status = {}; saveSL(); renderShortlist();
});
$("#slPrint").addEventListener("click", () => {
  document.querySelectorAll("#shortlist details").forEach((d) => (d.open = true));
  window.print();
});

// view switching (also remembered in the URL: #shortlist / #released)
function setView(v) {
  const changed = (view === "released") !== (v === "released");
  view = v;
  document.querySelectorAll(".tabs button").forEach((b) => b.classList.toggle("on", b.dataset.view === v));
  $("#allView").hidden = v === "shortlist";
  $("#shortlistView").hidden = v !== "shortlist";
  document.body.classList.toggle("sl-mode", v === "shortlist");
  document.body.classList.toggle("rel-mode", v === "released");
  history.replaceState(null, "", v === "all" ? location.pathname : "#" + v);
  if (changed) { BATCH_HIDE = new Set(); applyReleased(); }
  else if (v === "shortlist") renderShortlist(); else render();
}
document.querySelectorAll(".tabs button").forEach((b) => b.addEventListener("click", () => setView(b.dataset.view)));

load().then(() => {
  updateSlCount();
  if (location.hash === "#shortlist" || location.hash === "#released") setView(location.hash.slice(1));
});


// phones: filters fold away behind a button so the list gets the screen
$("#filtersBtn").addEventListener("click", () => {
  const on = $(".controls").classList.toggle("show-filters");
  $("#filtersBtn").setAttribute("aria-expanded", on);
});
