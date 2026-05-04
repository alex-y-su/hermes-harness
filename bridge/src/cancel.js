import { existsSync } from 'node:fs';
import { join } from 'node:path';
import { moveIfExists, readJson } from './fs_contract.js';

function timestamp() {
  return new Date().toISOString().replace(/[:.]/g, '-');
}

export async function cancelTeam({ db, secrets, a2aClient, factoryDir, teamName, teamDir }) {
  const transport = readJson(join(teamDir, 'transport.json'));
  const bearerToken = secrets.resolve(transport.team_bearer_token_ref);
  const active = db.activeAssignments(teamName);
  for (const assignment of active) {
    try {
      await a2aClient.cancelTask({ transport, bearerToken, taskId: assignment.a2a_task_id });
      db.markCancelRequested(assignment.assignment_id);
      db.appendEvent({
        teamName,
        assignmentId: assignment.assignment_id,
        taskId: assignment.a2a_task_id,
        source: 'a2a-bridge',
        kind: 'cancel-requested',
        state: 'cancel-requested',
      });
    } catch (error) {
      db.appendEvent({
        teamName,
        assignmentId: assignment.assignment_id,
        taskId: assignment.a2a_task_id,
        source: 'a2a-bridge',
        kind: 'cancel-failed',
        state: 'failed',
        metadata: { error: error.message },
      });
    }
  }

  const handle = db.getSubstrateHandle(teamName);
  db.appendEvent({
    teamName,
    source: 'a2a-bridge',
    kind: 'archive',
    state: 'archived',
    metadata: { substrate_handle: handle?.handle ?? null, substrate_cancel_stub: true },
  });

  const archiveDir = join(factoryDir, '..', 'archive', `teams_${teamName}_${timestamp()}`);
  if (existsSync(teamDir)) moveIfExists(teamDir, archiveDir);
  return { archivedPath: archiveDir, canceled: active.length };
}
