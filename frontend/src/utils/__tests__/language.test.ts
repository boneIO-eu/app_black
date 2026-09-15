import { describe, it, expect } from 'vitest';
import { FALLBACK_LANGUAGE, pickLanguage } from '../language';

const SUPPORTED = ['en', 'pl'];

describe('pickLanguage', () => {
  it('honours an earlier explicit choice over the browser', () => {
    expect(pickLanguage('pl', ['en-US', 'en'], SUPPORTED)).toBe('pl');
  });

  it('ignores a stored language we do not ship', () => {
    // Hand-edited or left over from a build that had more locales: taking it
    // at face value leaves the UI rendering raw translation keys.
    expect(pickLanguage('de', ['pl-PL'], SUPPORTED)).toBe('pl');
  });

  it('follows the browser when nothing was chosen yet', () => {
    expect(pickLanguage(null, ['pl-PL', 'pl'], SUPPORTED)).toBe('pl');
    expect(pickLanguage(undefined, ['en-GB'], SUPPORTED)).toBe('en');
  });

  it('matches a regional tag on its primary subtag', () => {
    expect(pickLanguage(null, ['PL-pl'], SUPPORTED)).toBe('pl');
  });

  it('respects the order of the browser preference list', () => {
    expect(pickLanguage(null, ['de-DE', 'pl', 'en'], SUPPORTED)).toBe('pl');
  });

  it('falls back to English for a language we do not ship', () => {
    expect(pickLanguage(null, ['de-DE', 'fr'], SUPPORTED)).toBe(FALLBACK_LANGUAGE);
  });

  it('falls back when the browser names no language at all', () => {
    expect(pickLanguage(null, [], SUPPORTED)).toBe(FALLBACK_LANGUAGE);
    expect(pickLanguage(null, [undefined], SUPPORTED)).toBe(FALLBACK_LANGUAGE);
  });
});
