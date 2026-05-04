import { mkdirSync, readdirSync, readFileSync, renameSync, writeFileSync, appendFileSync } from 'node:fs';
import { basename, dirname, join } from 'node:path';

export function ensureDir(path) {
  mkdirSync(path, { recursive: true });
}

export function readJson(path) {
  return JSON.parse(readFileSync(path, 'utf8'));
}

export function writeJson(path, value) {
  ensureDir(dirname(path));
  writeFileSync(path, `${JSON.stringify(value, null, 2)}\n`);
}

export function appendJournal(teamDir, line) {
  appendFileSync(join(teamDir, 'journal.md'), `${new Date().toISOString()} ${line}\n`);
}

export function discoverTeams(factoryDir) {
  const teamsDir = join(factoryDir, 'teams');
  try {
    return readdirSync(teamsDir, { withFileTypes: true })
      .filter((entry) => entry.isDirectory())
      .map((entry) => ({ name: entry.name, dir: join(teamsDir, entry.name) }));
  } catch {
    return [];
  }
}

export function assignmentIdFromPath(path) {
  return basename(path).replace(/\.md$/, '');
}

export function moveIfExists(from, to) {
  ensureDir(dirname(to));
  try {
    renameSync(from, to);
    return true;
  } catch (error) {
    if (error.code === 'ENOENT') return false;
    throw error;
  }
}
