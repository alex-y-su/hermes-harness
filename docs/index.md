# Hermes Hub

Live operator console for the Hermes harness, powered by SilverBullet + the
read-only viewer API. Pages try the Docker service URL first and the native
loopback URL second.

## Live views

* [[Dashboard]] — counts, team status table, recent assignments
* [[Assignments]] — flat list of all recent assignments
* [[OrgGraph]] — team / hub topology rendered with Mermaid

## Static content

* `templates/` — read-write mount of `bus_template/` (team scaffolding)
* `teams/` — read-only mount of the live factory's team subtree

  Open any team's brief, e.g. `[[teams/research/brief]]`.

## Configuration

Plug list and SilverBullet config live in [[CONFIG]].
