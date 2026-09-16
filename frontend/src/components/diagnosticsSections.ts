/**
 * What Diagnostics can show, in the order it is offered.
 *
 * Its own file for the same reason the settings tree has one: whether a
 * section exists, and which group it belongs to, is a fact about the section
 * rather than about the component that draws the list.
 */
export interface DiagnosticsSectionDef {
  name: string;
  icon: string;
  /** Translation key for the label. */
  titleKey: string;
  /** Translation key for the one line under the page title. */
  descriptionKey: string;
  /** Which sidebar group this belongs to. */
  group: DiagnosticsGroup;
  /** Needs a board with a CAN transceiver. */
  requiresCan?: boolean;
}

/**
 * What Diagnostics can show, in the order it is offered.
 *
 * The bus scans used to be a tab strip inside a strip inside the page. They
 * are places you go, the same as a settings section, so they are entries in a
 * sidebar now and the nesting is gone.
 */
export type DiagnosticsGroup = 'log' | 'buses';

/**
 * Groups in the order they appear.
 *
 * Headings rather than accordions: six entries fit without folding, and the
 * settings tree only collapses because it has forty.
 */
export const DIAGNOSTICS_GROUPS: { name: DiagnosticsGroup; icon: string; titleKey: string }[] = [
  { name: 'log', icon: '📜', titleKey: 'diagnostics.group_log' },
  { name: 'buses', icon: '🔍', titleKey: 'diagnostics.group_buses' },
];

export const DIAGNOSTICS_SECTIONS: DiagnosticsSectionDef[] = [
  { name: 'log', icon: '📜', titleKey: 'diagnostics.section_log', descriptionKey: 'diagnostics.section_log_desc', group: 'log' },
  { name: 'support', icon: '🛟', titleKey: 'diagnostics.section_support', descriptionKey: 'diagnostics.section_support_desc', group: 'log' },

  { name: 'modbus', icon: '🔌', titleKey: 'diagnostics.section_modbus', descriptionKey: 'diagnostics.section_modbus_desc', group: 'buses' },
  { name: 'i2c', icon: '🧩', titleKey: 'diagnostics.section_i2c', descriptionKey: 'diagnostics.section_i2c_desc', group: 'buses' },
  { name: 'can_network', icon: '⚡', titleKey: 'diagnostics.section_can_network', descriptionKey: 'diagnostics.section_can_network_desc', group: 'buses', requiresCan: true },
  { name: 'can_sniffer', icon: '📡', titleKey: 'diagnostics.section_can_sniffer', descriptionKey: 'diagnostics.section_can_sniffer_desc', group: 'buses', requiresCan: true },
];

export const DEFAULT_DIAGNOSTICS_SECTION = 'log';
