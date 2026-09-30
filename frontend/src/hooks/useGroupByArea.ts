import { useState } from 'react';

/**
 * Whether a dashboard groups its entities by area, remembered per view.
 *
 * Off whenever no area is configured, whatever was remembered: there is
 * nothing to group by, and the toggle is not shown either.
 */
export function useGroupByArea(storageKey: string, hasAreas: boolean): [boolean, (on: boolean) => void] {
  const [on, setOn] = useState(() => {
    try {
      return localStorage.getItem(storageKey) === 'true';
    } catch {
      return false;
    }
  });

  const set = (value: boolean) => {
    setOn(value);
    try {
      localStorage.setItem(storageKey, String(value));
    } catch {
      // Private mode: the choice lasts until the page is closed.
    }
  };

  return [on && hasAreas, set];
}
