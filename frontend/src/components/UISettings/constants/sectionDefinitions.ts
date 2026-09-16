/**
 * Section definitions for the settings editor.
 *
 * Sections are grouped by the question they answer, not by where their data
 * lives — see SETTINGS_IA.md. The old split put the password boneIO connects
 * with in Settings and the broker's own accounts in System, because one is in
 * config.yaml and the other is not. Nobody asks that question; they ask how to
 * change a password.
 *
 * Three lists, because "which group is it in" and "what does saving it cost"
 * are different facts:
 *
 *   RELOAD_SECTIONS   config.yaml, applied without a restart
 *   RESTART_SECTIONS  config.yaml, needs the app restarted — carries the badge
 *   SYSTEM_SECTIONS   acts on the operating system, takes effect at once
 *
 * Only the group decides where an entry appears. The lists decide whether
 * `requiresRestart` is true, which is what the badge and the save banner read.
 */

export interface SectionDefinition {
  name: string;
  icon: string;
  translationKey: string;
  /** Optional badge key (e.g. 'experimental') — shown next to section label. */
  badge?: string;
  /** Which sidebar group this belongs to. */
  group?: SectionGroup;
}

export type SectionGroup =
  | 'device'
  | 'control'
  | 'connections'
  | 'services'
  | 'access'
  | 'maintenance'
  | 'advanced';

/**
 * Groups in the order they appear in the sidebar, outermost concern first:
 * what the controller is, what it drives, what it talks to, what runs on it,
 * who may reach it, keeping it running, and the sharp tools.
 */
export const SECTION_GROUPS: { name: SectionGroup; icon: string; translationKey: string }[] = [
  { name: 'device', icon: '🔧', translationKey: 'settings.group_device' },
  { name: 'control', icon: '💡', translationKey: 'settings.group_control' },
  { name: 'connections', icon: '🔌', translationKey: 'settings.group_connections' },
  { name: 'services', icon: '📦', translationKey: 'settings.group_services' },
  { name: 'access', icon: '🛡️', translationKey: 'settings.group_access' },
  { name: 'maintenance', icon: '🧰', translationKey: 'settings.group_maintenance' },
  { name: 'advanced', icon: '⚙️', translationKey: 'settings.group_advanced' },
];

/**
 * Sections that only require reload (hot reload supported).
 * Changes to these sections can be applied without restarting the application.
 */
export const RELOAD_SECTIONS: SectionDefinition[] = [
  { name: 'areas', icon: '🏠', translationKey: 'sections.areas', group: 'device' },
  { name: 'oled', icon: '🖥️', translationKey: 'sections.oled', group: 'device' },

  { name: 'local_inputs', icon: '📥', translationKey: 'sections.local_inputs', group: 'control' },
  { name: 'output', icon: '💡', translationKey: 'sections.output', group: 'control' },
  { name: 'output_group', icon: '🔗', translationKey: 'sections.output_group', group: 'control' },
  { name: 'cover', icon: '🚪', translationKey: 'sections.cover', group: 'control' },
  { name: 'sensor', icon: '🌡️', translationKey: 'sections.sensor', group: 'control' },
  { name: 'adc', icon: '📊', translationKey: 'sections.adc', group: 'control' },
  { name: 'virtual_energy_sensor', icon: '⚡', translationKey: 'sections.virtual_energy_sensor', group: 'control' },
  // Irrigation is a template platform, edited inside this section.
  { name: 'template', icon: '🧩', translationKey: 'sections.template', group: 'control' },
  { name: 'binding_matrix', icon: '📊', translationKey: 'sections.binding_matrix', group: 'control' },

  { name: 'modbus_devices', icon: '📱', translationKey: 'sections.modbus_devices', group: 'connections' },
  { name: 'remote_devices', icon: '🌐', translationKey: 'sections.remote_devices', group: 'connections' },
  { name: 'remote_inputs', icon: '🔌', translationKey: 'sections.remote_inputs', group: 'connections' },
  { name: 'remote_outputs', icon: '📡', translationKey: 'sections.remote_outputs', group: 'connections' },

  { name: 'security', icon: '🛡️', translationKey: 'sections.security', group: 'access' },
  { name: 'accounts', icon: '👥', translationKey: 'sections.accounts', group: 'access' },

  { name: 'logger', icon: '📝', translationKey: 'sections.logger', group: 'advanced' },
  // Generates a Home Assistant dashboard from the configured entities. It was
  // a tab on the Tools page; it is about an integration, not about hardware.
  { name: 'ha_dashboard', icon: '📤', translationKey: 'sections.ha_dashboard', group: 'connections' },
  { name: 'yaml_editor', icon: '📄', translationKey: 'sections.yaml_editor', group: 'advanced' },
];

/**
 * Sections that require full application restart.
 * Changes to these sections require restarting the application to take effect.
 */
export const RESTART_SECTIONS: SectionDefinition[] = [
  { name: 'boneio', icon: '🔧', translationKey: 'sections.boneio', group: 'device', badge: 'restart' },
  { name: 'board_sensors', icon: '🔌', translationKey: 'sections.board_sensors', group: 'device', badge: 'restart' },

  // MQTT and Loxone UDP together — the section is about protocols, not one broker.
  { name: 'mqtt', icon: '📡', translationKey: 'sections.mqtt', group: 'connections', badge: 'restart' },
  { name: 'modbus', icon: '🔌', translationKey: 'sections.modbus', group: 'connections', badge: 'restart' },
  { name: 'can', icon: '🔗', translationKey: 'sections.can', group: 'connections', badge: 'restart' },

  { name: 'web', icon: '🌐', translationKey: 'sections.web', group: 'access', badge: 'restart' },

  // Expander wiring: correct to configure, easy to break, and irrelevant to
  // anyone who has not added one. Advanced rather than Device.
  { name: 'mcp23017', icon: '🔗', translationKey: 'sections.mcp23017', group: 'advanced', badge: 'restart' },
];

/**
 * Sections that act on the operating system rather than on config.yaml.
 *
 * They moved here from the System page. Nothing about them is saved as YAML,
 * so they have no save button, no restore and no preview — the editor renders
 * them through the standalone-section registry.
 */
export const SYSTEM_SECTIONS: SectionDefinition[] = [
  { name: 'hostname', icon: '🏷️', translationKey: 'sections.hostname', group: 'device' },
  { name: 'timezone', icon: '🕓', translationKey: 'sections.timezone', group: 'device' },

  // The broker running on this controller, which is not the same thing as the
  // MQTT connection under Connections. See SETTINGS_IA.md.
  { name: 'mosquitto', icon: '📨', translationKey: 'sections.mosquitto', group: 'services' },
  { name: 'nodered_service', icon: '🔀', translationKey: 'sections.nodered_service', group: 'services' },
  // Deliberately absent: the certificate panel (SslSection) is marked `hidden`
  // in its own markup and has been since a February refactor, so it never
  // rendered on the System page either. Its /api/caddy endpoints still work,
  // so this is a UI decision someone made, not dead code — and cloud
  // registration under Access is the supported path to a trusted certificate.
  // Listing it here would ship a panel that was taken out of sight on purpose.

  { name: 'update', icon: '⬆️', translationKey: 'sections.update', group: 'maintenance' },
  { name: 'backup', icon: '💾', translationKey: 'sections.backup', group: 'maintenance' },
  { name: 'migrations', icon: '🧬', translationKey: 'sections.migrations', group: 'maintenance' },
  { name: 'power', icon: '⏻', translationKey: 'sections.power', group: 'maintenance' },
  { name: 'device_tools', icon: '🔬', translationKey: 'sections.device_tools', group: 'maintenance' },
  { name: 'hardware_errors', icon: '⚠️', translationKey: 'sections.hardware_errors', group: 'maintenance' },
  { name: 'factory_reset', icon: '♻️', translationKey: 'sections.factory_reset', group: 'maintenance' },
];

/**
 * All config sections combined.
 */
export const ALL_SECTIONS: SectionDefinition[] = [
  ...RELOAD_SECTIONS,
  ...RESTART_SECTIONS,
  ...SYSTEM_SECTIONS,
];

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
  board_sensors: ['lm75', 'ina219', 'ina226', 'mcp9808'],
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
