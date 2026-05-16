import type { McpAddress, ManagedExpanderId } from '../types/mcp';

export const MCP_ADDRESS_OPTIONS: readonly McpAddress[] = [
  '0x20', '0x21', '0x22', '0x23', '0x24', '0x25', '0x26', '0x27',
] as const;

export const MANAGED_EXPANDER_IDS: readonly ManagedExpanderId[] = [
  'mcp_left', 'mcp_right', 'expander_left', 'expander_right',
] as const;

export const DEFAULT_ADDRESSES: Record<ManagedExpanderId, McpAddress> = {
  mcp_left: '0x21',
  mcp_right: '0x20',
  expander_left: '0x23',
  expander_right: '0x22',
};

export const DEFAULT_ADDRESS_INTEGERS: Record<ManagedExpanderId, number> = {
  mcp_left: 0x21,
  mcp_right: 0x20,
  expander_left: 0x23,
  expander_right: 0x22,
};
