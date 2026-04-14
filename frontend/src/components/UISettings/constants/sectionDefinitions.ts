/**
 * Section definitions for UISettings configuration editor.
 * Defines which sections require reload vs restart, icons, and other metadata.
 */

export interface SectionDefinition {
  name: string;
  icon: string;
  translationKey: string;
}

/**
 * Sections that only require reload (hot reload supported).
 * Changes to these sections can be applied without restarting the application.
 */
export const RELOAD_SECTIONS: SectionDefinition[] = [
  { name: 'areas', icon: '🏠', translationKey: 'sections.areas' },
  { name: 'binary_sensor', icon: '🔘', translationKey: 'sections.binary_sensor' },
  { name: 'event', icon: '⚡', translationKey: 'sections.event' },
  { name: 'output', icon: '💡', translationKey: 'sections.output' },
  { name: 'output_group', icon: '🔗', translationKey: 'sections.output_group' },
  { name: 'cover', icon: '🚪', translationKey: 'sections.cover' },
  { name: 'remote_devices', icon: '🌐', translationKey: 'sections.remote_devices' },
  { name: 'modbus_devices', icon: '📱', translationKey: 'sections.modbus_devices' },
  { name: 'sensor', icon: '🌡️', translationKey: 'sections.sensor' },
  { name: 'adc', icon: '📊', translationKey: 'sections.adc' },
  { name: 'virtual_energy_sensor', icon: '⚡', translationKey: 'sections.virtual_energy_sensor' },
  { name: 'template', icon: '🧩', translationKey: 'sections.template' },
  { name: 'logger', icon: '📝', translationKey: 'sections.logger' },
  { name: 'oled', icon: '🖥️', translationKey: 'sections.oled' },
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
  'event',
  'binary_sensor',
  'output',
  'output_group',
  'cover',
  'modbus_devices',
  'areas',
  'sensor',
  'virtual_energy_sensor',
  'remote_devices',
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
