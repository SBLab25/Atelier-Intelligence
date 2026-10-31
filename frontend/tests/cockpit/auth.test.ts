import { describe, expect, it } from 'vitest';
import { validateEmail, validatePassword, formatSessionSummary } from '@/cockpit/utils/auth';

describe('auth utilities', () => {
  it('validateEmail checks standard email patterns', () => {
    expect(validateEmail('elena@atelier.intelligence')).toBe(true);
    expect(validateEmail('user.name+tag@domain.co')).toBe(true);
    expect(validateEmail('invalid-email')).toBe(false);
    expect(validateEmail('')).toBe(false);
    expect(validateEmail('user@domain')).toBe(false);
  });

  it('validatePassword validates minimum length requirements', () => {
    expect(validatePassword('123456').valid).toBe(true);
    expect(validatePassword('secure-passkey-2026').valid).toBe(true);
    expect(validatePassword('123').valid).toBe(false);
    expect(validatePassword('').valid).toBe(false);
  });

  it('formatSessionSummary formats session hours and minutes', () => {
    const sum1 = formatSessionSummary(9300); // 2h 35m
    expect(sum1.formatted).toBe('2h 35m');
    expect(sum1.hours).toBe(2);
    expect(sum1.minutes).toBe(35);
  });
});
