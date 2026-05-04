import { createServer } from 'node:http';
import { existsSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { A2AClient } from './a2a_client.js';
import { cancelTeam } from './cancel.js';
import { dispatchAssignment } from './dispatch.js';
import { discoverTeams, ensureDir, writeJson } from './fs_contract.js';
import { processPush } from './push.js';

async function readJsonBody(req) {
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  if (!chunks.length) return {};
  return JSON.parse(Buffer.concat(chunks).toString('utf8'));
}

export class BridgeDaemon {
  constructor({ factoryDir, db, secrets, port = 8787, pollMs = 2000, a2aClient = new A2AClient() }) {
    this.factoryDir = factoryDir;
    this.db = db;
    this.secrets = secrets;
    this.port = Number(port);
    this.pollMs = Number(pollMs);
    this.a2aClient = a2aClient;
    this.seenHalts = new Set();
    this.inProgress = new Set();
    this.server = undefined;
    this.timer = undefined;
    this.heartbeatTimer = undefined;
  }

  async start() {
    this.server = createServer(async (req, res) => {
      if (req.method !== 'POST' || req.url !== '/a2a/push') {
        res.writeHead(404, { 'content-type': 'application/json' });
        res.end(JSON.stringify({ error: 'not found' }));
        return;
      }
      try {
        const body = await readJsonBody(req);
        const result = await processPush({
          db: this.db,
          secrets: this.secrets,
          factoryDir: this.factoryDir,
          headers: {
            authorization: req.headers.authorization,
            'x-a2a-notification-token': req.headers['x-a2a-notification-token'],
          },
          body,
        });
        res.writeHead(result.status, { 'content-type': 'application/json' });
        res.end(JSON.stringify(result.body));
      } catch (error) {
        res.writeHead(500, { 'content-type': 'application/json' });
        res.end(JSON.stringify({ error: error.message }));
      }
    });
    await new Promise((resolve) => this.server.listen(this.port, resolve));
    this.heartbeat();
    this.heartbeatTimer = setInterval(() => this.heartbeat(), 30_000);
    this.timer = setInterval(() => this.tick().catch((error) => this.recordError(error)), this.pollMs);
    await this.tick();
  }

  async stop() {
    clearInterval(this.timer);
    clearInterval(this.heartbeatTimer);
    if (this.server) await new Promise((resolve) => this.server.close(resolve));
  }

  heartbeat() {
    writeJson(join(this.factoryDir, 'status', 'a2a-bridge.json'), {
      service: 'a2a-bridge',
      state: existsSync(join(this.factoryDir, 'HALT_a2a-bridge.flag')) ? 'halting' : 'running',
      pid: process.pid,
      port: this.port,
      updated_at: new Date().toISOString(),
    });
  }

  recordError(error) {
    this.db.appendEvent({
      teamName: 'a2a-bridge',
      source: 'a2a-bridge',
      kind: 'error',
      state: 'failed',
      metadata: { error: error.message },
    });
  }

  async tick() {
    if (existsSync(join(this.factoryDir, 'HALT_a2a-bridge.flag'))) {
      await this.stop();
      return;
    }
    for (const team of discoverTeams(this.factoryDir)) {
      await this.processTeam(team);
    }
  }

  async processTeam({ name, dir }) {
    const haltPath = join(dir, 'HALT.flag');
    if (existsSync(haltPath) && !this.seenHalts.has(name)) {
      this.seenHalts.add(name);
      await cancelTeam({
        db: this.db,
        secrets: this.secrets,
        a2aClient: this.a2aClient,
        factoryDir: this.factoryDir,
        teamName: name,
        teamDir: dir,
      });
      return;
    }
    const inbox = join(dir, 'inbox');
    ensureDir(inbox);
    for (const entry of readdirSync(inbox)) {
      if (!entry.endsWith('.md') || entry.endsWith('.in-flight.md')) continue;
      const path = join(inbox, entry);
      if (!statSync(path).isFile() || this.inProgress.has(path)) continue;
      this.inProgress.add(path);
      try {
        await dispatchAssignment({
          db: this.db,
          secrets: this.secrets,
          a2aClient: this.a2aClient,
          teamName: name,
          teamDir: dir,
          inboxPath: path,
        });
      } finally {
        this.inProgress.delete(path);
      }
    }
  }
}
