// @vitest-environment jsdom
/**
 * "Run now" on the schedules table follows the action bar's dirty flag. It
 * used to compare the section itself with raw JSON.stringify, so the same
 * entries with their keys in another order counted as a draft there while
 * the bar said nothing had changed.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import type { ConfigSection } from '../types/section';

vi.mock('@/hooks/useTranslation', () => ({ useTranslation: () => ({ t: (k: string) => k, language: 'en' }) }));
vi.mock('../../../hooks/useTranslation', () => ({ useTranslation: () => ({ t: (k: string) => k, language: 'en' }) }));
vi.mock('@/api/axios', () => ({
  default: {
    get: vi.fn(async () => ({ data: { schedules: [{ id: 'x', enabled: true }] } })),
    post: vi.fn(),
  },
}));

const { default: SectionContent } = await import('../components/SectionContent');

const saved = { name: 'X', trigger: { type: 'sun', event: 'sunset' }, actions: [] };
const reordered = { actions: [], trigger: { event: 'sunset', type: 'sun' }, name: 'X' };
const section = { name: 'schedule', schema: {}, normalizedSchema: {}, uiSchema: {}, data: [] } as unknown as ConfigSection;

const renderSchedules = (isDirty: boolean) =>
  render(
    <SectionContent
      activeSection="schedule"
      activeSectionData={section}
      formData={{ schedule: [reordered] }}
      originalData={{ schedule: [saved] }}
      isDirty={isDirty}
      schemaLoaded
      onSectionChange={() => {}}
      onSaveSection={async () => {}}
    />,
  );

describe('schedules table and the dirty flag', () => {
  afterEach(cleanup);

  it('lets a schedule run when the bar says nothing changed', async () => {
    renderSchedules(false);
    await waitFor(() => expect(screen.getAllByTitle('schedule.run_now').length).toBeGreaterThan(0));
  });

  it('holds it back while the bar says there is a draft', async () => {
    renderSchedules(true);
    await waitFor(() => expect(screen.getAllByTitle('schedule.run_needs_save').length).toBeGreaterThan(0));
  });
});
