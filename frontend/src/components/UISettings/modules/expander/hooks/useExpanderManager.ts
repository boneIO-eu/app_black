/**
 * Expander lifecycle hook — state + fetch + handlers.
 *
 * Encapsulates the entire add/remove workflow for an expansion board so the
 * presentation component (`<ExpanderManager />`) is purely a renderer. An
 * alternative re-skinned component can consume this hook unchanged.
 */
import { useCallback, useMemo, useState } from 'react';
import axios from '@/api/axios';

import { DEFAULT_ADDRESSES } from '../constants/mcpAddresses';
import {
  detectExpanderBoardType,
  EXPANDER_BOARDS,
  generateExpanderOutputEntries,
  isExpanderOutput,
} from '../helpers/expanderBoards';
import type { McpAddress, ManagedExpanderId } from '../types/mcp';
import type { OutputEntity } from '../types/output';
import type { ExpanderBoardType } from '../types/expander';

export interface ExpanderResult {
  status: 'success' | 'error';
  message?: string;
}

export interface UseExpanderManagerArgs {
  allOutputs: OutputEntity[];
  allEvents: Array<{ name?: string; boneio_input?: string; actions?: unknown }>;
  allBinarySensors: Array<{ name?: string; boneio_input?: string; actions?: unknown }>;
}

export interface UseExpanderManagerReturn {
  // Computed
  hasExpander: boolean;
  exOutputs: OutputEntity[];
  detectedBoardType: ExpanderBoardType | null;
  // Add form state
  isAddOpen: boolean;
  boardType: ExpanderBoardType;
  addresses: Record<Extract<ManagedExpanderId, 'expander_left' | 'expander_right'>, McpAddress>;
  // Remove flow state
  isRemoveConfirmOpen: boolean;
  blockingInputs: string[];
  // Shared state
  isBusy: boolean;
  result: ExpanderResult | null;
  // Handlers
  openAdd: () => void;
  closeAdd: () => void;
  setBoardType: (type: ExpanderBoardType) => void;
  setAddress: (id: 'expander_left' | 'expander_right', value: McpAddress) => void;
  submitAdd: () => Promise<void>;
  openRemoveConfirm: () => void;
  closeRemoveConfirm: () => void;
  submitRemove: () => Promise<void>;
  dismissBlocking: () => void;
}

/**
 * Trigger a backend restart and reload the page once it's back.
 * Server-side restart is fire-and-forget (the request will error mid-flight).
 */
async function restartAndReload(): Promise<void> {
  try {
    await axios.post('/api/restart');
  } catch {
    // expected — server is restarting
  }
  setTimeout(() => window.location.reload(), 4000);
}

/**
 * Find input/event names whose actions reference any of the given expander IDs.
 * Used to warn the user before removing an expander that would orphan actions.
 */
function findInputsBlockingRemoval(
  exOutputs: OutputEntity[],
  allEvents: UseExpanderManagerArgs['allEvents'],
  allBinarySensors: UseExpanderManagerArgs['allBinarySensors'],
): string[] {
  const exIds = new Set<string>(
    exOutputs.flatMap((o) => [o.id, o.boneio_output].filter((v): v is string => !!v)),
  );
  const blocked: string[] = [];
  const check = (actions: unknown, name: string) => {
    if (!actions || typeof actions !== 'object') return;
    for (const list of Object.values(actions as Record<string, unknown>)) {
      if (!Array.isArray(list)) continue;
      for (const action of list) {
        const a = action as { pin?: string; boneio_output?: string };
        if ((a.pin && exIds.has(a.pin)) || (a.boneio_output && exIds.has(a.boneio_output))) {
          if (!blocked.includes(name)) blocked.push(name);
        }
      }
    }
  };
  allEvents.forEach((e) => check(e.actions, e.name || e.boneio_input || 'event'));
  allBinarySensors.forEach((s) => check(s.actions, s.name || s.boneio_input || 'sensor'));
  return blocked;
}

export function useExpanderManager(args: UseExpanderManagerArgs): UseExpanderManagerReturn {
  const { allOutputs, allEvents, allBinarySensors } = args;

  const [isAddOpen, setIsAddOpen] = useState(false);
  const [boardType, setBoardType] = useState<ExpanderBoardType>('32x10A');
  const [addresses, setAddresses] = useState<UseExpanderManagerReturn['addresses']>({
    expander_left: DEFAULT_ADDRESSES.expander_left,
    expander_right: DEFAULT_ADDRESSES.expander_right,
  });
  const [isBusy, setIsBusy] = useState(false);
  const [isRemoveConfirmOpen, setIsRemoveConfirmOpen] = useState(false);
  const [result, setResult] = useState<ExpanderResult | null>(null);
  const [blockingInputs, setBlockingInputs] = useState<string[]>([]);

  const exOutputs = useMemo(
    () => allOutputs.filter(isExpanderOutput),
    [allOutputs],
  );
  const hasExpander = exOutputs.length > 0;
  const detectedBoardType = useMemo(
    () => detectExpanderBoardType(exOutputs),
    [exOutputs],
  );

  const setAddress = useCallback(
    (id: 'expander_left' | 'expander_right', value: McpAddress) => {
      setAddresses((prev) => ({ ...prev, [id]: value }));
    },
    [],
  );

  const submitAdd = useCallback(async () => {
    setIsBusy(true);
    setResult(null);
    try {
      const outputs = generateExpanderOutputEntries(boardType);
      const res = await axios.post('/api/config/expander', {
        board_type: boardType,
        outputs,
        expander_left_address: addresses.expander_left,
        expander_right_address: addresses.expander_right,
      });
      setResult({ status: 'success', message: res.data.expansion_file });
      setIsAddOpen(false);
      await restartAndReload();
    } catch (e) {
      const err = e as { response?: { data?: { detail?: string } } };
      setResult({ status: 'error', message: err?.response?.data?.detail || String(e) });
      setIsBusy(false);
    }
  }, [boardType, addresses]);

  const submitRemove = useCallback(async () => {
    const blocking = findInputsBlockingRemoval(exOutputs, allEvents, allBinarySensors);
    if (blocking.length > 0) {
      setBlockingInputs(blocking);
      setIsRemoveConfirmOpen(false);
      return;
    }
    setIsBusy(true);
    setIsRemoveConfirmOpen(false);
    setResult(null);
    try {
      await axios.post('/api/config/expander/remove', { board_type: detectedBoardType });
      setResult({ status: 'success' });
      await restartAndReload();
    } catch (e) {
      const err = e as { response?: { data?: { detail?: string } } };
      setResult({ status: 'error', message: err?.response?.data?.detail || String(e) });
      setIsBusy(false);
    }
  }, [exOutputs, allEvents, allBinarySensors, detectedBoardType]);

  return {
    hasExpander,
    exOutputs,
    detectedBoardType,
    isAddOpen,
    boardType,
    addresses,
    isRemoveConfirmOpen,
    blockingInputs,
    isBusy,
    result,
    openAdd: useCallback(() => setIsAddOpen(true), []),
    closeAdd: useCallback(() => setIsAddOpen(false), []),
    setBoardType,
    setAddress,
    submitAdd,
    openRemoveConfirm: useCallback(() => setIsRemoveConfirmOpen(true), []),
    closeRemoveConfirm: useCallback(() => setIsRemoveConfirmOpen(false), []),
    submitRemove,
    dismissBlocking: useCallback(() => setBlockingInputs([]), []),
  };
}

// Re-export EXPANDER_BOARDS so consumers (component) can render board list
// without crossing back into helpers — keeps presentation isolated from helpers.
export { EXPANDER_BOARDS };
