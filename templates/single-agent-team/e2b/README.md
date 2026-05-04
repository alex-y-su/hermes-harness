# E2B Assembly

This folder describes how the local provisioner assembles the single-agent team
inside an assignment sandbox.

`setup.sh` runs inside `/home/user/workspace` for every assignment. It must stay
non-interactive, avoid cron, and never write raw provider keys into markdown.
