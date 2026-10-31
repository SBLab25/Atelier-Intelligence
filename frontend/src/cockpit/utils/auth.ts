/**
 * Pure authentication helper functions and validation logic
 */

export interface AuthSession {
  user: {
    id: string;
    name: string;
    email: string;
    role: string;
    avatar: string;
    status: 'In Focus' | 'Available' | 'In Meeting';
  };
  loginTime: number;
  sessionDurationSeconds: number;
  uncommittedSyncs: number;
}

export function validateEmail(email: string): boolean {
  if (!email || typeof email !== 'string') return false;
  const regex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  return regex.test(email.trim());
}

export function validatePassword(password: string): { valid: boolean; reason?: string } {
  if (!password || password.length < 6) {
    return { valid: false, reason: 'Password must be at least 6 characters' };
  }
  return { valid: true };
}

export function formatSessionSummary(seconds: number): {
  formatted: string;
  hours: number;
  minutes: number;
} {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const formatted = hours > 0 ? `${hours}h ${minutes}m` : `${minutes}m`;
  return { formatted, hours, minutes };
}
