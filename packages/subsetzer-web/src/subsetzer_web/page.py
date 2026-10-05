"""Embedded web UI for subsetzer-web (single file, no build step)."""
from __future__ import annotations

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>subsetzer-web</title>
<style>
  :root { --bg:#15181d; --panel:#1e232b; --line:#2c333e; --fg:#e6e9ee; --dim:#8b95a5; --accent:#5aa9e6; --ok:#69c789; --bad:#e07a6b; }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--fg); font:15px/1.45 system-ui, sans-serif; }
  main { max-width: 860px; margin: 0 auto; padding: 28px 20px 60px; }
  h1 { font-size: 20px; font-weight: 600; }
  h1 span { color: var(--dim); font-weight: 400; font-size: 14px; }
  .card { background: var(--panel); border:1px solid var(--line); border-radius: 10px; padding: 18px; margin-top: 18px; }
  label { display:block; color: var(--dim); font-size: 13px; margin: 12px 0 4px; }
  input[type=text], input[type=number], select {
    width:100%; background:var(--bg); color:var(--fg); border:1px solid var(--line);
    border-radius:6px; padding:8px 10px; font:inherit;
  }
  input[type=file] { color: var(--dim); }
  .row { display:grid; grid-template-columns: 1fr 1fr; gap: 14px; }
  .checks { display:flex; gap:18px; margin-top:14px; }
  .checks label { display:flex; align-items:center; gap:7px; color:var(--fg); font-size:14px; margin:0; }
  button {
    margin-top:16px; background:var(--accent); color:#0c1116; border:0; border-radius:7px;
    padding:10px 18px; font:600 15px system-ui, sans-serif; cursor:pointer;
  }
  button:disabled { opacity:.45; cursor:default; }
  button.secondary { background:transparent; color:var(--dim); border:1px solid var(--line); font-weight:400; }
  button.danger { background:var(--bad); color:#14100e; }
  .progress { margin-top:16px; display:none; }
  .bar { height:8px; background:var(--bg); border-radius:4px; overflow:hidden; border:1px solid var(--line); }
  .bar > i { display:block; height:100%; width:0%; background:var(--accent); transition:width .3s; }
  .status { margin-top:8px; color:var(--dim); font-size:14px; }
  .status .err { color:var(--bad); }
  .status .ok { color:var(--ok); }
  table { width:100%; border-collapse:collapse; font-size:14px; }
  th, td { text-align:left; padding:8px 10px; border-bottom:1px solid var(--line); }
  th { color:var(--dim); font-weight:500; font-size:12px; text-transform:uppercase; letter-spacing:.05em; }
  td a { color:var(--accent); text-decoration:none; }
  .tag { font-size:12px; padding:2px 8px; border-radius:10px; border:1px solid var(--line); color:var(--dim); }
  .tag.done { color:var(--ok); border-color:var(--ok); }
  .tag.error, .tag.aborted { color:var(--bad); border-color:var(--bad); }
  .tag.running { color:var(--accent); border-color:var(--accent); }
  .hint { color:var(--dim); font-size:13px; margin-top:10px; }
</style>
</head>
<body>
<main>
  <h1>subsetzer-web <span>subtitle translation</span></h1>

  <form class="card" id="form">
    <label>Subtitle file (SRT / VTT / TSV)</label>
    <input type="file" id="file" accept=".srt,.vtt,.tsv,.csv,.txt" required>

    <div class="row">
      <div>
        <label>Source language</label>
        <input type="text" id="source" value="auto" list="langs" placeholder="auto, Serbian, sr, zh-cn …">
      </div>
      <div>
        <label>Target language</label>
        <input type="text" id="target" value="English" list="langs" placeholder="English, German, de …">
      </div>
    </div>
    <datalist id="langs"></datalist>

    <div class="row">
      <div>
        <label>Model</label>
        <select id="model"><option value="">loading…</option></select>
      </div>
      <div>
        <label>Cues per request (1 = most robust, 4–8 = faster)</label>
        <input type="number" id="cues" min="1" max="15" value="1">
      </div>
    </div>

    <div class="checks">
      <label><input type="checkbox" id="no_punc"> strip punctuation</label>
      <label><input type="checkbox" id="one_line"> one line per cue</label>
    </div>

    <button id="go">Translate</button>
    <div class="progress" id="progress">
      <div class="bar"><i id="barfill"></i></div>
      <div class="status" id="status">queued…</div>
    </div>
    <div class="hint" id="hint"></div>
  </form>

  <section class="card">
    <h1>Jobs</h1>
    <table>
      <thead><tr><th>file</th><th>model</th><th>dir.</th><th>progress</th><th>status</th><th></th></tr></thead>
      <tbody id="jobrows"><tr><td colspan="6" class="hint">none yet</td></tr></tbody>
    </table>
  </section>
</main>
<script>
const $ = id => document.getElementById(id);
let es = null;

const LANGS = ["Serbian","Croatian","Bosnian","German","English","Czech","Polish","Hungarian",
  "Slovenian","Slovak","Italian","French","Spanish","Romanian","Bulgarian","Greek","Turkish",
  "Ukrainian","Russian","Macedonian","Albanian","Swedish","Norwegian","Danish","Finnish",
  "Dutch","Portuguese","Catalan","Basque","Galician","Estonian","Latvian","Lithuanian",
  "Chinese","Japanese","Korean","Arabic","Hebrew","Thai","Vietnamese"];
$("langs").innerHTML = LANGS.map(l => `<option value="${l}">`).join("");

async function loadModels() {
  try {
    const r = await (await fetch("/models")).json();
    const sel = $("model");
    sel.innerHTML = "";
    for (const m of r.data) {
      const o = document.createElement("option");
      o.value = m.id; o.textContent = m.id;
      sel.appendChild(o);
    }
    if (!r.data.length) {
      const o = document.createElement("option");
      o.value = ""; o.textContent = "server reported no models";
      sel.appendChild(o);
    }
  } catch (e) {
    $("model").innerHTML = '<option value="">LLM server unreachable</option>';
  }
}
loadModels();

function setBusy(busy) {
  $("go").disabled = busy;
  $("file").disabled = busy;
  $("model").disabled = busy;
}

$("form").addEventListener("submit", async e => {
  e.preventDefault();
  if (es) es.close();
  if (new FormData(e.target).get("file").size === 0) return;
  setBusy(true);
  $("progress").style.display = "block";
  $("barfill").style.width = "0%";
  $("status").innerHTML = "uploading…";
  $("hint").textContent = "";
  try {
    const fd = new FormData(e.target);
    fd.append("no_punc", $("no_punc").checked ? "true" : "false");
    fd.append("one_line", $("one_line").checked ? "true" : "false");
    const res = await fetch("/translate", {method:"POST", body: fd});
    if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
    const {job, position} = await res.json();
    $("status").textContent = position > 1 ? `queued (position ${position})…` : "running…";
    es = new EventSource(`/jobs/${job}/events`);
    es.onmessage = ev => {
      const j = JSON.parse(ev.data);
      const pct = j.total ? Math.round(100 * j.done / j.total) : 0;
      $("barfill").style.width = pct + "%";
      if (j.status === "done") {
        $("status").innerHTML = `<span class="ok">done — ${j.done}/${j.total} cues</span> · <a href="${j.download}">download</a>`;
        es.close(); setBusy(false); refreshJobs();
        $("hint").textContent = "";
      } else if (j.status === "error") {
        $("status").innerHTML = `<span class="err">error: ${j.error || "unknown"}</span>`;
        es.close(); setBusy(false); refreshJobs();
      } else if (j.status === "aborted") {
        $("status").innerHTML = `<span class="err">aborted</span>`;
        es.close(); setBusy(false); refreshJobs();
      } else {
        $("status").textContent = j.status === "queued" ? `queued (position ${j.done || ""})…` : `translating ${j.done}/${j.total} cues…`;
      }
    };
  } catch (err) {
    $("status").innerHTML = `<span class="err">${err.message}</span>`;
    es = null; setBusy(false);
  }
});

function refreshJobs() {
  fetch("/jobs").then(r => r.json()).then(jobs => {
    const tb = $("jobrows");
    tb.innerHTML = "";
    if (!jobs.length) {
      tb.innerHTML = '<tr><td colspan="6" class="hint">none yet</td></tr>';
      return;
    }
    for (const j of jobs) {
      const tr = document.createElement("tr");
      const dir = `${j.source || "auto"} → ${j.target}`;
      const prog = j.total ? `${j.done}/${j.total}` : "—";
      const act = j.status === "done"
        ? `<a href="${j.download}">download</a>`
        : (j.status === "queued" || j.status === "running")
          ? `<a href="#" class="abort" data-id="${j.id}">abort</a>`
          : `<span class="hint">${j.error ? j.error.slice(0, 60) : ""}</span>`;
      tr.innerHTML = `<td>${j.name}</td><td>${j.model}</td><td>${dir}</td><td>${prog}</td>
        <td><span class="tag ${j.status}">${j.status}</span></td><td>${act}</td>`;
      tb.appendChild(tr);
    }
    tb.querySelectorAll(".abort").forEach(a => a.addEventListener("click", e => {
      e.preventDefault();
      fetch(`/jobs/${a.dataset.id}/abort`, {method:"POST"}).then(refreshJobs);
    }));
  }).catch(() => {});
}
refreshJobs();
setInterval(refreshJobs, 10000);
</script>
</body>
</html>
"""
