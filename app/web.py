"""Dependency-free HTML UI and monitoring dashboard renderers."""

from __future__ import annotations

import html


def render_ui() -> str:
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Civic Incident Coordinator</title>
<style>
:root{color-scheme:dark;--bg:#07111f;--card:#102238;--line:#25405d;--text:#e6edf5;--muted:#93a7bd;--accent:#21c7a8;--danger:#ff6b6b}*{box-sizing:border-box}
body{margin:0;background:linear-gradient(135deg,#07111f,#0c2137);color:var(--text);font:15px system-ui,sans-serif}.shell{max-width:900px;margin:auto;padding:40px 22px}h1{margin:0;font-size:clamp(26px,5vw,42px)}.lead{color:var(--muted);max-width:720px;line-height:1.6}.panel{background:rgba(16,34,56,.96);border:1px solid var(--line);border-radius:16px;padding:22px;margin-top:24px;box-shadow:0 18px 50px #0005}textarea{width:100%;min-height:145px;background:#091827;color:var(--text);border:1px solid var(--line);border-radius:10px;padding:14px;font:inherit;resize:vertical}button{border:0;border-radius:9px;background:var(--accent);color:#03251e;font-weight:750;padding:11px 18px;margin-top:12px;cursor:pointer}button.secondary{background:#ffb454;color:#2a1700;margin-left:8px}button.danger{background:var(--danger);color:#310606;margin-left:8px}button:disabled{opacity:.45;cursor:wait}.hidden{display:none}.status{color:var(--muted);min-height:22px;margin-top:12px}.order{white-space:pre-wrap;line-height:1.6;background:#091827;border-radius:10px;padding:16px}.badge{display:inline-block;padding:6px 10px;border-radius:99px;font-weight:800}.emergency{background:#551d25;color:#ff9ca5}.standard{background:#153f36;color:#66e6c8}.meta{font:12px ui-monospace,monospace;color:var(--muted);word-break:break-all}.links a{color:#67dbca;margin-right:18px;text-decoration:none}
</style></head><body><main class="shell">
<p class="meta">MULTI-AGENT OPERATIONS DESK</p><h1>Civic Incident Coordinator</h1>
<p class="lead">Turn a resident infrastructure report into an operator-reviewed work order. The supervisor coordinates classification, impact, and dispatch agents before an audited priority route.</p>
<section class="panel"><label for="report"><strong>Resident report</strong></label>
<textarea id="report" placeholder="Example: A large water leak is flooding the crossing beside North Primary School. Traffic is swerving into the opposite lane."></textarea>
<button id="submit" onclick="submitIncident()">Analyze incident</button><div class="status" id="status"></div></section>
<section class="panel hidden" id="review"><h2>Operator review</h2><p class="lead" id="reason"></p><div class="order" id="order"></div>
<button onclick="reviewIncident(true)">Approve work order</button><button class="danger" onclick="reviewIncident(false)">Reject</button></section>
<section class="panel hidden" id="result"><h2>Routing result</h2><div id="badge" class="badge"></div><p id="decision"></p><p id="monitoring" class="lead"></p><div id="correlation" class="meta"></div></section>
<p class="links"><a href="/dashboard">Monitoring dashboard</a><a href="/docs">Docs</a><a href="/health">Health</a></p>
</main><script>
let threadId=null;
const el=id=>document.getElementById(id);
function busy(value,message){el('submit').disabled=value;el('status').textContent=message}
async function submitIncident(){const report=el('report').value.trim();if(!report){busy(false,'Please enter an incident report.');return}threadId='web-'+Date.now();busy(true,'Supervisor and specialist agents are working…');el('review').classList.add('hidden');el('result').classList.add('hidden');try{const response=await fetch('/incidents',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({report,thread_id:threadId})});const data=await response.json();if(!response.ok)throw new Error(data.detail||'Request failed');el('order').textContent=data.work_order;el('reason').textContent='Supervisor: '+data.supervisor_reason;el('review').classList.remove('hidden');busy(false,'Awaiting operator decision.')}catch(error){busy(false,'Error: '+error.message)}}
async function reviewIncident(approved){busy(true,approved?'Auditing and routing…':'Rejecting…');try{const response=await fetch('/incidents/'+threadId+'/review',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({approved,comment:approved?'Approved in web UI':'Rejected in web UI'})});const data=await response.json();if(!response.ok)throw new Error(data.detail||'Request failed');el('review').classList.add('hidden');const priority=data.priority||'REJECTED';el('badge').textContent=priority;el('badge').className='badge '+(priority==='EMERGENCY'?'emergency':'standard');el('decision').textContent=data.routing_decision||'The proposed work order was rejected.';el('monitoring').textContent=data.monitoring_report||'';el('correlation').textContent='Correlation ID: '+data.correlation_id;el('result').classList.remove('hidden');busy(false,'Complete.')}catch(error){busy(false,'Error: '+error.message)}}
</script></body></html>"""


def render_dashboard(metrics: dict, runs: list[dict]) -> str:
    statuses = metrics["status_counts"]
    tokens = metrics["total_tokens"]
    node_rows = "".join(
        "<tr>"
        f"<td>{html.escape(node)}</td><td>{stats['calls']}</td>"
        f"<td>{stats['errors']}</td><td>{stats['duration_ms_avg']}</td>"
        f"<td>{stats['input_tokens']} / {stats['output_tokens']} / {stats['total_tokens']}</td>"
        "</tr>"
        for node, stats in sorted(metrics["per_node"].items())
    )
    run_rows = "".join(
        "<tr>"
        f"<td><a href='/runs/{html.escape(run['correlation_id'])}'>{html.escape(run['correlation_id'])}</a></td>"
        f"<td>{html.escape(run['status'])}</td><td>{html.escape(run['started_at'])}</td>"
        f"<td>{run['event_count']}</td></tr>"
        for run in runs
    )
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="refresh" content="15">
<title>Incident Monitoring</title><style>
body{{background:#07111f;color:#e6edf5;font:14px system-ui,sans-serif;margin:0;padding:28px}}a{{color:#58d8c0}}.cards{{display:flex;gap:12px;flex-wrap:wrap}}.card,table{{background:#102238;border:1px solid #25405d;border-radius:12px}}.card{{padding:14px 18px;min-width:140px}}.value{{font-size:26px;font-weight:800}}.label{{color:#93a7bd;font-size:11px;text-transform:uppercase}}table{{width:100%;border-collapse:collapse;overflow:hidden;margin:12px 0 28px}}th,td{{padding:10px;text-align:left;border-bottom:1px solid #25405d}}th{{color:#93a7bd;font-size:11px;text-transform:uppercase}}h2{{margin-top:28px;font-size:17px}}.muted{{color:#93a7bd}}
</style></head><body><p><a href="/ui">← Incident desk</a></p><h1>Monitoring Agent Dashboard</h1>
<p class="muted">Refreshes every 15 seconds. Every node event carries the same run correlation ID.</p>
<div class="cards"><div class="card"><div class="label">Runs</div><div class="value">{metrics["run_count"]}</div></div>
<div class="card"><div class="label">Completed</div><div class="value">{statuses.get("completed", 0)}</div></div>
<div class="card"><div class="label">Failed</div><div class="value">{statuses.get("failed", 0)}</div></div>
<div class="card"><div class="label">Running</div><div class="value">{statuses.get("running", 0)}</div></div>
<div class="card"><div class="label">Total tokens</div><div class="value">{tokens["total_tokens"]}</div></div></div>
<h2>Node performance</h2><table><tr><th>Node</th><th>Calls</th><th>Errors</th><th>Average ms</th><th>Tokens in / out / total</th></tr>{node_rows or '<tr><td colspan="5">No events recorded.</td></tr>'}</table>
<h2>Recent traces</h2><table><tr><th>Correlation ID</th><th>Status</th><th>Started</th><th>Events</th></tr>{run_rows or '<tr><td colspan="4">No runs recorded.</td></tr>'}</table>
</body></html>"""
