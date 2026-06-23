"""Cl3 enrichment web app.

A small, password-gated UI: paste a list of names, run the existing
agent_enrich LinkedIn lookup + Claude verification, and view results.
Also keeps Render's web service alive (binds $PORT, /healthz health check).
"""

import os
import secrets
import threading
import time
import uuid
from hmac import compare_digest

from flask import (
    Flask,
    Response,
    jsonify,
    redirect,
    render_template_string,
    request,
    session,
)

import web_enrich

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY") or secrets.token_hex(32)

APP_PASSWORD = os.getenv("APP_PASSWORD", "")
SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
MAX_NAMES = int(os.getenv("MAX_NAMES", "25"))

JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()
JOB_TTL = 3600  # seconds to keep finished jobs in memory


def _authed() -> bool:
    return bool(session.get("authed"))


def _prune_jobs() -> None:
    now = time.time()
    with JOBS_LOCK:
        stale = [j for j, d in JOBS.items() if now - d["created"] > JOB_TTL]
        for j in stale:
            JOBS.pop(j, None)


def _start_job(rows: list[dict]) -> str:
    job_id = uuid.uuid4().hex
    with JOBS_LOCK:
        JOBS[job_id] = {
            "status": "running",
            "total": len(rows),
            "done": 0,
            "results": None,
            "error": None,
            "created": time.time(),
        }

    def on_progress(done: int) -> None:
        with JOBS_LOCK:
            if job_id in JOBS:
                JOBS[job_id]["done"] = done

    def run() -> None:
        try:
            results = web_enrich.run_enrichment_sync(rows, on_progress)
            with JOBS_LOCK:
                JOBS[job_id]["results"] = results
                JOBS[job_id]["status"] = "done"
        except Exception as exc:  # surface any unexpected failure to the UI
            with JOBS_LOCK:
                JOBS[job_id]["status"] = "error"
                JOBS[job_id]["error"] = str(exc)

    threading.Thread(target=run, daemon=True).start()
    return job_id


@app.get("/healthz")
def healthz() -> Response:
    return Response("ok", mimetype="text/plain")


@app.get("/")
def index() -> str:
    if not APP_PASSWORD:
        return render_template_string(PAGE, view="unconfigured", max_names=MAX_NAMES)
    if not _authed():
        return render_template_string(PAGE, view="login", max_names=MAX_NAMES)
    return render_template_string(PAGE, view="app", max_names=MAX_NAMES)


@app.post("/login")
def login():
    if not APP_PASSWORD:
        return redirect("/")
    supplied = request.form.get("password", "")
    if compare_digest(supplied, APP_PASSWORD):
        session["authed"] = True
        return redirect("/")
    return render_template_string(
        PAGE, view="login", max_names=MAX_NAMES, error="Incorrect password."
    )


@app.get("/logout")
def logout():
    session.clear()
    return redirect("/")


@app.post("/enrich")
def enrich():
    if not APP_PASSWORD or not _authed():
        return jsonify({"error": "Not authorized."}), 401
    if not SERPAPI_KEY or not ANTHROPIC_API_KEY:
        return jsonify(
            {"error": "Server missing SERPAPI_KEY and/or ANTHROPIC_API_KEY."}
        ), 400

    text = request.form.get("names", "") or (request.json or {}).get("names", "")
    rows = web_enrich.parse_lines(text)
    if not rows:
        return jsonify({"error": "No valid names provided."}), 400
    if len(rows) > MAX_NAMES:
        return jsonify(
            {"error": f"Too many names ({len(rows)}). Max is {MAX_NAMES} per run."}
        ), 400

    _prune_jobs()
    job_id = _start_job(rows)
    return jsonify({"job_id": job_id, "total": len(rows)})


@app.get("/status/<job_id>")
def status(job_id: str):
    if not APP_PASSWORD or not _authed():
        return jsonify({"error": "Not authorized."}), 401
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return jsonify({"error": "Unknown job."}), 404
        return jsonify(
            {
                "status": job["status"],
                "total": job["total"],
                "done": job["done"],
                "results": job["results"],
                "error": job["error"],
            }
        )


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Cl3 — Prospect Enrichment</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body { margin: 0; font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
         background: #0d1117; color: #e6edf3; }
  .wrap { max-width: 920px; margin: 0 auto; padding: 32px 20px 80px; }
  h1 { font-size: 22px; margin: 0 0 4px; }
  .sub { color: #8b949e; font-size: 14px; margin: 0 0 24px; }
  .card { background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 20px; }
  label { display: block; font-size: 13px; color: #8b949e; margin-bottom: 8px; }
  textarea, input[type=password] {
    width: 100%; background: #0d1117; color: #e6edf3; border: 1px solid #30363d;
    border-radius: 8px; padding: 12px; font-size: 14px; font-family: ui-monospace, SFMono-Regular, monospace; }
  textarea { min-height: 180px; resize: vertical; }
  button { margin-top: 14px; background: #238636; color: #fff; border: 0; border-radius: 8px;
           padding: 11px 18px; font-size: 14px; font-weight: 600; cursor: pointer; }
  button:disabled { opacity: .55; cursor: default; }
  .hint { color: #6e7681; font-size: 12px; margin-top: 8px; }
  .bar { height: 8px; background: #21262d; border-radius: 6px; overflow: hidden; margin: 18px 0 6px; }
  .bar > div { height: 100%; width: 0; background: #2f81f7; transition: width .3s; }
  table { width: 100%; border-collapse: collapse; margin-top: 18px; font-size: 13px; }
  th, td { text-align: left; padding: 9px 10px; border-bottom: 1px solid #21262d; vertical-align: top; }
  th { color: #8b949e; font-weight: 600; }
  a { color: #58a6ff; }
  .pill { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 12px; font-weight: 600; }
  .hi { background: #14301c; color: #3fb950; }
  .mid { background: #3a2e12; color: #d29922; }
  .lo { background: #3a1518; color: #f85149; }
  .err { color: #f85149; font-size: 13px; margin-top: 10px; }
  .topbar { display:flex; justify-content:space-between; align-items:center; }
  .logout { color:#8b949e; font-size:13px; text-decoration:none; }
  .warn { background:#3a2e12; border:1px solid #d29922; color:#e3b341; padding:14px; border-radius:8px; font-size:13px; }
  code { background:#0d1117; border:1px solid #30363d; border-radius:5px; padding:1px 5px; }
</style>
</head>
<body>
<div class="wrap">
  <div class="topbar">
    <h1>Prospect Enrichment</h1>
    {% if view == 'app' %}<a class="logout" href="/logout">Log out</a>{% endif %}
  </div>
  <p class="sub">Paste names → find each person's LinkedIn profile with a confidence score.</p>

  {% if view == 'unconfigured' %}
    <div class="card">
      <div class="warn">
        This app is not configured. Set the <code>APP_PASSWORD</code> environment variable
        in Render (plus <code>SERPAPI_KEY</code> and <code>ANTHROPIC_API_KEY</code>), then redeploy.
      </div>
    </div>

  {% elif view == 'login' %}
    <div class="card">
      <form method="post" action="/login">
        <label for="password">Password</label>
        <input type="password" id="password" name="password" autofocus required>
        {% if error %}<div class="err">{{ error }}</div>{% endif %}
        <button type="submit">Enter</button>
      </form>
    </div>

  {% else %}
    <div class="card">
      <label for="names">Names — one per line. Optional: <code>Name, Company, City, State</code></label>
      <textarea id="names" placeholder="Jane Smith&#10;John Doe, Acme Capital, Miami, FL"></textarea>
      <div class="hint">Up to {{ max_names }} names per run.</div>
      <button id="run">Enrich</button>
      <div id="err" class="err"></div>
      <div id="progress" style="display:none">
        <div class="bar"><div id="fill"></div></div>
        <div class="hint" id="ptext"></div>
      </div>
      <div id="out"></div>
    </div>
  {% endif %}
</div>

<script>
const btn = document.getElementById('run');
if (btn) {
  const namesEl = document.getElementById('names');
  const errEl = document.getElementById('err');
  const prog = document.getElementById('progress');
  const fill = document.getElementById('fill');
  const ptext = document.getElementById('ptext');
  const out = document.getElementById('out');

  function pill(score) {
    const cls = score >= 90 ? 'hi' : (score >= 50 ? 'mid' : 'lo');
    return '<span class="pill ' + cls + '">' + score + '</span>';
  }

  function render(results) {
    if (!results || !results.length) { out.innerHTML = ''; return; }
    let html = '<table><thead><tr><th>Name</th><th>Confidence</th><th>LinkedIn</th><th>Notes</th></tr></thead><tbody>';
    for (const r of results) {
      const link = r.linkedin_url
        ? '<a href="' + encodeURI(r.linkedin_url) + '" target="_blank" rel="noopener">profile</a>'
        : '<span class="hint">none</span>';
      const td = document.createElement('td');
      td.textContent = r.justification || '';
      const nameTd = document.createElement('span'); nameTd.textContent = r.name || r.input || '';
      html += '<tr><td>' + nameTd.outerHTML + '</td><td>' + pill(r.confidence_score || 0)
            + '</td><td>' + link + '</td><td>' + td.innerHTML + '</td></tr>';
    }
    html += '</tbody></table>';
    out.innerHTML = html;
  }

  async function poll(jobId) {
    const res = await fetch('/status/' + jobId);
    const data = await res.json();
    if (data.error) { errEl.textContent = data.error; reset(); return; }
    const pct = data.total ? Math.round(100 * data.done / data.total) : 0;
    fill.style.width = pct + '%';
    ptext.textContent = data.done + ' / ' + data.total + ' processed';
    if (data.status === 'running') { setTimeout(() => poll(jobId), 1500); return; }
    if (data.status === 'error') { errEl.textContent = data.error || 'Job failed.'; reset(); return; }
    render(data.results);
    reset();
  }

  function reset() { btn.disabled = false; btn.textContent = 'Enrich'; }

  btn.addEventListener('click', async () => {
    errEl.textContent = ''; out.innerHTML = '';
    const names = namesEl.value.trim();
    if (!names) { errEl.textContent = 'Enter at least one name.'; return; }
    btn.disabled = true; btn.textContent = 'Working…';
    prog.style.display = 'block'; fill.style.width = '0%'; ptext.textContent = 'Starting…';
    try {
      const res = await fetch('/enrich', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ names })
      });
      const data = await res.json();
      if (data.error) { errEl.textContent = data.error; reset(); return; }
      poll(data.job_id);
    } catch (e) { errEl.textContent = 'Request failed: ' + e; reset(); }
  });
}
</script>
</body>
</html>"""


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    print(f"Cl3 enrichment app listening on 0.0.0.0:{port}", flush=True)
    app.run(host="0.0.0.0", port=port, threaded=True)
