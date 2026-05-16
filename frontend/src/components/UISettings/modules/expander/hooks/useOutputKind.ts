/**
 * Derive ``'board' | 'expander'`` from the currently-edited output item.
 *
 * Replaces a manual ``useState`` + ``setOutputKind`` pattern that was prone to
 * desync. The kind is purely a function of the item shape, so memoization is
 * enough — there's no independent state to keep.
 */
import { useMemo } from 'react';

import { isExpanderOutput } from '../helpers/expanderBoards';
import type { OutputEntity, OutputKind } from '../types/output';

export function useOutputKind(item: Partial<OutputEntity> | null | undefined): OutputKind {
  return useMemo(() => (isExpanderOutput(item) ? 'expander' : 'board'), [item]);
}
