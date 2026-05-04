import test from 'node:test';
import assert from 'node:assert/strict';
import { canonicalJson, signPush, verifyPushSignature } from '../src/hmac.js';

test('canonicalJson is stable for object key ordering', () => {
  assert.equal(canonicalJson({ b: 1, a: { d: 2, c: 3 } }), canonicalJson({ a: { c: 3, d: 2 }, b: 1 }));
});

test('push signatures verify and reject tampering', () => {
  const body = { state: 'working', sequence: 7, task_id: 'task-1', team_name: 'dev' };
  const signature = signPush({
    secret: 'bridge-secret',
    teamName: 'dev',
    taskId: 'task-1',
    state: 'working',
    sequence: 7,
    body,
  });
  assert.equal(
    verifyPushSignature({
      expected: `sha256=${signature}`,
      secret: 'bridge-secret',
      teamName: 'dev',
      taskId: 'task-1',
      state: 'working',
      sequence: 7,
      body,
    }),
    true
  );
  assert.equal(
    verifyPushSignature({
      expected: signature,
      secret: 'bridge-secret',
      teamName: 'dev',
      taskId: 'task-1',
      state: 'completed',
      sequence: 7,
      body,
    }),
    false
  );
});
