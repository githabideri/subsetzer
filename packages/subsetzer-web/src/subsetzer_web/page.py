"""Embedded web UI for subsetzer-web (single file, no build step).

Styling follows the llm-hub house design (llmlab/hub/ui): near-black
panels, monospace, small uppercase labels, thin bars, bordered buttons,
uppercase state words.
"""
from __future__ import annotations

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>subsetzer</title>
<style>
  :root {
    --bg:   #101112;
    --panel:#16181a;
    --line: #26292d;
    --line2:#1d2023;
    --text: #d6d9dc;
    --dim:  #8b9097;
    --faint:#5c6168;
    --ok:   #71b893;
    --err:  #cf6e62;
    --warn: #cf9d4e;
  }
  * { box-sizing:border-box; margin:0; }
  html { background:var(--bg); }
  body {
    background:var(--bg); color:var(--text);
    font:13px/1.5 ui-monospace,"SF Mono","Cascadia Code",Menlo,Consolas,monospace;
    font-variant-numeric:tabular-nums;
    padding:20px 20px 28px; max-width:960px; margin:0 auto;
  }
  header { display:flex; align-items:baseline; gap:14px; flex-wrap:wrap; margin-bottom:16px; }
  h1 { font-size:15px; font-weight:700; letter-spacing:.02em; }
  .sub { color:var(--faint); font-size:12px; }
  .tick { color:var(--faint); font-size:11px; margin-left:auto; }

  .card { background:var(--panel); border:1px solid var(--line); border-radius:6px;
          padding:14px 16px 12px; margin-bottom:12px; }
  .card h2 { font-size:14px; font-weight:700; }
  .card-head { display:flex; align-items:baseline; gap:10px; margin-bottom:4px; }
  .kind { color:var(--faint); font-size:11px; }

  .label { font-size:10px; letter-spacing:.10em; text-transform:uppercase;
           color:var(--faint); margin:12px 0 5px; }
  .row { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
  input[type=text], input[type=number], select, input[type=file] {
    width:100%; background:var(--line2); color:var(--text); border:1px solid var(--line);
    border-radius:3px; padding:6px 9px; font:inherit; font-size:13px;
  }
  input[type=file] { padding:5px 9px; color:var(--dim); }
  input:focus, select:focus { outline:none; border-color:var(--faint); }
  .hint { color:var(--faint); font-size:11px; margin-top:4px; }

  .checks { display:flex; gap:16px; margin-top:12px; }
  .checks label { display:flex; align-items:center; gap:6px; color:var(--dim);
                  font-size:12px; letter-spacing:.05em; text-transform:uppercase; }
  .checks input { accent-color:var(--ok); }

  .btn { border:1px solid var(--line); background:transparent; color:var(--dim);
         border-radius:3px; padding:5px 14px; font:inherit; font-size:11px;
         letter-spacing:.08em; text-transform:uppercase; cursor:pointer; margin-top:14px; }
  .btn:hover:not(:disabled) { background:var(--line2); color:var(--text); }
  .btn:disabled { opacity:.4; cursor:default; }
  .btn.go { color:var(--ok); border-color:rgba(113,184,147,.45); }
  .btn.go:hover:not(:disabled) { background:rgba(113,184,147,.10); }
  .btn.abort { color:var(--err); border-color:rgba(207,110,98,.45); }
  .btn.abort:hover { background:rgba(207,110,98,.10); }

  .bar { height:7px; background:var(--line2); border-radius:2px; overflow:hidden;
         margin-top:12px; }
  .bar > div { height:100%; width:0%; background:var(--ok); transition:width .4s; }
  .state { margin-left:auto; font-size:11px; letter-spacing:.08em; text-transform:uppercase; }
  .state.ok   { color:var(--ok); }
  .state.err  { color:var(--err); }
  .state.warn { color:var(--warn); }
  .status { margin-top:8px; font-size:12px; color:var(--dim); min-height:18px; }
  .status .err { color:var(--err); }
  .status .ok { color:var(--ok); }
  .status a { color:var(--ok); text-decoration:none; }

  table { width:100%; border-collapse:collapse; table-layout:fixed; }
  th { color:var(--faint); font-weight:500; font-size:10px; letter-spacing:.10em;
       text-transform:uppercase; text-align:left; padding:2px 6px 5px;
       border-bottom:1px solid var(--line); white-space:nowrap; }
  td { padding:7px 6px; border-bottom:1px solid var(--line2); vertical-align:middle;
       overflow-wrap:break-word; font-size:12px; }
  tr:last-child td { border-bottom:none; }
  .c-name { width:34%; } .c-model { width:26%; } .c-dir { width:18%; }
  .c-prog { width:12%; } .c-state { width:10%; }
  .ms { font-size:11px; letter-spacing:.08em; text-transform:uppercase; white-space:nowrap; }
  .ms.queued  { color:var(--faint); }
  .ms.running { color:var(--warn); }
  .ms.done    { color:var(--ok); }
  .ms.error, .ms.aborted { color:var(--err); }
  td a { color:var(--ok); text-decoration:none; }
  .jerr { color:var(--faint); font-size:11px; }
</style>
</head>
<body>
<header>
  <h1>subsetzer</h1>
  <span class="sub">subtitle translation</span>
  <span class="tick" id="tick">connecting…</span>
</header>

<section class="card">
  <div class="card-head"><h2>translate</h2><span class="kind">srt / vtt / tsv</span></div>

  <label class="label" for="file">File</label>
  <input type="file" id="file" name="file" accept=".srt,.vtt,.tsv,.csv,.txt">

  <div class="row">
    <div>
      <label class="label" for="source">Source</label>
      <input type="text" id="source" name="source" value="auto" list="langs" placeholder="auto, Serbian, sr, zh-cn …">
    </div>
    <div>
      <label class="label" for="target">Target</label>
      <input type="text" id="target" name="target" value="English" list="langs" placeholder="English, German, de …">
    </div>
  </div>
  <datalist id="langs"></datalist>

  <div class="row">
    <div>
      <label class="label" for="model">Model</label>
      <select id="model" name="model"><option value="">loading…</option></select>
    </div>
    <div>
      <label class="label" for="cues">Cues / request</label>
      <input type="number" id="cues" name="cues_per_request" min="1" max="15" value="1">
      <div class="hint">1 = most robust · 4–8 = faster</div>
    </div>
  </div>

  <div class="checks">
    <label><input type="checkbox" id="no_punc"> no punctuation</label>
    <label><input type="checkbox" id="one_line"> one line / cue</label>
  </div>

  <div style="display:flex;align-items:center;gap:12px;margin-top:14px;">
    <button class="btn go" id="go" type="button">Translate</button>
    <div class="bar" id="barwrap" style="flex:1;visibility:hidden;"><div id="barfill"></div></div>
    <span class="state" id="state"></span>
  </div>
  <div class="status" id="status"></div>
</section>

<section class="card">
  <div class="card-head"><h2>jobs</h2><span class="kind" id="jobcount"></span></div>
  <table>
    <thead><tr><th class="c-name">file</th><th class="c-model">model</th><th class="c-dir">dir.</th>
      <th class="c-prog">progress</th><th class="c-state">state</th><th></th></tr></thead>
    <tbody id="jobrows"><tr><td colspan="6" class="jerr">none yet</td></tr></tbody>
  </table>
</section>

<script>
const $ = id => document.getElementById(id);
const TOKEN = new URLSearchParams(location.search).get("token") || "";
const url = p => TOKEN ? p + (p.includes("?") ? "&" : "?") + "token=" + encodeURIComponent(TOKEN) : p;
let es = null;

const LANGS = ["Serbian","Croatian","Bosnian","German","English","Czech","Polish","Hungarian",
  "Slovenian","Slovak","Italian","French","Spanish","Romanian","Bulgarian","Greek","Turkish",
  "Ukrainian","Russian","Macedonian","Albanian","Swedish","Norwegian","Danish","Finnish",
  "Dutch","Portuguese","Catalan","Basque","Galician","Estonian","Latvian","Lithuanian",
  "Chinese","Japanese","Korean","Arabic","Hebrew","Thai","Vietnamese"];
$("langs").innerHTML = LANGS.map(l => `<option value="${l}">`).join("");

function setState(cls, text) {
  const s = $("state");
  s.className = "state " + (cls || "");
  s.textContent = text || "";
}

async function loadModels() {
  try {
    const r = await (await fetch(url("/models"))).json();
    const sel = $("model");
    sel.innerHTML = "";
    for (const m of r.data) {
      const o = document.createElement("option");
      o.value = m.id; o.textContent = m.id;
      sel.appendChild(o);
    }
    if (!r.data.length) {
      const o = document.createElement("option");
      o.value = ""; o.textContent = "(server reported no models)";
      sel.appendChild(o);
    }
    $("tick").textContent = r.server + " · " + r.data.length + " model(s)";
  } catch (e) {
    $("model").innerHTML = '<option value="">LLM server unreachable</option>';
    $("tick").textContent = "LLM server unreachable";
    setState("err", "llm server unreachable");
  }
}
loadModels();

$("go").addEventListener("click", async () => {
  if (es) try { es.close(); } catch (_) {}
  const f = $("file").files[0];
  if (!f) {
    setState("err", "no file");
    $("status").innerHTML = '<span class="err">choose a subtitle file first</span>';
    return;
  }
  const go = $("go");
  go.disabled = true;
  $("barwrap").style.visibility = "visible";
  $("barfill").style.width = "0%";
  setState("warn", "uploading");
  $("status").innerHTML = "uploading " + f.name + " (" + (f.size/1024).toFixed(0) + " kB) …";
  try {
    const fd = new FormData();
    fd.append("file", f);
    fd.append("source", $("source").value.trim() || "auto");
    fd.append("target", $("target").value.trim() || "English");
    fd.append("model", $("model").value);
    fd.append("cues_per_request", String($("cues").value || "1"));
    fd.append("no_punc", $("no_punc").checked ? "true" : "false");
    fd.append("one_line", $("one_line").checked ? "true" : "false");
    const res = await fetch(url("/translate"), {method:"POST", body: fd});
    let body;
    try { body = await res.json(); } catch (_) { body = {detail: res.statusText}; }
    if (!res.ok) throw new Error(body.detail || ("HTTP " + res.status));
    const {job, position} = body;
    setState("warn", "queued");
    $("status").textContent = position > 1
      ? "queued — position " + position + " (jobs run serially)"
      : "running…";
    es = new EventSource(url("/jobs/" + job + "/events"));
    es.onmessage = ev => {
      const j = JSON.parse(ev.data);
      const pct = j.total ? Math.round(100 * j.done / j.total) : 0;
      $("barfill").style.width = pct + "%";
      if (j.status === "done") {
        setState("ok", "done");
        $("status").innerHTML = 'done — ' + j.done + "/" + j.total + ' cues · <a href="' + url(j.download) + '">download</a>';
        es.close(); es = null; go.disabled = false; refreshJobs();
      } else if (j.status === "error") {
        setState("err", "error");
        $("status").innerHTML = '<span class="err">' + (j.error || "unknown error") + "</span>";
        es.close(); es = null; go.disabled = false; refreshJobs();
      } else if (j.status === "aborted") {
        setState("err", "aborted");
        $("status").textContent = "aborted";
        es.close(); es = null; go.disabled = false; refreshJobs();
      } else {
        setState("warn", j.status);
        $("status").textContent = j.status === "queued"
          ? "queued (position " + (j.done || "") + ")…"
          : "translating " + j.done + "/" + j.total + " cues…";
      }
    };
    es.onerror = () => {}; // transient hiccup: the browser reconnects itself
  } catch (err) {
    setState("err", "error");
    $("status").innerHTML = '<span class="err">' + err.message + "</span>";
    go.disabled = false;
  }
});

function refreshJobs() {
  fetch(url("/jobs")).then(r => r.json()).then(jobs => {
    $("jobcount").textContent = jobs.length ? jobs.length + " shown" : "";
    const tb = $("jobrows");
    if (!jobs.length) { tb.innerHTML = '<tr><td colspan="6" class="jerr">none yet</td></tr>'; return; }
    tb.innerHTML = "";
    for (const j of jobs) {
      const tr = document.createElement("tr");
      const dir = (j.source || "auto") + " → " + (j.target || "?");
      const prog = j.total ? (j.done + "/" + j.total) : "—";
      let act = "";
      if (j.status === "done") act = '<a href="' + url(j.download) + '">download</a>';
      else if (j.status === "queued" || j.status === "running")
        act = '<a href="#" class="jabort" data-id="' + j.id + '" style="color:var(--err)">abort</a>';
      else if (j.error) act = '<span class="jerr">' + j.error.slice(0, 60) + "</span>";
      tr.innerHTML = '<td>' + j.name + '</td><td>' + (j.model || "") + '</td><td>' + dir +
        '</td><td>' + prog + '</td><td><span class="ms ' + j.status + '">' + j.status +
        '</span></td><td style="text-align:right">' + act + "</td>";
      tb.appendChild(tr);
    }
    tb.querySelectorAll(".jabort").forEach(a => a.addEventListener("click", e => {
      e.preventDefault();
      fetch(url("/jobs/" + a.dataset.id + "/abort"), {method:"POST"}).then(refreshJobs);
    }));
  }).catch(() => {});
}
refreshJobs();
setInterval(refreshJobs, 5000);
</script>
</body>
</html>
"""
