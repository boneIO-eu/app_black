export interface CpuService {
  label: string;
  percent: number;
}

export interface CpuProcess extends CpuService {
  pid: number;
  name: string;
}

/** `GET /api/diagnostics/cpu`. */
export interface CpuReport {
  measured_at: number;
  breakdown: Record<'user' | 'system' | 'iowait' | 'irq' | 'softirq' | 'idle', number>;
  busy: number;
  interrupts: boolean;
  services: CpuService[];
  processes: CpuProcess[];
}

export type CpuSummary =
  | { kind: 'idle' }
  | { kind: 'interrupts' }
  | { kind: 'service'; label: string; percent: number };

/** Below this the headline says the processor is fine rather than naming anyone. */
export const CPU_BUSY_HEADLINE = 50;

/** The one sentence an owner reads first: who holds the processor, if anyone. */
export function cpuSummary(report: CpuReport): CpuSummary {
  if (report.busy < CPU_BUSY_HEADLINE) return { kind: 'idle' };
  if (report.interrupts) return { kind: 'interrupts' };
  const top = report.services[0];
  return top ? { kind: 'service', label: top.label, percent: top.percent } : { kind: 'idle' };
}
