/**
 * Public API for the expander module.
 *
 * BoneIO files MUST import only from this index — never reach into module internals.
 * This is the stable contract; internal restructuring of the module never breaks consumers.
 */

// Types
export type { OutputEntity, OutputKind, OutputType } from './types/output';
export type {
  McpEntry,
  McpAddress,
  ManagedExpanderId,
} from './types/mcp';
export type {
  ExpanderBoardType,
  ExpanderBoardDefinition,
  ExpanderOutputSlot,
  ExpanderOutputStats,
  ChipRole,
} from './types/expander';

// Constants
export {
  MCP_ADDRESS_OPTIONS,
  MANAGED_EXPANDER_IDS,
  DEFAULT_ADDRESSES,
  DEFAULT_ADDRESS_INTEGERS,
} from './constants/mcpAddresses';

// Helpers — pure functions
export {
  EXPANDER_OUTPUT_PREFIX,
  EXPANDER_BOARDS,
  isExpanderOutput,
  generateExpanderOutputEntries,
  detectExpanderBoardType,
  getOutputStats,
} from './helpers/expanderBoards';

export {
  getMcpIdOptions,
  getMcpPinOptions,
  hasMcpHardwareOverride,
} from './helpers/outputMcpUtils';

// Hooks (stateful + side-effects; consumable by alternative UI skins)
export {
  useExpanderManager,
  type UseExpanderManagerArgs,
  type UseExpanderManagerReturn,
  type ExpanderResult,
} from './hooks/useExpanderManager';

// Components (Presentational; safe to swap for alternative skins)
export { default as ExpanderManager } from './components/ExpanderManager';
