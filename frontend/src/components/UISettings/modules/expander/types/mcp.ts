export type McpAddress = `0x2${0 | 1 | 2 | 3 | 4 | 5 | 6 | 7}`;
export type ManagedExpanderId = 'mcp_left' | 'mcp_right' | 'expander_left' | 'expander_right';

export interface McpEntry {
  id: string;
  address: McpAddress | string | number;
  init_sleep?: string | number;
}
