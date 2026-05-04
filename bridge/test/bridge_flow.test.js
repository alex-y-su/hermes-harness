import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { BridgeDb } from '../src/db.js';
import { dispatchAssignment } from '../src/dispatch.js';
import { processPush } from '../src/push.js';
import { signPush } from '../src/hmac.js';
import { SecretResolver } from '../src/secrets.js';

function setup() {
  const root = mkdtempSync(join(tmpdir(), 'hermes-bridge-'));
  const factoryDir = join(root, 'factory');
  const teamDir = join(factoryDir, 'teams', 'dev');
  mkdirSync(join(teamDir, 'inbox'), { recursive: true });
  mkdirSync(join(teamDir, 'outbox'), { recursive: true });
  writeFileSync(
    join(teamDir, 'transport.json'),
    JSON.stringify({
      protocol: 'a2a',
      endpoint_url: 'https://remote.example/rpc',
      push_url: 'https://boss.example/a2a/push',
      team_bearer_token_ref: 'env://TEAM_BEARER',
      push_token_ref: 'env://PUSH_TOKEN',
      bridge_secret_ref: 'env://BRIDGE_SECRET',
    })
  );
  const envPath = join(root, 'bridge.env');
  writeFileSync(envPath, 'TEAM_BEARER=remote-token\nPUSH_TOKEN=push-token\nBRIDGE_SECRET=bridge-secret\n');
  return { root, factoryDir, teamDir, db: new BridgeDb(join(root, 'bridge.sqlite')), secrets: new SecretResolver(envPath) };
}

test('dispatch is idempotent after a task id is recorded', async () => {
  const { db, secrets, teamDir } = setup();
  const inboxPath = join(teamDir, 'inbox', 'assign-1.md');
  writeFileSync(inboxPath, '# Assignment\n');
  let sends = 0;
  const a2aClient = {
    async sendAssignment() {
      sends += 1;
      return { taskId: 'task-1', result: { id: 'task-1', kind: 'task' } };
    },
  };

  await dispatchAssignment({ db, secrets, a2aClient, teamName: 'dev', teamDir, inboxPath });
  await dispatchAssignment({ db, secrets, a2aClient, teamName: 'dev', teamDir, inboxPath });

  assert.equal(sends, 1);
  assert.equal(db.getAssignment('assign-1').a2a_task_id, 'task-1');
  db.close();
});

test('push duplicate sequence is accepted as a no-op', async () => {
  const { db, secrets, factoryDir } = setup();
  db.ensureAssignment({ assignmentId: 'assign-1', teamName: 'dev', inboxPath: '/tmp/assign-1.md' });
  db.markDispatched({ assignmentId: 'assign-1', taskId: 'task-1', inFlightPath: '/tmp/assign-1.in-flight.md' });
  const body = { team_name: 'dev', task_id: 'task-1', state: 'working', sequence: 1, message: 'started' };
  const signature = signPush({
    secret: 'bridge-secret',
    teamName: 'dev',
    taskId: 'task-1',
    state: 'working',
    sequence: 1,
    body,
  });
  const headers = { authorization: 'Bearer push-token', 'x-a2a-notification-token': signature };

  assert.equal((await processPush({ db, secrets, factoryDir, headers, body })).status, 202);
  const duplicate = await processPush({ db, secrets, factoryDir, headers, body });

  assert.equal(duplicate.status, 202);
  assert.deepEqual(duplicate.body, { duplicate: true });
  db.close();
});
