# Assignments

All recent assignments across every team.

The viewer exposes per-assignment detail at `/api/assignments/<id>` but does not
expose a list endpoint. The list below is derived from the `assignments` array
returned by `/api/dashboard` (top 100, ordered by `created_at` desc).

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

function hermes_assignments()
  local res = hermes_fetch("/api/dashboard")
  if not res.ok then
    return widget.markdownBlock("> **error** viewer API returned status " .. tostring(res.status))
  end
  local data = res.body
  local lines = {}
  table.insert(lines, "| assignment | team | status | created | dispatched | terminal |")
  table.insert(lines, "| --- | --- | --- | --- | --- | --- |")
  for _, a in ipairs(data.assignments or {}) do
    table.insert(lines, "| " .. tostring(a.assignment_id)
      .. " | [[teams/" .. tostring(a.team_name) .. "/brief]]"
      .. " | " .. tostring(a.status)
      .. " | " .. tostring(a.created_at or "-")
      .. " | " .. tostring(a.dispatched_at or "-")
      .. " | " .. tostring(a.terminal_at or "-") .. " |")
  end
  if #data.assignments == 0 then
    return widget.markdownBlock("_No assignments yet._")
  end
  return widget.markdownBlock(table.concat(lines, "\n"))
end
```

${hermes_assignments()}

See also: [[Dashboard]], [[OrgGraph]], [[index]].
