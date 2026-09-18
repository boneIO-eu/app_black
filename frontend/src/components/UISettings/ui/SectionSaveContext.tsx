import { createContext, useContext, useEffect, useRef } from 'react';
import type { SettingsPageWidth } from './SettingsPage';

/**
 * How a hand-written settings page hands its save to the shell.
 *
 * Schema-driven sections are committed by UISettings itself, which knows what
 * is dirty and owns the action bar at the bottom of the pane. The pages moved
 * in from the old System screen do not go through that machinery — they hold
 * their own state and call their own endpoint — so they used to close with a
 * button in the card footer instead. Two kinds of settings page, two places to
 * look for "save", which is the thing the action bar exists to prevent.
 *
 * So these pages register their save instead of drawing it. The shell renders
 * the same bar in the same place it renders every other one, and the page
 * keeps its own state and its own endpoint.
 *
 * Only for a save that commits the whole section. A button that acts on one
 * card — change this broker's password, download this backup, reboot — stays
 * in that card's footer, because it belongs to the card and not to the page.
 */
export interface SectionSaveRegistration {
  /** There are edits waiting to be written. */
  dirty: boolean;
  /** The save is in flight. */
  saving: boolean;
  /** Refuse the save even while dirty — a field failed validation. */
  disabled: boolean;
  /** Overrides the generic "Save" when the section has a better verb. */
  label?: string;
  /** The page's own column, so the bar lines up with its cards. */
  width?: SettingsPageWidth;
  onSave: () => void;
}

/**
 * Set by the shell. The default is a no-op so a section can be rendered on
 * its own — in a test, or in a story — without the provider.
 */
export const SectionSaveContext = createContext<
  (registration: SectionSaveRegistration | null) => void
>(() => {});

export interface SectionSaveOptions {
  dirty: boolean;
  saving?: boolean;
  disabled?: boolean;
  label?: string;
  width?: SettingsPageWidth;
}

/**
 * Publish this section's save to the shell's action bar.
 *
 * Pass `null` to publish nothing — for a page that only sometimes has
 * something to commit. The registration is withdrawn on unmount, so changing
 * section cannot leave a bar behind that saves the page you just left.
 */
export function useSectionSave(
  options: SectionSaveOptions | null,
  onSave: () => void,
): void {
  const register = useContext(SectionSaveContext);

  // The handler closes over the page's current state, so it is a new function
  // on every render. Registering it directly would re-register — and re-render
  // the shell — on every keystroke; behind a ref the registration below
  // depends only on values that actually change what the bar looks like.
  const handler = useRef(onSave);
  useEffect(() => {
    handler.current = onSave;
  });

  const enabled = options !== null;
  const dirty = options?.dirty ?? false;
  const saving = options?.saving ?? false;
  const disabled = options?.disabled ?? false;
  const label = options?.label;
  const width = options?.width;

  useEffect(() => {
    if (!enabled) return;
    register({
      dirty,
      saving,
      disabled,
      label,
      width,
      onSave: () => handler.current(),
    });
    return () => register(null);
  }, [register, enabled, dirty, saving, disabled, label, width]);
}
