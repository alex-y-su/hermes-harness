import { existsSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { assignmentIdFromPath, moveIfExists, readJson, writeJson } from './fs_contract.js';

export async function dispatchAssignment({ db, secrets, a2aClient, teamName, teamDir, inboxPath }) {
  const assignmentId = assignmentIdFromPath(inboxPath);
  const existing = db.ensureAssignment({ assignmentId, teamName, inboxPath });
  if (existing?.a2a_task_id) return { skipped: true, taskId: existing.a2a_task_id };
  if (!existsSync(inboxPath)) return { skipped: true, missing: true };

  const transport = readJson(join(teamDir, 'transport.json'));
  const bearerToken = secrets.resolve(transport.team_bearer_token_ref);
  const pushToken = secrets.resolve(transport.push_token_ref);
  const text = readFileSync(inboxPath, 'utf8');

  let sendResult;
  try {
    sendResult = await a2aClient.sendAssignment({
      transport,
      bearerToken,
      pushToken,
      assignmentId,
      text,
    });
  } catch (error) {
    db.updateAssignmentStatus({ assignmentId, status: 'failed' });
    const failurePath = join(dirname(inboxPath), `${assignmentId}.failed.json`);
    writeJson(failurePath, {
      assignment_id: assignmentId,
      team_name: teamName,
      failed_at: new Date().toISOString(),
      error: error.message,
    });
    db.appendEvent({
      teamName,
      assignmentId,
      source: 'a2a-bridge',
      kind: 'dispatch-failed',
      state: 'failed',
      payloadPath: failurePath,
      metadata: { error: error.message },
    });
    throw error;
  }

  const { taskId, result } = sendResult;
  const inFlightPath = join(dirname(inboxPath), `${assignmentId}.in-flight.md`);
  db.markDispatched({ assignmentId, taskId, inFlightPath });
  writeJson(join(dirname(inboxPath), `${assignmentId}.dispatched.json`), {
    assignment_id: assignmentId,
    team_name: teamName,
    task_id: taskId,
    dispatched_at: new Date().toISOString(),
    response: result,
  });
  moveIfExists(inboxPath, inFlightPath);
  db.appendEvent({
    teamName,
    assignmentId,
    taskId,
    source: 'a2a-bridge',
    kind: 'dispatched',
    state: 'dispatched',
    payloadPath: inFlightPath,
  });
  return { dispatched: true, taskId };
}
