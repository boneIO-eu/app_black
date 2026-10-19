import { describe, expect, it } from 'vitest';
import { cpuSummary, type CpuReport } from './cpuSummary';

const report = (over: Partial<CpuReport>): CpuReport => ({
  measured_at: 0,
  breakdown: { user: 0, system: 0, iowait: 0, irq: 0, softirq: 0, idle: 100 },
  busy: 0,
  interrupts: false,
  services: [],
  processes: [],
  ...over,
});

describe('cpuSummary', () => {
  it('an idle controller has nothing to blame', () => {
    expect(cpuSummary(report({ busy: 20, services: [{ label: 'nodered.service', percent: 15 }] })))
      .toEqual({ kind: 'idle' });
  });

  it('interrupts are named before any program', () => {
    expect(cpuSummary(report({ busy: 95, interrupts: true, services: [{ label: 'node', percent: 10 }] })))
      .toEqual({ kind: 'interrupts' });
  });

  it('a busy controller names the service on top', () => {
    expect(cpuSummary(report({ busy: 98, services: [{ label: 'nodered.service', percent: 87 }] })))
      .toEqual({ kind: 'service', label: 'nodered.service', percent: 87 });
  });
});
