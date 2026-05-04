import { createHash, createHmac, timingSafeEqual } from 'node:crypto';

export function canonicalJson(value) {
  if (value === null || typeof value !== 'object') {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map((item) => canonicalJson(item)).join(',')}]`;
  }
  return `{${Object.keys(value)
    .sort()
    .map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`)
    .join(',')}}`;
}

export function canonicalBodyHash(body) {
  return createHash('sha256').update(canonicalJson(body)).digest('hex');
}

export function pushSignaturePayload({ teamName, taskId, state, sequence, bodyHash }) {
  return [teamName, taskId, state, String(sequence), bodyHash].join('\n');
}

export function signPush({ secret, teamName, taskId, state, sequence, body }) {
  const bodyHash = canonicalBodyHash(body);
  return createHmac('sha256', secret)
    .update(pushSignaturePayload({ teamName, taskId, state, sequence, bodyHash }))
    .digest('hex');
}

export function verifyPushSignature({ expected, secret, teamName, taskId, state, sequence, body }) {
  const normalized = expected?.startsWith('sha256=') ? expected.slice('sha256='.length) : expected;
  if (!normalized || !/^[a-fA-F0-9]{64}$/.test(normalized)) return false;
  const actual = signPush({ secret, teamName, taskId, state, sequence, body });
  return timingSafeEqual(Buffer.from(actual, 'hex'), Buffer.from(normalized, 'hex'));
}
