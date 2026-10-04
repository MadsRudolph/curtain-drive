// Curtain Drive tuning dashboard. Served by the ESPHome web_server (js_include) in place of
// the stock page: live data from /events, controls through the web_server REST calls.
// Plain JS, no libraries -- it has to fit in flash and work without internet.

const CSS = `
:root{--bg:#f4f5f7;--card:#fff;--fg:#1b1f24;--mut:#667085;--line:#e3e6ea;--grid:#eceef1;
--cur:#2563eb;--thr:#dc2626;--peak:#d97706;--duty:#059669;--pos:#7c3aed;--btn:#eef1f5}
@media (prefers-color-scheme:dark){:root{--bg:#0f1115;--card:#171a21;--fg:#e6e8eb;--mut:#8b93a1;
--line:#262b35;--grid:#20242d;--cur:#60a5fa;--thr:#f87171;--peak:#fbbf24;--duty:#34d399;--pos:#a78bfa;--btn:#222733}}
*{box-sizing:border-box}html,body{margin:0;background:var(--bg);color:var(--fg);
font:14px/1.4 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
header{display:flex;align-items:center;gap:12px;padding:10px 16px;border-bottom:1px solid var(--line);background:var(--card)}
header h1{font-size:16px;margin:0;font-weight:600}#dot{width:10px;height:10px;border-radius:50%;background:#999}
#dot.on{background:#16a34a}#hdr{color:var(--mut);font-size:12px;margin-left:auto}
main{display:grid;grid-template-columns:minmax(0,1fr) 330px;gap:12px;padding:12px 16px}
@media (max-width:900px){main{grid-template-columns:minmax(0,1fr)}}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px}
.card h2{font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:var(--mut);margin:0 0 8px;font-weight:600}
.charts{display:flex;flex-direction:column;gap:12px;min-width:0}
.bar{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-bottom:6px}
.bar .t{font-weight:600;margin-right:auto}.legend{display:flex;gap:12px;font-size:12px;color:var(--mut);flex-wrap:wrap}
.legend i{display:inline-block;width:14px;height:3px;vertical-align:middle;margin-right:4px}
canvas{display:block;width:100%;touch-action:none}#c_cur{height:max(340px,52vh)}#c_duty{height:170px}
button,select,input{font:inherit;color:inherit}
button{background:var(--btn);border:1px solid var(--line);border-radius:7px;padding:6px 10px;cursor:pointer}
button:hover{border-color:var(--mut)}button.on{background:var(--cur);color:#fff;border-color:var(--cur)}
.big{display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px}.big button{padding:10px 0;font-weight:600}
.side{display:flex;flex-direction:column;gap:12px}
.kv{display:grid;grid-template-columns:1fr auto;gap:3px 10px}.kv span:nth-child(odd){color:var(--mut)}
.kv span:nth-child(even){text-align:right;font-variant-numeric:tabular-nums;font-weight:600}
.num{display:grid;grid-template-columns:1fr 92px;gap:6px;align-items:center;margin:5px 0}
.num input{width:100%;padding:5px 6px;border:1px solid var(--line);border-radius:6px;background:var(--bg);text-align:right}
.num input.dirty{border-color:var(--peak)}.hint{font-size:12px;color:var(--mut);margin-top:6px}
input[type=range]{width:100%}
details.log{margin:0 16px 16px}details.log summary{cursor:pointer;color:var(--mut);font-size:12px;padding:4px 0}
#log{height:150px;overflow:auto;font:11px/1.35 ui-monospace,Menlo,Consolas,monospace;background:var(--card);
border:1px solid var(--line);border-radius:8px;padding:6px 8px;white-space:pre-wrap}
#log .E{color:var(--thr)}#log .W{color:var(--peak)}#log .I{color:var(--duty)}
`;

const HTML = `
<header><span id=dot></span><h1>Curtain Drive</h1><span id=hdr>connecting…</span></header>
<main>
 <section class=charts>
  <div class=card>
   <div class=bar><span class=t>Motor current</span>
    <span id=win></span><button id=pause>Pause</button><button id=clr>Clear</button></div>
   <div class=legend><span><i style="background:var(--cur)"></i>current</span>
    <span><i style="background:var(--thr)"></i>stall threshold</span>
    <span><i style="background:var(--peak)"></i>stop / peak</span><span id=hover></span></div>
   <canvas id=c_cur></canvas>
  </div>
  <div class=card>
   <div class=bar><span class=t>Duty &amp; position</span></div>
   <div class=legend><span><i style="background:var(--duty)"></i>motor duty %</span>
    <span><i style="background:var(--pos)"></i>position %</span></div>
   <canvas id=c_duty></canvas>
  </div>
 </section>
 <aside class=side>
  <div class=card><h2>Curtain</h2>
   <div class=big><button data-cv=open>Open</button><button data-cv=stop>Stop</button><button data-cv=close>Close</button></div>
   <div class=bar style="margin-top:6px"><button data-mark="Mark fully closed">It is fully closed</button><button data-mark="Mark fully open">It is fully open</button></div>
   <div class=hint>Position <b id=posv>–</b></div>
   <input type=range id=pos min=0 max=100 step=1>
  </div>
  <div class=card><h2>Live</h2><div class=kv id=kv></div></div>
  <div class=card><h2>Tuning</h2><div id=tune></div>
   <div class=hint>Enter or leave a field to apply. Values are kept across restarts.</div></div>
  <div class=card><h2>Actions</h2>
   <div class=bar><button id=teach>Teach travel</button><button data-btn="Calibrate travel">Calibrate travel</button>
   <button data-btn="Restart">Restart</button></div>
   <div class=hint>Teach travel: with the curtain closed, press once to open, press again when it is fully open.</div></div>
 </aside>
</main>
<details class=log><summary>Device log</summary><div id=log></div></details>`;

document.head.insertAdjacentHTML("beforeend",
  `<meta name=viewport content="width=device-width,initial-scale=1"><title>Curtain Drive</title><style>${CSS}</style>`);
document.body.innerHTML = HTML;
const $ = (s) => document.querySelector(s);

// ---------------- state ----------------
const S = {};                        // latest event per entity id
const cur = [], duty = [], pos = []; // [t_ms, value]
const marks = [];                    // {t, v, txt}
const KEEP = 20 * 60e3;
let t0 = Date.now(), connectedAt = 0, paused = false, pausedAt = 0, win = 60e3, hoverX = null;

const LIVE = [
  ["sensor/Motor current", "Current"], ["sensor/Peak current (last run)", "Peak (last run)"],
  ["sensor/Current at last stall stop", "At last stall stop"], ["sensor/Motor duty", "Duty"],
  ["text_sensor/Last stop reason", "Last stop"], ["number/Travel time", "Travel time (s)"],
  ["sensor/Supply voltage", "Supply (check R2)"],
];
$("#kv").innerHTML = LIVE.map(([id, l]) => `<span>${l}</span><span data-kv="${id}">–</span>`).join("");

for (const [ms, l] of [[20e3, "20 s"], [60e3, "1 min"], [300e3, "5 min"], [900e3, "15 min"]]) {
  const b = document.createElement("button");
  b.textContent = l; b.onclick = () => { win = ms; wins(); draw(); };
  b.dataset.w = ms; $("#win").appendChild(b);
}
const wins = () => document.querySelectorAll("#win button").forEach(b => b.classList.toggle("on", +b.dataset.w === win));
wins();

function push(arr, v) {
  const t = Date.now(); arr.push([t, v]);
  while (arr.length && arr[0][0] < t - KEEP) arr.shift();
}

// ---------------- events ----------------
function onState(d) {
  const prev = S[d.id]; S[d.id] = d;
  const live = Date.now() - connectedAt > 2000;   // skip the burst of states sent on connect
  switch (d.id) {
    case "sensor/Motor current": push(cur, d.value); break;
    case "sensor/Motor duty": push(duty, d.value); break;
    case "cover/Curtain":
      push(pos, d.position * 100);
      if (document.activeElement !== $("#pos")) $("#pos").value = Math.round(d.position * 100);
      $("#posv").textContent = `${Math.round(d.position * 100)} % · ${d.current_operation.toLowerCase()}`;
      break;
    case "sensor/Current at last stall stop":
      if (live && prev) marks.push({ t: Date.now(), v: d.value, txt: `stall ${d.value.toFixed(2)} A` });
      break;
    case "sensor/Peak current (last run)":
      if (live && prev) marks.push({ t: Date.now(), v: d.value, txt: `peak ${d.value.toFixed(2)} A`, peak: 1 });
      break;
  }
  if (d.domain === "number") tuneRow(d);
  if (d.domain === "switch") switchRow(d);
  const kv = document.querySelector(`[data-kv="${CSS_esc(d.id)}"]`);
  if (kv) kv.textContent = d.state === "NA" ? "–" : (d.state ?? d.value);
}
const CSS_esc = (s) => s.replace(/"/g, '\\"');

function tuneRow(d) {
  let row = document.querySelector(`[data-num="${CSS_esc(d.id)}"]`);
  if (!row) {
    row = document.createElement("div"); row.className = "num"; row.dataset.num = d.id;
    row.dataset.w = d.sorting_weight ?? 50;
    row.innerHTML = `<label>${d.name}${d.uom ? ` <small>(${d.uom})</small>` : ""}</label>
      <input type=number min="${d.min_value}" max="${d.max_value}" step="${d.step}">`;
    const inp = row.querySelector("input");
    const send = () => {
      if (!inp.classList.contains("dirty")) return;
      post(`/number/${encodeURIComponent(d.name)}/set?value=${encodeURIComponent(inp.value)}`);
      inp.classList.remove("dirty");
    };
    inp.oninput = () => inp.classList.add("dirty");
    inp.onkeydown = (e) => { if (e.key === "Enter") { send(); inp.blur(); } };
    inp.onblur = send;
    const box = $("#tune");
    const after = [...box.children].find(c => +c.dataset.w > +row.dataset.w);
    box.insertBefore(row, after || null);
  }
  const inp = row.querySelector("input");
  if (document.activeElement !== inp && !inp.classList.contains("dirty")) inp.value = d.value;
}

function switchRow(d) {
  let row = document.querySelector(`[data-num="${CSS_esc(d.id)}"]`);
  if (!row) {
    row = document.createElement("div"); row.className = "num"; row.dataset.num = d.id;
    row.dataset.w = d.sorting_weight ?? 50;
    row.innerHTML = `<label for="sw_${d.id}">${d.name}</label><input type=checkbox id="sw_${d.id}" style="justify-self:end;width:auto">`;
    const inp = row.querySelector("input");
    inp.onchange = () => post(`/switch/${encodeURIComponent(d.name)}/${inp.checked ? "turn_on" : "turn_off"}`);
    const box = $("#tune");
    const after = [...box.children].find(c => +c.dataset.w > +row.dataset.w);
    box.insertBefore(row, after || null);
  }
  row.querySelector("input").checked = d.value === true || d.state === "ON";
}

function post(url) {
  return fetch(url, { method: "POST" }).catch(e => logLine(`E request failed: ${url} ${e}`));
}
document.querySelectorAll("[data-cv]").forEach(b => b.onclick = () => post(`/cover/Curtain/${b.dataset.cv}`));
document.querySelectorAll("[data-btn]").forEach(b => b.onclick = () => {
  if (confirm(`${b.dataset.btn}?`)) post(`/button/${encodeURIComponent(b.dataset.btn)}/press`);
});
document.querySelectorAll("[data-mark]").forEach(b => b.onclick = () => post(`/button/${encodeURIComponent(b.dataset.mark)}/press`));
$("#teach").onclick = () => post(`/button/${encodeURIComponent("Teach travel")}/press`);
$("#pos").onchange = (e) => post(`/cover/Curtain/set?position=${e.target.value / 100}`);
$("#pause").onclick = () => { paused = !paused; pausedAt = Date.now(); $("#pause").classList.toggle("on", paused);
  $("#pause").textContent = paused ? "Resume" : "Pause"; draw(); };
$("#clr").onclick = () => { cur.length = duty.length = pos.length = marks.length = 0; draw(); };

// ---------------- log ----------------
const ANSI = /\x1b\[[0-9;]*m/g;
function logLine(s) {
  const el = $("#log"), atEnd = el.scrollTop + el.clientHeight >= el.scrollHeight - 4;
  const line = s.replace(ANSI, ""), m = line.match(/\[([EWIDCVS])\]/);
  if (m && (m[1] === "S" || m[1] === "V")) return;          // per-sample state lines: that's what the graphs are for
  const div = document.createElement("div"); div.textContent = line; if (m) div.className = m[1];
  el.appendChild(div); while (el.childElementCount > 300) el.firstChild.remove();
  if (atEnd) el.scrollTop = el.scrollHeight;
}

function connect() {
  const es = new EventSource("/events");
  es.onopen = () => { connectedAt = Date.now(); $("#dot").classList.add("on"); };
  es.onerror = () => { $("#dot").classList.remove("on"); $("#hdr").textContent = "disconnected – retrying…"; };
  es.addEventListener("state", (e) => onState(JSON.parse(e.data)));
  es.addEventListener("log", (e) => logLine(e.data));
  es.addEventListener("ping", (e) => {
    const d = JSON.parse(e.data || "{}");
    if (d.uptime !== undefined) $("#hdr").textContent = `up ${fmtUp(d.uptime)} · ${location.host}`;
  });
}
const fmtUp = (s) => s < 3600 ? `${Math.floor(s / 60)} min` : `${(s / 3600).toFixed(1)} h`;
connect();

// ---------------- charts ----------------
const cvCur = $("#c_cur"), cvDuty = $("#c_duty");
function css(v) { return getComputedStyle(document.documentElement).getPropertyValue(v).trim(); }

function chart(cv, series, o) {
  const dpr = window.devicePixelRatio || 1, W = cv.clientWidth, H = cv.clientHeight;
  if (cv.width !== W * dpr || cv.height !== H * dpr) { cv.width = W * dpr; cv.height = H * dpr; }
  const g = cv.getContext("2d"); g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, W, H);
  const L = 46, R = 10, T = 8, B = 22, pw = W - L - R, ph = H - T - B;
  const tEnd = paused ? pausedAt : Date.now(), tStart = tEnd - win;
  const X = (t) => L + (t - tStart) / win * pw, Y = (v) => T + ph - (v - o.ymin) / (o.ymax - o.ymin) * ph;
  g.font = "11px system-ui,sans-serif"; g.lineWidth = 1;
  // grid + y labels
  const step = niceStep((o.ymax - o.ymin) / 6);
  g.strokeStyle = css("--grid"); g.fillStyle = css("--mut"); g.textAlign = "right"; g.textBaseline = "middle";
  for (let v = Math.ceil(o.ymin / step) * step; v <= o.ymax + 1e-9; v += step) {
    g.beginPath(); g.moveTo(L, Y(v) + .5); g.lineTo(W - R, Y(v) + .5); g.stroke();
    g.fillText(fmt(v, step) + (o.unit || ""), L - 5, Y(v));
  }
  // x labels: seconds before now
  g.textAlign = "center"; g.textBaseline = "top";
  const xs = niceStep(win / 1000 / 6);
  for (let s = 0; s <= win / 1000; s += xs) g.fillText(s === 0 ? (paused ? "paused" : "now") : `-${s}s`, X(tEnd - s * 1000), T + ph + 5);
  // horizontal reference lines
  for (const h of o.hlines || []) {
    g.strokeStyle = h.color; g.setLineDash([6, 4]); g.lineWidth = 1.5;
    g.beginPath(); g.moveTo(L, Y(h.v)); g.lineTo(W - R, Y(h.v)); g.stroke(); g.setLineDash([]);
    g.fillStyle = h.color; g.textAlign = "left"; g.textBaseline = "bottom"; g.fillText(h.label, L + 4, Y(h.v) - 2);
  }
  // series
  g.save(); g.beginPath(); g.rect(L, T, pw, ph); g.clip();
  for (const s of series) {
    // Sensors with a delta filter only report changes, so draw steps and hold the
    // last value up to "now".
    g.strokeStyle = s.color; g.lineWidth = s.w || 1.8; g.beginPath();
    let prevY = null;
    for (let i = 0; i < s.data.length; i++) {
      const [t, v] = s.data[i];
      if (t > tEnd) break;
      if (t < tStart && i + 1 < s.data.length && s.data[i + 1][0] < tStart) continue;
      const x = X(Math.max(t, tStart)), y = Y(Math.min(Math.max(v, o.ymin), o.ymax));
      if (prevY === null) g.moveTo(x, y);
      else { if (s.step) g.lineTo(x, prevY); g.lineTo(x, y); }
      prevY = y;
    }
    if (prevY !== null) g.lineTo(X(tEnd), prevY);
    g.stroke();
  }
  // markers
  for (const m of o.marks || []) {
    if (m.t < tStart) continue;
    const x = X(m.t), y = Y(Math.min(m.v, o.ymax));
    g.fillStyle = css("--peak"); g.beginPath(); g.arc(x, y, m.peak ? 3.5 : 5, 0, 7); g.fill();
    g.textAlign = "right"; g.textBaseline = "bottom"; g.fillText(m.txt, x - 6, y - 4);
  }
  g.restore();
  // hover readout
  if (hoverX !== null && hoverX > L && hoverX < W - R) {
    const t = tStart + (hoverX - L) / pw * win;
    g.strokeStyle = css("--mut"); g.beginPath(); g.moveTo(hoverX + .5, T); g.lineTo(hoverX + .5, T + ph); g.stroke();
    return { t, vals: series.map(s => nearest(s.data, t)) };
  }
}
function nearest(a, t) {
  let lo = 0, hi = a.length - 1; if (hi < 0) return null;
  while (hi - lo > 1) { const m = (lo + hi) >> 1; a[m][0] < t ? lo = m : hi = m; }
  const p = Math.abs(a[lo][0] - t) < Math.abs(a[hi][0] - t) ? a[lo] : a[hi];
  return Math.abs(p[0] - t) < 2000 ? p[1] : null;
}
function niceStep(r) { const p = 10 ** Math.floor(Math.log10(r)), n = r / p; return (n < 1.5 ? 1 : n < 3.5 ? 2 : n < 7.5 ? 5 : 10) * p; }
const fmt = (v, st) => v.toFixed(st < 0.1 ? 2 : st < 1 ? 1 : 0);

function draw() {
  const thr = S["number/Stall threshold"]?.value;
  const tEnd = paused ? pausedAt : Date.now();
  let vmax = 0; for (const [t, v] of cur) if (t > tEnd - win && v > vmax) vmax = v;
  const ymax = Math.max(1.2, (thr ?? 0) * 1.25, vmax * 1.1);
  const h1 = chart(cvCur, [{ data: cur, color: css("--cur"), w: 2 }],
    { ymin: 0, ymax, unit: " A", hlines: thr !== undefined ? [{ v: thr, color: css("--thr"), label: `stall threshold ${(+thr).toFixed(2)} A` }] : [], marks });
  const h2 = chart(cvDuty, [{ data: duty, color: css("--duty"), step: 1 }, { data: pos, color: css("--pos") }], { ymin: 0, ymax: 100, unit: "%" });
  const h = h1 || h2;
  $("#hover").textContent = h ? `at −${((tEnd - h.t) / 1000).toFixed(1)} s: ` +
    [h1 && h1.vals[0] != null ? `${h1.vals[0].toFixed(2)} A` : "", h2 && h2.vals[0] != null ? `duty ${h2.vals[0].toFixed(0)} %` : "",
     h2 && h2.vals[1] != null ? `pos ${h2.vals[1].toFixed(0)} %` : ""].filter(Boolean).join(" · ") : "";
}
for (const cv of [cvCur, cvDuty]) {
  cv.onpointermove = (e) => { hoverX = e.offsetX; if (paused) draw(); };
  cv.onpointerleave = () => { hoverX = null; if (paused) draw(); };
}
setInterval(() => { if (!paused) draw(); }, 100);
window.onresize = draw;
