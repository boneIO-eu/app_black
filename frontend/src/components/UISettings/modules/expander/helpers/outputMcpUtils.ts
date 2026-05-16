import { MANAGED_EXPANDER_IDS } from '../constants/mcpAddresses';
import type { OutputEntity } from '../types/output';

const MCP_PIN_COUNT = 16;

/**
 * Accepts any object exposing an `id` field — both full McpEntry rows from config
 * and partial schemas (e.g. when caller only knows ids).
 */
type McpIdSource = { id?: string };

export function getMcpIdOptions(
  mcp23017Config: McpIdSource[] | undefined,
  currentMcpId?: string,
): string[] {
  const fromConfig = (mcp23017Config ?? [])
    .map((entry) => entry?.id)
    .filter((id): id is string => typeof id === 'string' && id.length > 0);

  const options = [...new Set([...MANAGED_EXPANDER_IDS, ...fromConfig])];

  if (currentMcpId && !options.includes(currentMcpId)) {
    options.push(currentMcpId);
  }

  return options;
}

export function getMcpPinOptions(): number[] {
  return Array.from({ length: MCP_PIN_COUNT }, (_, index) => index);
}

export function hasMcpHardwareOverride(data: Pick<OutputEntity, 'mcp_id' | 'pin'>): boolean {
  return Boolean(data.mcp_id);
}
