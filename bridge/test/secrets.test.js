import test from 'node:test';
import assert from 'node:assert/strict';
import { parseDotEnv } from '../src/secrets.js';

test('parseDotEnv reads quoted and unquoted values', () => {
  assert.deepEqual(parseDotEnv("A=one\nB='two two'\nC=\"three\\nlines\"\n# nope\n"), {
    A: 'one',
    B: 'two two',
    C: 'three\nlines',
  });
});
