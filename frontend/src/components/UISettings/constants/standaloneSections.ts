import { lazy, type ComponentType } from 'react';

/**
 * Settings sections that are not generated from the config schema.
 *
 * Most of the settings tree is built from `config.schema.json` — a section
 * name, a form, a save button. These are the ones that are not: accounts live
 * in users.json, the security posture is computed rather than stored, and the
 * pages moved in from the old System screen act on the operating system
 * instead of on config.yaml.
 *
 * They are listed here rather than as another branch in UISettings' render,
 * because that branch was already a four-deep ternary and this release roughly
 * triples the count. A registry also keeps the decision in one place: whether
 * a section is schema-driven is a fact about the section, not about the order
 * someone wrote the conditions in.
 *
 * Lazily loaded. The old System page pulled its ten panels into the bundle
 * whether or not anyone opened them; from a sidebar, most visits open one.
 */

export interface StandaloneSection {
  /** The component rendered when this section is selected. */
  component: ComponentType<StandaloneSectionProps>;
}

export interface StandaloneSectionProps {
  /** Lets a section ask the editor to show the restart banner. */
  onRestartRequired?: () => void;
}

/**
 * Wrap a dynamic import as a lazy section.
 *
 * The cast is deliberate: most of these components take no props at all, a
 * couple take `onRestartRequired`, and the registry hands every one of them
 * the same object. TypeScript cannot express "ignores what it does not want"
 * across a heterogeneous map, and widening the components' own prop types to
 * match would put a prop in their signatures that they never read.
 */
const lazySection = (
  loader: () => Promise<{ default: ComponentType<StandaloneSectionProps> }>,
) => lazy(loader) as ComponentType<StandaloneSectionProps>;

export const STANDALONE_SECTIONS: Record<string, StandaloneSection> = {
  security: { component: lazySection(() => import('../../SecurityView') as Promise<{ default: ComponentType<StandaloneSectionProps> }>) },
  accounts: { component: lazySection(() => import('../../AccountsView') as Promise<{ default: ComponentType<StandaloneSectionProps> }>) },

  // Moved in from the System page.
  hostname: {
    component: lazySection(() => import('../SystemStateComponents/HostnameSection') as Promise<{ default: ComponentType<StandaloneSectionProps> }>),
  },
  timezone: {
    component: lazySection(() => import('../SystemStateComponents/TimezoneSection') as Promise<{ default: ComponentType<StandaloneSectionProps> }>),
  },
  mosquitto: {
    component: lazySection(() => import('../SystemStateComponents/MqttPasswordsSection') as Promise<{ default: ComponentType<StandaloneSectionProps> }>),
  },
  nodered_service: {
    component: lazySection(() => import('../SystemStateComponents/NodeRedManagement') as Promise<{ default: ComponentType<StandaloneSectionProps> }>),
  },
  certificate: {
    component: lazySection(() => import('../SystemStateComponents/SslSection') as Promise<{ default: ComponentType<StandaloneSectionProps> }>),
  },
  update: {
    component: lazySection(
      () => import('../SystemState').then(m => ({
        default: (props: StandaloneSectionProps) => m.default({ ...props, section: 'update' }),
      })) as Promise<{ default: ComponentType<StandaloneSectionProps> }>,
    ),
  },
  device_tools: {
    component: lazySection(
      () => import('../SystemState').then(m => ({
        default: (props: StandaloneSectionProps) => m.default({ ...props, section: 'tools' }),
      })) as Promise<{ default: ComponentType<StandaloneSectionProps> }>,
    ),
  },
  hardware_errors: {
    component: lazySection(
      () => import('../SystemState').then(m => ({
        default: (props: StandaloneSectionProps) => m.default({ ...props, section: 'hardware_errors' }),
      })) as Promise<{ default: ComponentType<StandaloneSectionProps> }>,
    ),
  },
  backup: {
    component: lazySection(() => import('../SystemStateComponents/BackupSection') as Promise<{ default: ComponentType<StandaloneSectionProps> }>),
  },
  migrations: {
    component: lazySection(() => import('../MigrationsSection') as Promise<{ default: ComponentType<StandaloneSectionProps> }>),
  },
  power: {
    component: lazySection(() => import('../SystemStateComponents/DeviceControlSection') as Promise<{ default: ComponentType<StandaloneSectionProps> }>),
  },
  factory_reset: {
    component: lazySection(() => import('../SystemStateComponents/FactoryResetSection') as Promise<{ default: ComponentType<StandaloneSectionProps> }>),
  },
};
