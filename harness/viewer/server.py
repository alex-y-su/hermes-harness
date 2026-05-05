from __future__ import annotations

import argparse
import html
import json
import os
import secrets
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from harness import db
from harness.factory import factory_path
from harness.viewer import auth
from harness.viewer.data import assignment_detail, dashboard, graph, hub_config, team_detail


APP_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Hermes Hub Viewer</title>
  <style>
    :root { color-scheme: dark; --bg:#101214; --panel:#181c20; --line:#2b3238; --text:#edf1f5; --muted:#9aa6b2; --accent:#67d4b4; --warn:#ffbf69; --bad:#ff7b7b; }
    * { box-sizing: border-box; }
    body { margin: 0; font: 14px/1.45 Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: var(--bg); color: var(--text); }
    a { color: inherit; text-decoration: none; }
    .shell { display: grid; grid-template-columns: 280px 1fr; min-height: 100vh; }
    aside { border-right: 1px solid var(--line); background: #12161a; padding: 18px; position: sticky; top: 0; height: 100vh; overflow: auto; }
    main { padding: 24px; overflow: auto; }
    h1, h2, h3 { margin: 0; font-weight: 650; letter-spacing: 0; }
    h1 { font-size: 24px; }
    h2 { font-size: 18px; margin: 22px 0 10px; }
    h3 { font-size: 14px; color: var(--muted); margin: 14px 0 8px; text-transform: uppercase; }
    .brand { display: flex; align-items: center; justify-content: space-between; margin-bottom: 18px; }
    .nav { display: grid; gap: 6px; }
    .nav a, button, input { border: 1px solid var(--line); background: var(--panel); color: var(--text); border-radius: 6px; }
    .nav a { padding: 9px 10px; }
    .nav a.active { border-color: var(--accent); color: var(--accent); }
    input { width: 100%; padding: 9px 10px; margin: 10px 0; }
    .grid { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); }
    .card { border: 1px solid var(--line); background: var(--panel); border-radius: 8px; padding: 14px; min-width: 0; }
    .metric { font-size: 28px; font-weight: 700; }
    .muted { color: var(--muted); }
    .pill { display: inline-flex; align-items: center; gap: 6px; min-height: 24px; padding: 2px 8px; border: 1px solid var(--line); border-radius: 999px; color: var(--muted); font-size: 12px; }
    .state-failed, .state-error { color: var(--bad); }
    .state-working, .state-dispatched, .state-queued, .state-spawned, .state-retrying { color: var(--accent); }
    .state-input-required, .state-auth-required, .state-open, .state-supplied, .state-resuming { color: var(--warn); }
    .state-stale { color: var(--bad); }
    table { width: 100%; border-collapse: collapse; border: 1px solid var(--line); background: var(--panel); border-radius: 8px; overflow: hidden; }
    th, td { border-bottom: 1px solid var(--line); padding: 9px 10px; text-align: left; vertical-align: top; }
    th { color: var(--muted); font-weight: 600; }
    tr:last-child td { border-bottom: 0; }
    pre { white-space: pre-wrap; word-break: break-word; border: 1px solid var(--line); background: #0d1013; padding: 14px; border-radius: 8px; max-height: 520px; overflow: auto; }
    .split { display: grid; grid-template-columns: minmax(0, 1fr) 360px; gap: 16px; align-items: start; }
    svg { width: 100%; min-height: 560px; border: 1px solid var(--line); background: var(--panel); border-radius: 8px; }
    .node-label { font-size: 13px; font-weight: 650; fill: var(--text); pointer-events: none; }
    .node-meta { font-size: 11px; fill: var(--muted); pointer-events: none; }
    .edge { stroke: #47525d; stroke-width: 1.4; fill: none; }
    .org-card { stroke: var(--line); stroke-width: 1.2; rx: 8; }
    .org-root { fill: #1f3c36; stroke: #67d4b4; }
    .org-team { fill: #17243a; stroke: #8ab4ff; }
    .org-assignment { fill: #251d34; stroke: #c9a7ff; }
    .section-head { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; margin: 22px 0 10px; }
    .section-head h2 { margin: 0; }
    .dashboard-graph svg { min-height: 420px; }
    .tabs { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; border-bottom: 1px solid var(--line); margin: 14px 0 18px; }
    .tabs a { display: inline-flex; align-items: center; min-height: 34px; padding: 7px 10px; color: var(--muted); border: 1px solid transparent; border-bottom: 0; border-radius: 6px 6px 0 0; }
    .tabs a.active { color: var(--accent); border-color: var(--line); background: var(--panel); }
    .kanban { display: grid; grid-template-columns: repeat(7, minmax(240px, 1fr)); gap: 12px; overflow-x: auto; padding-bottom: 8px; }
    .kanban-column { min-width: 240px; border: 1px solid var(--line); background: #15191d; border-radius: 8px; padding: 10px; }
    .kanban-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 10px; }
    .kanban-head h2 { margin: 0; font-size: 14px; }
    .kanban-count { color: var(--muted); font-size: 12px; }
    .kanban-stack { display: grid; gap: 8px; }
    .kanban-card { border: 1px solid var(--line); background: var(--panel); border-radius: 8px; padding: 10px; min-width: 0; }
    .kanban-title { display: block; font-weight: 650; overflow-wrap: anywhere; }
    .kanban-meta { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
    .kanban-empty { color: var(--muted); border: 1px dashed var(--line); border-radius: 8px; padding: 10px; min-height: 56px; }
    @media (max-width: 860px) { .shell { grid-template-columns: 1fr; } aside { position: static; height: auto; } .split { grid-template-columns: 1fr; } main { padding: 16px; } .kanban { grid-template-columns: repeat(7, 260px); } }
  </style>
</head>
<body>
  <div class="shell">
    <aside>
      <div class="brand"><h1>Hermes Hub</h1><a class="muted" href="/logout">Logout</a></div>
      <input id="filter" placeholder="Filter teams">
      <nav class="nav" id="nav"></nav>
    </aside>
    <main id="app"></main>
  </div>
  <script>
    const app = document.getElementById("app");
    const nav = document.getElementById("nav");
    const filter = document.getElementById("filter");
    let state = { dashboard: null, graph: null };
    const esc = (s) => String(s ?? "").replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    async function api(path) {
      const res = await fetch(path);
      if (res.status === 401) location.href = "/login";
      if (!res.ok) throw new Error(await res.text());
      return res.json();
    }
    function linkFor(kind, id) {
      if (kind === "team") return `#/teams/${encodeURIComponent(id)}`;
      if (kind === "assignment") return `#/assignments/${encodeURIComponent(id)}`;
      if (kind === "hub") return `#/hubs/${encodeURIComponent(id)}`;
      return "#/";
    }
    function renderNav() {
      const q = filter.value.toLowerCase();
      const teams = (state.dashboard?.teams || []).filter(t => t.team_name.toLowerCase().includes(q));
      nav.innerHTML = `
        <a href="#/" data-route="/">Dashboard</a>
        <a href="#/kanban" data-route="/kanban">Kanban</a>
        <a href="#/config" data-route="/config">Hub Config</a>
        <a href="#/graph" data-route="/graph">Graph</a>
        ${(state.dashboard?.hubs || []).map(h => `<a href="${linkFor("hub", h)}">Hub: ${esc(h)}</a>`).join("")}
        <h3>Teams</h3>
        ${teams.map(t => `<a href="${linkFor("team", t.team_name)}">${esc(t.team_name)} <span class="muted">(${esc(t.state)})</span></a>`).join("")}
      `;
    }
    function statusClass(value) { return `state-${String(value || "unknown").toLowerCase()}`; }
    function renderTabs(active) {
      const tabs = [
        {id: "dashboard", label: "Dashboard", href: "#/"},
        {id: "kanban", label: "Kanban", href: "#/kanban"},
        {id: "graph", label: "Graph", href: "#/graph"},
        {id: "config", label: "Hub Config", href: "#/config"}
      ];
      return `<nav class="tabs" aria-label="Hub views">${tabs.map(tab => `<a class="${active === tab.id ? "active" : ""}" href="${tab.href}">${esc(tab.label)}</a>`).join("")}</nav>`;
    }
    function renderDashboard() {
      const d = state.dashboard;
      app.innerHTML = `
        <h1>Dashboard</h1>
        ${renderTabs("dashboard")}
        <p class="muted">${esc(d.factory)}</p>
        <section class="grid">
          <div class="card"><div class="metric">${d.counts.teams}</div><div class="muted">Teams</div></div>
          <div class="card"><div class="metric">${d.counts.hubs}</div><div class="muted">Hubs</div></div>
          <div class="card"><div class="metric">${d.counts.active_assignments}</div><div class="muted">Active assignments</div></div>
          <div class="card"><div class="metric">${d.counts.waiting_on_user}</div><div class="muted">Waiting on user</div></div>
          <div class="card"><div class="metric">${d.counts.retrying_assignments}</div><div class="muted">Retrying</div></div>
          <div class="card"><div class="metric">${d.counts.stale_assignments}</div><div class="muted">Stale</div></div>
          <div class="card"><div class="metric">${d.counts.open_alerts}</div><div class="muted">Open alerts</div></div>
        </section>
        <div class="section-head">
          <h2>Org Graph</h2>
          <a class="pill" href="#/graph">Open full graph</a>
        </div>
        <section class="dashboard-graph">
          ${renderOrgGraphSvg({maxAssignmentsPerTeam: 2, minHeight: 420})}
        </section>
        <h2>Waiting on User</h2>
        ${userRequestTable(d.user_requests || [])}
        <h2>Alerts</h2>
        ${alertTable(d.alerts || [])}
        <h2>Teams</h2>
        ${teamTable(d.teams)}
        <h2>Recent Events</h2>
        ${eventTable(d.recent_events)}
      `;
    }
    function teamTable(teams) {
      return `<table><thead><tr><th>Team</th><th>Hub</th><th>State</th><th>Substrate</th><th>Active</th><th>Retry</th><th>Stale</th><th>User</th><th>Last Event</th></tr></thead><tbody>
        ${teams.map(t => `<tr>
          <td><a href="${linkFor("team", t.team_name)}">${esc(t.team_name)}</a></td>
          <td>${t.hub ? `<a href="${linkFor("hub", t.hub)}">${esc(t.hub)}</a>` : ""}</td>
          <td class="${statusClass(t.state)}">${esc(t.state)}</td>
          <td>${esc(t.substrate)}</td>
          <td>${esc(t.active_assignments)}</td>
          <td class="${Number(t.retrying_assignments || 0) ? "state-working" : "muted"}">${esc(t.retrying_assignments || 0)} retry</td>
          <td class="${Number(t.stale_assignments || 0) ? "state-failed" : "muted"}">${esc(t.stale_assignments || 0)} stale</td>
          <td class="${Number(t.open_user_requests || 0) ? "state-open" : "muted"}">${esc(t.open_user_requests || 0)}</td>
          <td class="muted">${esc(t.last_event_at || "never")}</td>
        </tr>`).join("")}
      </tbody></table>`;
    }
    function userRequestTable(requests) {
      const visible = requests.filter(r => ["open", "supplied", "resuming"].includes(String(r.status)));
      if (!visible.length) return '<p class="muted">No user-blocked requests.</p>';
      return `<table><thead><tr><th>Request</th><th>Status</th><th>Kind</th><th>Team</th><th>Assignment</th><th>Title</th><th>Created</th></tr></thead><tbody>
        ${visible.map(r => `<tr>
          <td>${esc(r.request_id)}</td>
          <td class="${statusClass(r.status)}">${esc(r.status)}</td>
          <td>${esc(r.kind)}</td>
          <td><a href="${linkFor("team", r.team_name)}">${esc(r.team_name)}</a></td>
          <td><a href="${linkFor("assignment", r.assignment_id)}">${esc(r.assignment_id)}</a></td>
          <td>${esc(r.title)}</td>
          <td class="muted">${esc(r.created_at)}</td>
        </tr>`).join("")}
      </tbody></table>`;
    }
    function eventTable(events) {
      return `<table><thead><tr><th>Time</th><th>Team</th><th>Kind</th><th>State</th><th>Assignment</th></tr></thead><tbody>
        ${events.map(e => `<tr>
          <td class="muted">${esc(e.ts)}</td>
          <td><a href="${linkFor("team", e.team_name)}">${esc(e.team_name)}</a></td>
          <td>${esc(e.kind)}</td>
          <td class="${statusClass(e.state)}">${esc(e.state || "")}</td>
          <td>${e.assignment_id ? `<a href="${linkFor("assignment", e.assignment_id)}">${esc(e.assignment_id)}</a>` : ""}</td>
        </tr>`).join("")}
      </tbody></table>`;
    }
    function alertTable(alerts) {
      const visible = alerts.filter(a => String(a.status || "open") === "open");
      if (!visible.length) return '<p class="muted">No open alerts.</p>';
      return `<table><thead><tr><th>Alert</th><th>Severity</th><th>Kind</th><th>Team</th><th>Assignment</th><th>Title</th><th>Created</th></tr></thead><tbody>
        ${visible.map(a => `<tr>
          <td>${esc(a.alert_id)}</td>
          <td class="${a.severity === "critical" ? "state-failed" : "state-open"}">${esc(a.severity)}</td>
          <td>${esc(a.kind)}</td>
          <td>${a.team_name ? `<a href="${linkFor("team", a.team_name)}">${esc(a.team_name)}</a>` : ""}</td>
          <td>${a.assignment_id ? `<a href="${linkFor("assignment", a.assignment_id)}">${esc(a.assignment_id)}</a>` : ""}</td>
          <td>${esc(a.title)}</td>
          <td class="muted">${esc(a.created_at)}</td>
        </tr>`).join("")}
      </tbody></table>`;
    }
    function kanbanAssignmentCard(a) {
      return `<article class="kanban-card">
        <a class="kanban-title" href="${linkFor("assignment", a.assignment_id)}">${esc(a.assignment_id)}</a>
        <div class="kanban-meta">
          <span class="pill ${statusClass(a.status)}">${esc(a.status)}</span>
          <span class="pill"><a href="${linkFor("team", a.team_name)}">${esc(a.team_name)}</a></span>
        </div>
        <div class="muted">${esc(a.order_id || "no order")} · ${esc(a.created_at || "")}</div>
        ${a.status_reason ? `<div class="muted">${esc(a.status_reason)}</div>` : ""}
        ${a.next_retry_at ? `<div class="muted">retry ${esc(a.next_retry_at)}</div>` : ""}
      </article>`;
    }
    function kanbanRequestCard(r) {
      return `<article class="kanban-card">
        <span class="kanban-title">${esc(r.title || r.request_id)}</span>
        <div class="kanban-meta">
          <span class="pill ${statusClass(r.status)}">${esc(r.status)}</span>
          <span class="pill">${esc(r.kind)}</span>
          <span class="pill"><a href="${linkFor("team", r.team_name)}">${esc(r.team_name)}</a></span>
        </div>
        <div class="muted"><a href="${linkFor("assignment", r.assignment_id)}">${esc(r.assignment_id)}</a> · ${esc(r.created_at || "")}</div>
      </article>`;
    }
    function kanbanColumn(title, cards, renderer) {
      return `<section class="kanban-column">
        <div class="kanban-head"><h2>${esc(title)}</h2><span class="kanban-count">${cards.length}</span></div>
        <div class="kanban-stack">${cards.length ? cards.map(renderer).join("") : '<div class="kanban-empty">Empty</div>'}</div>
      </section>`;
    }
    function renderKanban() {
      const d = state.dashboard;
      const assignments = d.assignments || [];
      const requests = d.user_requests || [];
      const queued = assignments.filter(a => ["queued", "pending"].includes(String(a.status)));
      const running = assignments.filter(a => ["dispatched", "working", "spawned", "booted"].includes(String(a.status)));
      const waiting = requests.filter(r => String(r.status) === "open");
      const resumingRequests = requests.filter(r => ["supplied", "resuming"].includes(String(r.status)));
      const resumingAssignments = assignments.filter(a => String(a.status) === "resuming");
      const retrying = assignments.filter(a => String(a.status) === "retrying");
      const stale = assignments.filter(a => String(a.status) === "stale");
      const done = assignments.filter(a => String(a.status) === "completed");
      const stopped = assignments.filter(a => ["failed", "canceled", "cancel-requested", "archived"].includes(String(a.status)));
      app.innerHTML = `
        <div class="section-head">
          <h1>Kanban</h1>
          <span class="pill">read-only</span>
        </div>
        ${renderTabs("kanban")}
        <p class="muted">${esc(d.factory)}</p>
        <section class="kanban">
          ${kanbanColumn("Queued", queued, kanbanAssignmentCard)}
          ${kanbanColumn("Running", running, kanbanAssignmentCard)}
          ${kanbanColumn("Waiting on User", waiting, kanbanRequestCard)}
          ${kanbanColumn("Resuming", [...resumingRequests, ...resumingAssignments], card => card.request_id ? kanbanRequestCard(card) : kanbanAssignmentCard(card))}
          ${kanbanColumn("Retrying", retrying, kanbanAssignmentCard)}
          ${kanbanColumn("Stale", stale, kanbanAssignmentCard)}
          ${kanbanColumn("Completed", done, kanbanAssignmentCard)}
          ${kanbanColumn("Stopped", stopped, kanbanAssignmentCard)}
        </section>`;
    }
    async function renderTeam(name) {
      const t = await api(`/api/teams/${encodeURIComponent(name)}`);
      app.innerHTML = `
        <div class="split">
          <section>
            <h1>${esc(t.team_name)}</h1>
            <p><span class="pill ${statusClass(t.state)}">${esc(t.state)}</span> <span class="pill">${esc(t.substrate || "unknown substrate")}</span> ${t.hub ? `<span class="pill">hub: <a href="${linkFor("hub", t.hub)}">${esc(t.hub)}</a></span>` : ""}</p>
            <h2>Journal</h2><pre>${esc(t.journal || "No journal yet.")}</pre>
            <h2>Waiting on User</h2>${userRequestTable(t.user_requests || [])}
            <h2>Alerts</h2>${alertTable(t.alerts || [])}
            <h2>Assignments</h2>${assignmentTable(t.assignments)}
            <h2>Recent Events</h2>${eventTable(t.events)}
          </section>
          <aside class="card" style="position: static; height: auto;">
            <h2>Brief</h2><pre>${esc(t.brief || "No brief.")}</pre>
            <h2>Criteria</h2><pre>${esc(t.criteria || "No criteria.")}</pre>
            <h2>Outbox</h2>
            ${(t.outbox || []).map(o => `<div><span class="muted">${esc(o.relative_path)}</span></div>`).join("") || '<p class="muted">No artifacts.</p>'}
          </aside>
        </div>`;
    }
    async function renderConfig() {
      const config = await api("/api/config");
      const files = config.live.length ? config.live : config.fallback;
      app.innerHTML = `
        <h1>Hub Config</h1>
        ${renderTabs("config")}
        <p class="muted">${config.using_fallback ? "Showing repository templates because no live factory config files exist yet." : "Showing live factory config files."}</p>
        ${files.map(file => `<section>
          <h2>${esc(file.name)} <span class="pill">${esc(file.source)}</span></h2>
          <p class="muted">${esc(file.path)}</p>
          <pre>${esc(file.body || "Empty file.")}</pre>
        </section>`).join("") || '<p class="muted">No config files found.</p>'}`;
    }
    function assignmentTable(rows) {
      return `<table><thead><tr><th>Assignment</th><th>Status</th><th>Created</th><th>Terminal</th></tr></thead><tbody>
        ${rows.map(a => `<tr><td><a href="${linkFor("assignment", a.assignment_id)}">${esc(a.assignment_id)}</a></td><td class="${statusClass(a.status)}">${esc(a.status)}</td><td class="muted">${esc(a.created_at)}</td><td class="muted">${esc(a.terminal_at || "")}</td></tr>`).join("")}
      </tbody></table>`;
    }
    async function renderAssignment(id) {
      const a = await api(`/api/assignments/${encodeURIComponent(id)}`);
      app.innerHTML = `<h1>${esc(a.assignment_id)}</h1>
        <p><span class="pill ${statusClass(a.status)}">${esc(a.status)}</span> <span class="pill">team: <a href="${linkFor("team", a.team_name)}">${esc(a.team_name)}</a></span></p>
        <p class="muted">${esc(a.relative_payload_path || "")}</p>
        <h2>Body</h2><pre>${esc(a.body || "No body available.")}</pre>
        <h2>Waiting on User</h2>${userRequestTable(a.user_requests || [])}
        <h2>Alerts</h2>${alertTable(a.alerts || [])}
        <h2>Resume Chain</h2><pre>${esc(JSON.stringify(a.resumes || [], null, 2))}</pre>
        <h2>Sandbox</h2><pre>${esc(JSON.stringify(a.sandbox || {}, null, 2))}</pre>
        <h2>Events</h2>${eventTable(a.events)}`;
    }
    function renderHub(name) {
      const teams = state.dashboard.teams.filter(t => t.hub === name);
      app.innerHTML = `<h1>Hub: ${esc(name)}</h1><h2>Subteams</h2>${teamTable(teams)}`;
    }
    function renderOrgGraphSvg(options = {}) {
      const d = state.dashboard;
      const maxAssignmentsPerTeam = options.maxAssignmentsPerTeam ?? 4;
      const minHeight = options.minHeight ?? 560;
      const assignmentsByTeam = {};
      for (const assignment of d.assignments || []) {
        (assignmentsByTeam[assignment.team_name] ||= []).push(assignment);
      }
      const teams = [...(d.teams || [])].sort((a, b) => a.team_name.localeCompare(b.team_name));
      const cardW = 220, cardH = 72, xGap = 40, yGap = 90;
      const width = Math.max(920, teams.length * (cardW + xGap) + xGap);
      const root = {x: width / 2 - cardW / 2, y: 32, w: cardW, h: cardH, label: "Boss Team", meta: "public coordinator", kind: "root", href: "#/"};
      const nodes = [root], edges = [];
      teams.forEach((team, i) => {
        const x = xGap + i * (cardW + xGap);
        const teamNode = {
          x, y: root.y + cardH + yGap, w: cardW, h: cardH,
          label: team.team_name,
          meta: `${team.substrate || "unknown"} · ${team.state || "unknown"}`,
          kind: "team",
          href: linkFor("team", team.team_name)
        };
        nodes.push(teamNode);
        edges.push({from: root, to: teamNode});
        (assignmentsByTeam[team.team_name] || []).slice(0, maxAssignmentsPerTeam).forEach((assignment, j) => {
          const assignmentNode = {
            x, y: teamNode.y + cardH + 54 + j * (cardH + 14), w: cardW, h: cardH,
            label: assignment.assignment_id,
            meta: assignment.status || "unknown",
            kind: "assignment",
            href: linkFor("assignment", assignment.assignment_id)
          };
          nodes.push(assignmentNode);
          edges.push({from: teamNode, to: assignmentNode});
        });
      });
      const height = Math.max(minHeight, Math.max(...nodes.map(n => n.y + n.h)) + 40);
      const nodeMarkup = nodes.map(n => `
        <a href="${n.href}">
          <rect class="org-card org-${n.kind}" x="${n.x}" y="${n.y}" width="${n.w}" height="${n.h}"></rect>
          <text class="node-label" x="${n.x + 14}" y="${n.y + 28}">${esc(n.label)}</text>
          <text class="node-meta" x="${n.x + 14}" y="${n.y + 50}">${esc(n.meta)}</text>
        </a>`).join("");
      const edgeMarkup = edges.map(e => {
        const x1 = e.from.x + e.from.w / 2, y1 = e.from.y + e.from.h;
        const x2 = e.to.x + e.to.w / 2, y2 = e.to.y;
        const mid = y1 + (y2 - y1) / 2;
        return `<path class="edge" d="M ${x1} ${y1} V ${mid} H ${x2} V ${y2}"></path>`;
      }).join("");
      return `<svg viewBox="0 0 ${width} ${height}">
        ${edgeMarkup}
        ${nodeMarkup}
      </svg>`;
    }
    async function renderGraph() {
      app.innerHTML = `<h1>Org Graph</h1>${renderTabs("graph")}<p class="muted">Boss team, connected remote teams, and their recent assignments.</p>
        ${renderOrgGraphSvg({maxAssignmentsPerTeam: 4, minHeight: 560})}`;
    }
    async function route() {
      try {
        state.dashboard = state.dashboard || await api("/api/dashboard");
        renderNav();
        const path = location.hash.slice(1) || "/";
        if (path === "/") renderDashboard();
        else if (path === "/kanban") renderKanban();
        else if (path === "/config") await renderConfig();
        else if (path === "/graph") await renderGraph();
        else if (path.startsWith("/teams/")) await renderTeam(decodeURIComponent(path.slice(7)));
        else if (path.startsWith("/assignments/")) await renderAssignment(decodeURIComponent(path.slice(13)));
        else if (path.startsWith("/hubs/")) renderHub(decodeURIComponent(path.slice(6)));
        else renderDashboard();
      } catch (error) {
        app.innerHTML = `<h1>Error</h1><pre>${esc(error.message)}</pre>`;
      }
    }
    filter.addEventListener("input", renderNav);
    window.addEventListener("hashchange", route);
    route();
    setInterval(async () => {
      state.dashboard = await api("/api/dashboard");
      state.graph = null;
      renderNav();
      const path = location.hash.slice(1) || "/";
      if (path === "/") renderDashboard();
      else if (path === "/kanban") renderKanban();
      else if (path === "/graph") await renderGraph();
      else if (path.startsWith("/hubs/")) renderHub(decodeURIComponent(path.slice(6)));
    }, 10000);
  </script>
</body>
</html>"""


LOGIN_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Hermes Hub Login</title>
  <style>
    * { box-sizing: border-box; }
    body { margin: 0; min-height: 100vh; display: grid; place-items: center; padding: 24px; background: #101214; color: #edf1f5; font: 14px system-ui, sans-serif; }
    form { width: min(420px, 100%); border: 1px solid #2b3238; background: #181c20; border-radius: 8px; padding: 22px; }
    h1 { margin: 0 0 16px; font-size: 22px; line-height: 1.2; }
    input, button { display: block; width: 100%; min-width: 0; padding: 10px 12px; border-radius: 6px; border: 1px solid #2b3238; background: #101214; color: #edf1f5; font: inherit; }
    button { margin-top: 10px; background: #67d4b4; color: #101214; font-weight: 700; cursor: pointer; }
    p { color: #ff7b7b; min-height: 20px; }
  </style>
</head>
<body>
  <form method="post" action="/login">
    <h1>Hermes Hub</h1>
    <input name="code" type="password" autocomplete="current-password" placeholder="Access code" autofocus>
    <button type="submit">Enter</button>
    <p>__ERROR__</p>
  </form>
</body>
</html>"""


class ViewerConfig:
    def __init__(self, *, factory: Path, db_path: Path, access_code: str, cookie_secret: str) -> None:
        self.factory = factory
        self.db_path = db_path
        self.access_code = access_code
        self.cookie_secret = cookie_secret


class ViewerHandler(BaseHTTPRequestHandler):
    server_version = "HermesViewer/0.1"

    @property
    def config(self) -> ViewerConfig:
        return self.server.config  # type: ignore[attr-defined, return-value]

    def log_message(self, fmt: str, *args: Any) -> None:
        if os.getenv("HARNESS_VIEWER_QUIET"):
            return
        super().log_message(fmt, *args)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/healthz":
            self._json({"ok": True})
            return
        if parsed.path == "/login":
            self._html(LOGIN_HTML.replace("__ERROR__", ""))
            return
        if parsed.path == "/logout":
            self.send_response(HTTPStatus.FOUND)
            self.send_header("Location", "/login")
            self.send_header("Set-Cookie", f"{auth.COOKIE_NAME}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax")
            self.end_headers()
            return
        if not self._authenticated():
            self._redirect_login()
            return
        if parsed.path == "/":
            self._html(APP_HTML)
            return
        if parsed.path.startswith("/api/"):
            self._api(parsed.path)
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/login":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8")
        submitted = parse_qs(body).get("code", [""])[0]
        if auth.code_matches(self.config.access_code, submitted):
            cookie = auth.issue_session(self.config.cookie_secret)
            self.send_response(HTTPStatus.FOUND)
            self.send_header("Location", "/")
            self.send_header("Set-Cookie", f"{auth.COOKIE_NAME}={cookie}; Path=/; HttpOnly; SameSite=Lax")
            self.end_headers()
            return
        self._html(LOGIN_HTML.replace("__ERROR__", html.escape("Invalid access code.")), status=HTTPStatus.UNAUTHORIZED)

    def _api(self, path: str) -> None:
        try:
            if path == "/api/dashboard":
                self._json(dashboard(self.config.factory, self.config.db_path))
                return
            if path == "/api/graph":
                self._json(graph(self.config.factory, self.config.db_path))
                return
            if path == "/api/config":
                self._json(hub_config(self.config.factory))
                return
            if path.startswith("/api/teams/"):
                team_name = unquote(path.removeprefix("/api/teams/"))
                detail = team_detail(self.config.factory, self.config.db_path, team_name)
                if detail is None:
                    self.send_error(HTTPStatus.NOT_FOUND, "unknown team")
                    return
                self._json(detail)
                return
            if path.startswith("/api/assignments/"):
                assignment_id = unquote(path.removeprefix("/api/assignments/"))
                detail = assignment_detail(self.config.factory, self.config.db_path, assignment_id)
                if detail is None:
                    self.send_error(HTTPStatus.NOT_FOUND, "unknown assignment")
                    return
                self._json(detail)
                return
        except Exception as error:
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(error))
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def _authenticated(self) -> bool:
        cookie = SimpleCookie(self.headers.get("Cookie"))
        morsel = cookie.get(auth.COOKIE_NAME)
        return auth.verify_session(self.config.cookie_secret, morsel.value if morsel else None)

    def _redirect_login(self) -> None:
        if self.path.startswith("/api/"):
            self._json({"error": "authentication required"}, status=HTTPStatus.UNAUTHORIZED)
            return
        self.send_response(HTTPStatus.FOUND)
        self.send_header("Location", "/login")
        self.end_headers()

    def _html(self, body: str, *, status: HTTPStatus = HTTPStatus.OK) -> None:
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _json(self, data: Any, *, status: HTTPStatus = HTTPStatus.OK) -> None:
        encoded = json.dumps(data, indent=2, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


class ViewerServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], config: ViewerConfig) -> None:
        self.config = config
        super().__init__(server_address, ViewerHandler)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Serve the read-only Hermes hub web viewer.")
    parser.add_argument("--factory", default=os.getenv("HARNESS_FACTORY", "factory"), help="Hermes factory path")
    parser.add_argument("--db", default=None, help="SQLite database path; defaults to <factory>/harness.sqlite3")
    parser.add_argument("--host", default=os.getenv("HARNESS_VIEWER_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("HARNESS_VIEWER_PORT", "8090")))
    parser.add_argument("--access-code", default=os.getenv("HARNESS_VIEWER_ACCESS_CODE"))
    parser.add_argument("--cookie-secret", default=os.getenv("HARNESS_VIEWER_COOKIE_SECRET"))
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if not args.access_code:
        raise SystemExit("Set HARNESS_VIEWER_ACCESS_CODE or pass --access-code.")
    factory = factory_path(args.factory)
    db_path = Path(args.db).resolve() if args.db else db.default_db_path(factory)
    db.init_db(db_path)
    config = ViewerConfig(
        factory=factory,
        db_path=db_path,
        access_code=args.access_code,
        cookie_secret=args.cookie_secret or secrets.token_urlsafe(32),
    )
    server = ViewerServer((args.host, args.port), config)
    print(f"Hermes hub viewer listening on http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
