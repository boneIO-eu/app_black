/**
 * Section definitions for UISettings configuration editor.
 * Defines which sections require reload vs restart, icons, and other metadata.
 */

export interface SectionDefinition {
  name: string;
  icon: string;
  translationKey: string;
  /** Optional badge key (e.g. 'experimental') — shown next to section label. */
  badge?: string;
}

/**
 * Sections that only require reload (hot reload supported).
 * Changes to these sections can be applied without restarting the application.
 */
export const RELOAD_SECTIONS: SectionDefinition[] = [
  { name: 'areas', icon: '🏠', translationKey: 'sections.areas' },
  { name: 'local_inputs', icon: '📥', translationKey: 'sections.local_inputs' },
  { name: 'output', icon: '💡', translationKey: 'sections.output' },
  { name: 'output_group', icon: '🔗', translationKey: 'sections.output_group' },
  { name: 'cover', icon: '🚪', translationKey: 'sections.cover' },
  { name: 'modbus_devices', icon: '📱', translationKey: 'sections.modbus_devices' },
  { name: 'sensor', icon: '🌡️', translationKey: 'sections.sensor' },
  { name: 'adc', icon: '📊', translationKey: 'sections.adc' },
  { name: 'virtual_energy_sensor', icon: '⚡', translationKey: 'sections.virtual_energy_sensor' },
  { name: 'template', icon: '🧩', translationKey: 'sections.template' },
  { name: 'logger', icon: '📝', translationKey: 'sections.logger' },
  { name: 'oled', icon: '🖥️', translationKey: 'sections.oled' },
  { name: 'remote_devices', icon: '🌐', translationKey: 'sections.remote_devices' },
  { name: 'remote_inputs', icon: '🔌', translationKey: 'sections.remote_inputs' },
  { name: 'remote_outputs', icon: '📡', translationKey: 'sections.remote_outputs' },
];

/**
 * Sections that require full application restart.
 * Changes to these sections require restarting the application to take effect.
 */
export const RESTART_SECTIONS: SectionDefinition[] = [
  { name: 'boneio', icon: '🔧', translationKey: 'sections.boneio' },
  { name: 'mqtt', icon: '📡', translationKey: 'sections.mqtt' },
  { name: 'web', icon: '🌐', translationKey: 'sections.web' },
  { name: 'modbus', icon: '🔌', translationKey: 'sections.modbus' },
  { name: 'can', icon: '🔗', translationKey: 'sections.can' },
  { name: 'mcp23017', icon: '🔗', translationKey: 'sections.mcp23017' },
  { name: 'board_sensors', icon: '🔌', translationKey: 'sections.board_sensors' },
];

/**
 * All config sections combined.
 */
export const ALL_SECTIONS: SectionDefinition[] = [...RELOAD_SECTIONS, ...RESTART_SECTIONS];

/**
 * Sections that use ArrayTableWidget (array-based data).
 */
export const ARRAY_SECTIONS = [
  'local_inputs',
  'remote_inputs',
  'output',
  'output_group',
  'cover',
  'modbus_devices',
  'areas',
  'sensor',
  'virtual_energy_sensor',
  'remote_devices',
  'remote_outputs',
  'template',
  'adc',
  'board_sensors',
] as const;

/**
 * Composite sections that combine multiple YAML keys into one UI section.
 * The key is the virtual section name, the value is an array of actual YAML keys.
 */
export const COMPOSITE_SECTIONS: Record<string, string[]> = {
  board_sensors: ['lm75', 'ina219', 'mcp9808'],
  local_inputs: ['binary_sensor', 'event'],
};

export type ArraySectionType = typeof ARRAY_SECTIONS[number];

/**
 * Check if a section is an array section.
 */
export function isArraySection(sectionName: string): sectionName is ArraySectionType {
  return ARRAY_SECTIONS.includes(sectionName as ArraySectionType);
}

/**
 * Check if a section requires restart.
 */
export function requiresRestart(sectionName: string): boolean {
  return RESTART_SECTIONS.some(s => s.name === sectionName);
}

/**
 * Get section definition by name.
 */
export function getSectionDefinition(sectionName: string): SectionDefinition | undefined {
  return ALL_SECTIONS.find(s => s.name === sectionName);
}
