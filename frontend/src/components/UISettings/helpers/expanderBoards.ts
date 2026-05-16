/**
 * @deprecated Import from `modules/expander` instead. This shim exists for backwards
 * compatibility with boneIO upstream files and will be removed once all consumers migrate.
 */
export {
  EXPANDER_OUTPUT_PREFIX,
  EXPANDER_BOARDS,
  isExpanderOutput,
  generateExpanderOutputEntries,
  detectExpanderBoardType,
  getOutputStats,
} from '../modules/expander/helpers/expanderBoards';

export type {
  ExpanderBoardType,
  ExpanderBoardDefinition,
  ExpanderOutputSlot,
  ChipRole,
} from '../modules/expander/types/expander';
