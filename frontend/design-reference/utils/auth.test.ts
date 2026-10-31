import test from 'node:test';
import assert from 'node:assert/strict';
import { validateEmail, validatePassword, formatSessionSummary } from './auth';

test('validateEmail checks standard email patterns', () => {
  assert.equal(validateEmail('elena@atelier.intelligence'), true);
  assert.equal(validateEmail('user.name+tag@domain.co'), true);
  assert.equal(validateEmail('invalid-email'), false);
  assert.equal(validateEmail(''), false);
  assert.equal(validateEmail('user@domain'), false);
});

test('validatePassword validates minimum length requirements', () => {
  assert.equal(validatePassword('123456').valid, true);
  assert.equal(validatePassword('secure-passkey-2026').valid, true);
  assert.equal(validatePassword('123').valid, false);
  assert.equal(validatePassword('').valid, false);
});

test('formatSessionSummary formats session hours and minutes', () => {
  const sum1 = formatSessionSummary(9300); // 2h 35m
  assert.equal(sum1.formatted, '2h 35m');
  assert.equal(sum1.hours, 2);
  assert.equal(sum1.minutes, 35);

  const sum2 = formatSessionSummary(1200); // 20m
  assert.equal(sum2.formatted, '20m');
  assert.equal(sum2.hours, 0);
  assert.equal(sum2.minutes, 20);
});
