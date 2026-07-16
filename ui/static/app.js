/* lp2graph demo UI — front-end logic.
   No framework, no build. Talks to the FastAPI server in ../server.py. */

const $ = (sel) => document.querySelector(sel);

const els = {
  source: $("#source"),
  examples: $("#examples"),
  viewSeg: $("#viewSeg"),
  cards: $("#cards"),
  translate: $("#translate"),
  graphHost: $("#graphHost"),
  graphTitle: $("#graphTitle"),
  graphMeta: $("#graphMeta"),
  errorBar: $("#errorBar"),
  detail: $("#detail"),
  familyBadge: $("#familyBadge"),
  footStatus: $("#footStatus"),
  keyBar: $("#keyBar"),
  keyInput: $("#keyInput"),
  keySave: $("#keySave"),
  keyMsg: $("#keyMsg"),
  keyBtn: $("#keyBtn"),
};

let state = {
  view: "schema",
  examples: [],
  indices: [],
  authRequired: false,
};

// API key — kept in localStorage, sent as the X-API-Key header.
let apiKey = localStorage.getItem("lp2graph_key") || "";

function authHeaders() {
  return apiKey ? { "X-API-Key": apiKey } : {};
}

// Wrap fetch so every API call carries the key and a 401 re-opens the key bar.
async function apiFetch(url, opts = {}) {
  opts.headers = Object.assign({}, opts.headers, authHeaders());
  const res = await fetch(url, opts);
  if (res.status === 401) {
    apiKey = "";
    localStorage.removeItem("lp2graph_key");
    state.authRequired = true;
    showKeyBar("That API key was rejected — paste a valid one.");
    throw new Error("unauthorized");
  }
  return res;
}

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------
init();

async function init() {
  bindControls();
  bindKeyBar();

  // Does the server want a key? Ask before hitting any gated endpoint.
  try {
    const res = await fetch("/api/auth/check");
    const j = await res.json();
    state.authRequired = !!j.auth_required;
  } catch {
    state.authRequired = false;
  }

  if (state.authRequired) {
    els.keyBtn.hidden = false;
    if (!apiKey) {
      showKeyBar();
      setStatus("enter your API key to begin");
      return; // wait for the user to unlock; loadAndTranslate() runs on save
    }
  }

  await loadAndTranslate();
}

async function loadAndTranslate() {
  try {
    const res = await apiFetch("/api/examples");
    state.examples = await res.json();
    populateExamples();
    // Load a juicy default: prefer the Big-M MILP, else the first one.
    const def =
      state.examples.find((e) => e.id === "mip_2_1_big_m") || state.examples[0];
    if (def) {
      els.examples.value = def.id;
      els.source.value = def.source;
      updateFamilyFromSource();
      // Auto-translate so the demo opens warm, not empty.
      translate();
    }
  } catch (e) {
    if (String(e).includes("unauthorized")) return; // key bar already shown
    setStatus("could not load examples — server running?");
  }
}

// ---------------------------------------------------------------------------
// API-key bar
// ---------------------------------------------------------------------------
function showKeyBar(msg) {
  els.keyBar.hidden = false;
  els.keyMsg.textContent = msg || "";
  els.keyInput.value = apiKey;
  els.keyInput.focus();
}

function bindKeyBar() {
  const save = () => {
    const v = els.keyInput.value.trim();
    if (!v) {
      els.keyMsg.textContent = "Key can't be empty.";
      return;
    }
    apiKey = v;
    localStorage.setItem("lp2graph_key", v);
    els.keyBar.hidden = true;
    els.keyMsg.textContent = "";
    setStatus("unlocked");
    if (state.examples.length) translate();
    else loadAndTranslate();
  };
  els.keySave.addEventListener("click", save);
  els.keyInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") save();
  });
  els.keyBtn.addEventListener("click", () => showKeyBar("Update your API key."));
}

function populateExamples() {
  const groups = {};
  for (const ex of state.examples) {
    (groups[ex.group] = groups[ex.group] || []).push(ex);
  }
  for (const [group, items] of Object.entries(groups)) {
    const og = document.createElement("optgroup");
    og.label = group;
    for (const ex of items) {
      const o = document.createElement("option");
      o.value = ex.id;
      o.textContent = `${ex.name}`;
      og.appendChild(o);
    }
    els.examples.appendChild(og);
  }
}

// ---------------------------------------------------------------------------
// Controls
// ---------------------------------------------------------------------------
function bindControls() {
  els.examples.addEventListener("change", () => {
    const ex = state.examples.find((e) => e.id === els.examples.value);
    if (ex) {
      els.source.value = ex.source;
      updateFamilyFromSource();
      translate();
    }
  });

  els.viewSeg.addEventListener("click", (e) => {
    const btn = e.target.closest(".seg-btn");
    if (!btn) return;
    [...els.viewSeg.children].forEach((b) => b.classList.remove("is-active"));
    btn.classList.add("is-active");
    state.view = btn.dataset.view;
    els.cards.hidden = state.view !== "ground";
    renderCardInputs();
    if (els.source.value.trim()) translate();
  });

  els.translate.addEventListener("click", translate);

  // Local family hint as you type, plus Cmd/Ctrl+Enter to translate.
  els.source.addEventListener("input", debounce(updateFamilyFromSource, 250));
  els.source.addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      e.preventDefault();
      translate();
    }
    // Tab inserts two spaces instead of leaving the editor.
    if (e.key === "Tab") {
      e.preventDefault();
      const s = els.source;
      const p = s.selectionStart;
      s.value = s.value.slice(0, p) + "  " + s.value.slice(s.selectionEnd);
      s.selectionStart = s.selectionEnd = p + 2;
    }
  });
}

function renderCardInputs() {
  els.cards.innerHTML = "";
  if (state.view !== "ground") return;
  const idx = currentIndices();
  if (!idx.length) {
    els.cards.innerHTML =
      '<span class="card-input"><label>no index families</label></span>';
    return;
  }
  for (const name of idx) {
    const wrap = document.createElement("span");
    wrap.className = "card-input";
    wrap.innerHTML = `<label>|${name}|</label><input type="number" min="1" max="12" value="4" data-idx="${name}">`;
    wrap.querySelector("input").addEventListener("change", () => {
      if (els.source.value.trim()) translate();
    });
    els.cards.appendChild(wrap);
  }
}

function currentIndices() {
  try {
    const data = JSON.parse(els.source.value);
    return (data.indices || []).map((i) => i.name);
  } catch {
    return state.indices;
  }
}

function gatherCards() {
  const cards = {};
  els.cards.querySelectorAll("input[data-idx]").forEach((inp) => {
    cards[inp.dataset.idx] = parseInt(inp.value, 10) || 4;
  });
  return cards;
}

// ---------------------------------------------------------------------------
// Family detection — local mirror of the server logic for instant feedback
// ---------------------------------------------------------------------------
const INT_DOMAINS = new Set(["integer", "binary"]);
const CONT_DOMAINS = new Set(["continuous", "non_negative"]);

function localDetect(data) {
  const domains = (data.variables || []).map((v) => v.domain);
  const hasInt = domains.some((d) => INT_DOMAINS.has(d));
  const hasCont = domains.some((d) => CONT_DOMAINS.has(d));
  if (!domains.length) return { detected: null };
  if (hasInt && hasCont) return { detected: "milp" };
  if (hasInt) return { detected: "mip" };
  return { detected: "lp" };
}

function updateFamilyFromSource() {
  try {
    const data = JSON.parse(els.source.value);
    const det = localDetect(data);
    paintFamily({ detected: det.detected, declared: data.family });
  } catch {
    paintFamily(null);
  }
}

function paintFamily(family) {
  const b = els.familyBadge;
  b.className = "family-badge";
  const val = b.querySelector(".fb-value");
  if (!family || !family.detected) {
    b.classList.add("is-empty");
    val.textContent = "—";
    return;
  }
  b.classList.add(`fam-${family.detected}`);
  val.textContent = family.detected;
  if (family.declared && family.declared !== family.detected) {
    b.classList.add("mismatch");
    b.title = `Declared "${family.declared}", detected "${family.detected}"`;
  } else {
    b.title = "Deterministically detected from variable domains";
  }
}

// ---------------------------------------------------------------------------
// Translate
// ---------------------------------------------------------------------------
async function translate() {
  const source = els.source.value;
  if (!source.trim()) return;
  setBusy(true);
  setStatus("translating…");
  hideError();

  try {
    const res = await apiFetch("/api/translate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        source,
        view: state.view,
        cards: gatherCards(),
      }),
    });
    const data = await res.json();

    if (data.family) paintFamily(data.family);

    if (!data.ok) {
      showError(data.error);
      setStatus("error");
      return;
    }

    state.indices = data.indices || [];
    if (state.view === "ground" && !els.cards.children.length) renderCardInputs();

    showGraph(data);
    showDetail(data);
    setStatus(`ok · ${data.meta.nodes} nodes · ${data.meta.edges} edges`);
  } catch (e) {
    if (String(e).includes("unauthorized")) {
      setStatus("locked — enter your API key");
    } else {
      showError({ kind: "network", message: String(e) });
      setStatus("network error");
    }
  } finally {
    setBusy(false);
  }
}

function showGraph(data) {
  els.graphHost.innerHTML = data.svg;
  els.graphTitle.textContent = data.meta.name || "Generated graph";
  els.graphMeta.textContent = `${data.view} view`;
}

function showDetail(data) {
  const m = data.meta;
  const fam = data.family || {};
  const s = data.metrics.structural || {};
  const flags = data.metrics.flags || {};

  const famLine = fam.detected
    ? `<div class="kv"><span class="k">family (detected)</span><span class="v">${fam.detected.toUpperCase()}</span>
         <span class="k">declared</span><span class="v">${(fam.declared||"—").toUpperCase()}</span></div>
       <p class="detail-empty" style="margin:8px 0 0">${esc(fam.reason||"")}</p>`
    : "";

  const counts = `
    <div class="kv">
      <span class="k">variables</span><span class="v">${m.n_variables}</span>
      <span class="k">constraints</span><span class="v">${m.n_constraints}</span>
      <span class="k">index families</span><span class="v">${m.n_indices}</span>
      <span class="k">parameters</span><span class="v">${m.n_parameters}</span>
      <span class="k">graph nodes</span><span class="v">${m.nodes}</span>
      <span class="k">graph edges</span><span class="v">${m.edges}</span>
    </div>`;

  const tagChips = (m.tags || []).length
    ? `<div class="chips">${m.tags.map((t) => `<span class="chip">${esc(t)}</span>`).join("")}</div>`
    : "";

  const metricOrder = [
    "edge_density",
    "constraint_variable_ratio",
    "minimal_size",
    "graph_diameter",
    "model_coherence",
  ];
  const metricRows = metricOrder
    .filter((k) => s[k])
    .map((k) => {
      const v = s[k].value;
      const shown = typeof v === "number" ? round(v) : v;
      return `<div class="metric-row"><span class="mk">${pretty(k)}<small>${esc(s[k].explanation||"")}</small></span><span class="mv">${shown}</span></div>`;
    })
    .join("");

  const flagRows = Object.entries(flags)
    .map(([k, f]) => {
      const on = !!f.value;
      return `<div class="flag ${on ? "on" : "off"}"><span class="pin"></span>${pretty(k.replace(/^has_/, ""))}</div>`;
    })
    .join("");

  els.detail.innerHTML = `
    ${famLine ? `<h3>Family</h3>${famLine}` : ""}
    ${m.description ? `<h3>Description</h3><p class="detail-empty">${esc(m.description)}</p>` : ""}
    <h3>Size</h3>${counts}
    ${tagChips ? `<h3>Tags</h3>${tagChips}` : ""}
    <h3>Structural metrics</h3>${metricRows || '<p class="detail-empty">—</p>'}
    <h3>Presence flags</h3><div class="flags">${flagRows || '<p class="detail-empty">—</p>'}</div>
  `;
}

// ---------------------------------------------------------------------------
// UI helpers
// ---------------------------------------------------------------------------
function showError(err) {
  const parts = [`${(err.kind || "error").toUpperCase()}: ${err.message || ""}`];
  if (err.details && Array.isArray(err.details)) {
    parts.push("", ...err.details.map((d) => "• " + d));
  }
  els.errorBar.textContent = parts.join("\n");
  els.errorBar.hidden = false;
}
function hideError() {
  els.errorBar.hidden = true;
}
function setBusy(b) {
  els.translate.disabled = b;
  els.translate.classList.toggle("busy", b);
}
function setStatus(t) {
  els.footStatus.textContent = t;
}

function pretty(k) {
  return k.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
function round(n) {
  return Math.round(n * 1000) / 1000;
}
function esc(s) {
  return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}
function debounce(fn, ms) {
  let t;
  return (...a) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...a), ms);
  };
}
