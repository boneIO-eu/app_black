/**
 * Tests for the first-run wizard gate.
 *
 * Regression cover for a bug that appeared twice while building the wizard:
 * gating on the raw `needs_onboarding` flag unmounted the wizard the moment it
 * created the account — once immediately, via an explicit refetch, and once
 * ~30s later via AppInitProvider's periodic poll — leaving the import and
 * summary steps unreachable.
 */
import { describe, it, expect } from 'vitest';

import { latchNeedsOnboarding } from '../AppInitContext';

describe('latchNeedsOnboarding', () => {
  it('shows the wizard on an unprovisioned device', () => {
    expect(latchNeedsOnboarding(false, { needs_onboarding: true })).toBe(true);
  });

  it('stays out of the way on a provisioned device', () => {
    expect(latchNeedsOnboarding(false, { needs_onboarding: false })).toBe(false);
  });

  it('keeps the wizard up after the account is created', () => {
    // The poll right after POST /api/onboarding/admin reports provisioned.
    expect(latchNeedsOnboarding(true, { needs_onboarding: false })).toBe(true);
  });

  it('survives any number of later polls', () => {
    let latched = latchNeedsOnboarding(false, { needs_onboarding: true });
    for (let i = 0; i < 10; i++) {
      latched = latchNeedsOnboarding(latched, { needs_onboarding: false });
    }
    expect(latched).toBe(true);
  });

  it('treats a missing or malformed payload as "no wizard"', () => {
    expect(latchNeedsOnboarding(false, null)).toBe(false);
    expect(latchNeedsOnboarding(false, undefined)).toBe(false);
    expect(latchNeedsOnboarding(false, {})).toBe(false);
  });

  it('does not let a failed poll drop a wizard already on screen', () => {
    expect(latchNeedsOnboarding(true, null)).toBe(true);
  });
});
