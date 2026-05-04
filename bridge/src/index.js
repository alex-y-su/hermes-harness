import { resolve } from 'node:path';
import { BridgeDb } from './db.js';
import { BridgeDaemon } from './daemon.js';
import { SecretResolver } from './secrets.js';

const factoryDir = resolve(process.env.HARNESS_FACTORY_DIR ?? 'factory');
const dbPath = resolve(process.env.HARNESS_SQLITE_PATH ?? 'bridge/hermes-harness.sqlite');
const envPath = process.env.HARNESS_ENV_PATH;

if (!envPath) {
  throw new Error('HARNESS_ENV_PATH must point to the external .env file');
}

const db = new BridgeDb(dbPath);
const daemon = new BridgeDaemon({
  factoryDir,
  db,
  secrets: new SecretResolver(envPath),
  port: process.env.HARNESS_A2A_BRIDGE_PORT ?? 8787,
  pollMs: process.env.HARNESS_A2A_BRIDGE_POLL_MS ?? 2000,
});

process.on('SIGINT', async () => {
  await daemon.stop();
  db.close();
  process.exit(0);
});
process.on('SIGTERM', async () => {
  await daemon.stop();
  db.close();
  process.exit(0);
});

await daemon.start();
