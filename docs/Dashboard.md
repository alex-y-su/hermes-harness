# Hermes Hub Dashboard

Live view of the running factory. Data is fetched from the read-only viewer API
every time this page is rendered.

```space-lua
function hermes_fetch(path)
  local urls = {
    "http://viewer:8090" .. path,
    "http://127.0.0.1:8091" .. path,
  }
  local last = nil
  for _, url in ipairs(urls) do
    local res = net.proxyFetch(url)
    if res.ok then return res end
    last = res
  end
  return last
end

-- Renders the Hermes hub dashboard as a markdown block.
function hermes_dashboard()
  local res = hermes_fetch("/api/dashboard")
  if not res.ok then
    return widget.markdownBlock("> **error** viewer API returned status " .. tostring(res.status))
  end
  local data = res.body
  local lines = {}
  table.insert(lines, "## Counts")
  table.insert(lines, "")
  table.insert(lines, "| metric | value |")
  table.insert(lines, "| --- | --- |")
  table.insert(lines, "| teams | " .. tostring(data.counts.teams) .. " |")
  table.insert(lines, "| hubs | " .. tostring(data.counts.hubs) .. " |")
  table.insert(lines, "| active assignments | " .. tostring(data.counts.active_assignments) .. " |")
  table.insert(lines, "")
  table.insert(lines, "## Teams")
  table.insert(lines, "")
  table.insert(lines, "| team | state | active | total | hub |")
  table.insert(lines, "| --- | --- | --- | --- | --- |")
  for _, t in ipairs(data.teams or {}) do
    local hub = t.hub or "-"
    table.insert(lines, "| [[teams/" .. t.team_name .. "/brief]] | " .. tostring(t.state)
      .. " | " .. tostring(t.active_assignments)
      .. " | " .. tostring(t.total_assignments)
      .. " | " .. tostring(hub) .. " |")
  end
  table.insert(lines, "")
  table.insert(lines, "## Recent assignments (top 10)")
  table.insert(lines, "")
  table.insert(lines, "| assignment | team | status | created |")
  table.insert(lines, "| --- | --- | --- | --- |")
  local count = 0
  for _, a in ipairs(data.assignments or {}) do
    if count >= 10 then break end
    table.insert(lines, "| " .. tostring(a.assignment_id)
      .. " | [[teams/" .. tostring(a.team_name) .. "/brief]]"
      .. " | " .. tostring(a.status)
      .. " | " .. tostring(a.created_at) .. " |")
    count = count + 1
  end
  return widget.markdownBlock(table.concat(lines, "\n"))
end
```

${hermes_dashboard()}

See also: [[Assignments]], [[OrgGraph]], [[index]].
