# Org Graph

Hermes team and hub topology, fetched from `http://viewer:8090/api/graph` and
rendered as a Mermaid `graph TD`. Requires the
[silverbullet-mermaid](https://github.com/silverbulletmd/silverbullet-mermaid)
plug — it is enabled in [[CONFIG]].

The API also returns `assignment:` nodes; including all of them quickly turns
the diagram into a hairball, so this page renders only `team` and `hub` nodes.
TODO: revisit if we need an assignment-level overview here. Mermaid also cannot
represent arbitrary metadata (state, active counts) on nodes — those are visible
on [[Dashboard]].

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

-- Mermaid IDs must be alphanumerics; build a stable mapping from API ids.
local function _mermaid_id(raw)
  local out = string.gsub(tostring(raw), "[^%w]", "_")
  return out
end

function hermes_org_graph()
  local res = hermes_fetch("/api/graph")
  if not res.ok then
    return widget.markdownBlock("> **error** viewer API returned status " .. tostring(res.status))
  end
  local data = res.body
  local keep = {}
  local lines = {"```mermaid", "graph TD"}
  for _, n in ipairs(data.nodes or {}) do
    if n.type == "team" or n.type == "hub" then
      keep[n.id] = true
      local mid = _mermaid_id(n.id)
      table.insert(lines, "  " .. mid .. "[\"" .. tostring(n.label) .. "\"]")
    end
  end
  for _, e in ipairs(data.edges or {}) do
    if keep[e.source] and keep[e.target] then
      table.insert(lines, "  " .. _mermaid_id(e.source) .. " --> " .. _mermaid_id(e.target))
    end
  end
  if #lines == 2 then
    table.insert(lines, "  empty[\"(no teams yet)\"]")
  end
  table.insert(lines, "```")
  return widget.markdownBlock(table.concat(lines, "\n"))
end
```

${hermes_org_graph()}

See also: [[Dashboard]], [[Assignments]], [[index]].
