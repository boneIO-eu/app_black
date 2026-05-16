/**
 * MCP hardware override controller — state + handlers.
 *
 * Manages the "Advanced → Hardware (mcp_id/pin)" override section that lets a
 * user route a board output to an arbitrary MCP chip+pin. For expander outputs
 * (EX_*), the override is auto-populated and locked when editing existing entries.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';

import {
  getMcpIdOptions,
  getMcpPinOptions,
  hasMcpHardwareOverride,
} from '../helpers/outputMcpUtils';
import { isExpanderOutput } from '../helpers/expanderBoards';
import type { OutputEntity } from '../types/output';

export const MCP_DEFAULT_VALUE = '_board_default_';

export interface UseMcpHardwareArgs {
  data: OutputEntity;
  mcp23017?: Array<{ id?: string }>;
  isNew?: boolean;
  onChange: (data: OutputEntity) => void;
}

export interface UseMcpHardwareReturn {
  mcpIdOptions: string[];
  pinOptions: number[];
  hasOverride: boolean;
  isExpanderOutput: boolean;
  expanded: boolean;
  pinValue: string;
  toggle: () => void;
  setMcpId: (value: string) => void;
  setPin: (value: string) => void;
}

function normalizePinForUpdate(pin: OutputEntity['pin']): number {
  if (pin === undefined || pin === null || pin === '') return 0;
  return typeof pin === 'number' ? pin : parseInt(String(pin), 10);
}

function clearOverride(data: OutputEntity): OutputEntity {
  const next = { ...data };
  delete next.kind;
  delete next.mcp_id;
  delete next.pin;
  return next;
}

export function useMcpHardware(args: UseMcpHardwareArgs): UseMcpHardwareReturn {
  const { data, mcp23017, onChange } = args;

  const hasOverride = hasMcpHardwareOverride(data);
  const isExpander = isExpanderOutput(data);

  const [expanded, setExpanded] = useState(hasOverride);

  // Auto-expand when boneio_output flips to EX_* (auto-fill sets mcp_id/pin)
  useEffect(() => {
    if (isExpander && !expanded) {
      setExpanded(true);
    }
    // Intentionally depend on mcp_id to react to auto-fill mutations
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isExpander, data.mcp_id]);

  const mcpIdOptions = useMemo(
    () => getMcpIdOptions(mcp23017, data.mcp_id),
    [mcp23017, data.mcp_id],
  );
  const pinOptions = useMemo(() => getMcpPinOptions(), []);
  const pinValue = data.pin !== undefined && data.pin !== null && data.pin !== ''
    ? String(data.pin)
    : '0';

  const toggle = useCallback(() => {
    if (expanded) {
      onChange(clearOverride(data));
    }
    setExpanded(!expanded);
  }, [expanded, data, onChange]);

  const setMcpId = useCallback((value: string) => {
    if (value === MCP_DEFAULT_VALUE) {
      onChange(clearOverride(data));
      setExpanded(false);
      return;
    }
    onChange({
      ...data,
      kind: 'mcp',
      mcp_id: value,
      pin: normalizePinForUpdate(data.pin),
    });
  }, [data, onChange]);

  const setPin = useCallback((value: string) => {
    if (!data.mcp_id) return;
    onChange({
      ...data,
      kind: 'mcp',
      mcp_id: data.mcp_id,
      pin: parseInt(value, 10),
    });
  }, [data, onChange]);

  return {
    mcpIdOptions,
    pinOptions,
    hasOverride,
    isExpanderOutput: isExpander,
    expanded,
    pinValue,
    toggle,
    setMcpId,
    setPin,
  };
}
