import { readFileSync } from 'node:fs';

export function parseDotEnv(text) {
  const values = {};
  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith('#')) continue;
    const match = line.match(/^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$/);
    if (!match) continue;
    let value = match[2].trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    values[match[1]] = value.replace(/\\n/g, '\n');
  }
  return values;
}

export class SecretResolver {
  constructor(envPath) {
    this.envPath = envPath;
    this.values = envPath ? parseDotEnv(readFileSync(envPath, 'utf8')) : {};
  }

  resolve(ref) {
    if (!ref) return undefined;
    if (!ref.startsWith('env://')) {
      throw new Error(`Unsupported secret ref: ${ref}`);
    }
    const key = ref.slice('env://'.length);
    const value = this.values[key] ?? process.env[key];
    if (!value) {
      throw new Error(`Missing secret for ${ref}`);
    }
    return value;
  }
}
