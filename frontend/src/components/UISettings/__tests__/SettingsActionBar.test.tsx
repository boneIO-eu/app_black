// @vitest-environment jsdom
/**
 * A clean section's "unsaved changes" label is hidden, not just transparent:
 * at opacity 0 it stayed in innerText, and anything reading the page as text
 * reported unsaved changes on a section nobody had touched.
 */
import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { SettingsActionBar } from '../ui/SettingsActionBar';

const labels = { save: 'Save', restore: 'Restore', unsaved: 'Unsaved changes' };

describe('SettingsActionBar', () => {
  afterEach(cleanup);

  it('hides the unsaved label on a clean section', () => {
    render(<SettingsActionBar dirty={false} onSave={() => {}} labels={labels} />);
    expect(screen.getByText('Unsaved changes').parentElement!.className).toContain('invisible');
    expect(screen.getByRole('button', { name: 'Save' })).toHaveProperty('disabled', true);
  });

  it('shows it once the section is dirty', () => {
    render(<SettingsActionBar dirty onSave={() => {}} labels={labels} />);
    expect(screen.getByText('Unsaved changes').parentElement!.className).not.toContain('invisible');
  });
});
