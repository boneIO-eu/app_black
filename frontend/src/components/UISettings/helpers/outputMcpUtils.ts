import { MANAGED_EXPANDER_IDS } from '../Mcp23017Form';

const MCP_PIN_COUNT = 16;

export function getMcpIdOptions(
  mcp23017Config: Array<{ id?: string }> | undefined,
  currentMcpId?: string
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

export function hasMcpHardwareOverride(data: {
  mcp_id?: string;
  pin?: number | string;
}): boolean {
  return Boolean(data.mcp_id);
}
