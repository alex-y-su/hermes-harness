import { mkdirSync, writeFileSync } from 'node:fs';
import { basename, join } from 'node:path';
import { appendJournal, ensureDir, readJson, writeJson } from './fs_contract.js';
import { verifyPushSignature } from './hmac.js';

function bearerFromHeader(header) {
  const match = header?.match(/^Bearer\s+(.+)$/i);
  return match?.[1];
}

function artifactName(artifact, index) {
  const raw = artifact?.name ?? artifact?.artifact_id ?? artifact?.id ?? `artifact-${index + 1}.md`;
  return basename(String(raw)).replace(/[^A-Za-z0-9._-]/g, '_') || `artifact-${index + 1}.md`;
}

function artifactText(artifact) {
  if (typeof artifact === 'string') return artifact;
  if (artifact?.text) return artifact.text;
  if (Array.isArray(artifact?.parts)) {
    return artifact.parts
      .map((part) => part.text ?? part.file?.uri ?? part.file?.bytes ?? JSON.stringify(part))
      .join('\n');
  }
  return JSON.stringify(artifact, null, 2);
}

export async function processPush({ db, secrets, factoryDir, headers, body }) {
  const teamName = body.team_name ?? body.teamName;
  const taskId = body.task_id ?? body.taskId ?? body.task?.id;
  const state = body.state ?? body.status?.state ?? body.task?.status?.state;
  const sequence = body.sequence;
  const signature = headers['x-a2a-notification-token'];
  if (!teamName || !taskId || !state || sequence === undefined || !signature) {
    return { status: 400, body: { error: 'missing required push fields' } };
  }

  const teamDir = join(factoryDir, 'teams', teamName);
  let transport;
  try {
    transport = readJson(join(teamDir, 'transport.json'));
  } catch {
    return { status: 404, body: { error: 'unknown team' } };
  }

  const expectedBearer = secrets.resolve(transport.push_token_ref);
  if (bearerFromHeader(headers.authorization) !== expectedBearer) {
    return { status: 401, body: { error: 'invalid bearer token' } };
  }

  const hmacSecret = secrets.resolve(transport.bridge_secret_ref ?? transport.push_token_ref);
  if (!verifyPushSignature({ expected: signature, secret: hmacSecret, teamName, taskId, state, sequence, body })) {
    return { status: 401, body: { error: 'invalid push signature' } };
  }

  const assignment = db.getAssignmentByTask(teamName, taskId);
  if (!assignment && body.kind !== 'peer-registration') {
    return { status: 404, body: { error: 'unknown task' } };
  }

  const event = db.appendEvent({
    teamName,
    assignmentId: assignment?.assignment_id,
    taskId,
    sequence,
    source: 'a2a-push',
    kind: 'push',
    state,
    costCents: body.cost_cents,
    durationMs: body.duration_ms,
    signature,
    metadata: body.metadata ?? {},
  });
  if (!event.inserted) {
    db.appendEvent({
      teamName,
      assignmentId: assignment?.assignment_id,
      taskId,
      source: 'a2a-push',
      kind: 'push-duplicate',
      state,
      signature,
      metadata: { duplicate_sequence: sequence },
    });
    return { status: 202, body: { duplicate: true } };
  }

  const statusPath = join(teamDir, 'status.json');
  writeJson(statusPath, {
    team_name: teamName,
    task_id: taskId,
    assignment_id: assignment?.assignment_id,
    state,
    sequence,
    updated_at: new Date().toISOString(),
    message: body.message ?? body.status?.message ?? null,
  });

  if (state === 'working') {
    appendJournal(teamDir, `working ${assignment?.assignment_id ?? taskId}: ${body.message ?? ''}`.trim());
    db.updateAssignmentStatus({ assignmentId: assignment.assignment_id, status: 'working' });
  } else if (state === 'input-required' || state === 'auth-required') {
    const escalationDir = join(factoryDir, 'escalations');
    ensureDir(escalationDir);
    const kind = state === 'auth-required' ? 'secret-request' : 'input-required';
    const path = join(escalationDir, `${teamName}_${assignment?.assignment_id ?? taskId}_${kind}.md`);
    writeFileSync(path, `# ${kind}: ${teamName}\n\n${body.message ?? JSON.stringify(body, null, 2)}\n`);
    db.updateAssignmentStatus({ assignmentId: assignment.assignment_id, status: state });
  } else if (state === 'completed') {
    const outbox = join(teamDir, 'outbox');
    mkdirSync(outbox, { recursive: true });
    const artifacts = body.artifacts ?? body.task?.artifacts ?? [{ name: `${assignment.assignment_id}.result.md`, text: body.message ?? JSON.stringify(body, null, 2) }];
    const written = artifacts.map((artifact, index) => {
      const path = join(outbox, artifactName(artifact, index));
      writeFileSync(path, artifactText(artifact));
      return path;
    });
    db.markTerminal({ assignmentId: assignment.assignment_id, status: 'completed', completedPath: written[0] });
  } else if (state === 'failed') {
    const escalationDir = join(factoryDir, 'escalations');
    ensureDir(escalationDir);
    const path = join(escalationDir, `${teamName}_${assignment.assignment_id}_failed.md`);
    writeFileSync(path, `# failed: ${teamName}\n\n${body.message ?? JSON.stringify(body, null, 2)}\n`);
    db.markTerminal({ assignmentId: assignment.assignment_id, status: 'failed' });
    db.appendEvent({
      teamName,
      assignmentId: assignment.assignment_id,
      taskId,
      source: 'a2a-bridge',
      kind: 'decision',
      state: 'failed',
      payloadPath: path,
    });
  } else if (state === 'canceled') {
    const haltWasLocal = true;
    db.markTerminal({ assignmentId: assignment.assignment_id, status: haltWasLocal ? 'canceled' : 'failed' });
  }

  return { status: 202, body: { ok: true } };
}
