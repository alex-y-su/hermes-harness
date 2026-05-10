import { Template } from "e2b"

export const template = Template()
  .fromImage("e2bdev/base")
  .runCmd("apt-get update && apt-get install -y git ripgrep jq sqlite3 python3 python3-pip nodejs npm curl")
  .runCmd("python3 -m pip install --break-system-packages hermes-harness || true")
