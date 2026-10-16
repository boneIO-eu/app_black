export type DiffRow =
  | { kind: 'add' | 'del' | 'ctx'; text: string; line: number | null }
  | { kind: 'gap' };

/**
 * A unified diff as rows to draw: the file headers dropped, each hunk header
 * turned into a gap between stretches, and every line numbered as it will
 * stand after the change (a removed line has no such number).
 */
export function parseDiff(diff: string): { rows: DiffRow[]; added: number; removed: number } {
  const rows: DiffRow[] = [];
  let added = 0;
  let removed = 0;
  let line = 0;
  for (const raw of diff.split('\n')) {
    if (raw.startsWith('+++') || raw.startsWith('---')) continue;
    const hunk = raw.match(/^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@/);
    if (hunk) {
      if (rows.length) rows.push({ kind: 'gap' });
      line = Number(hunk[1]);
      continue;
    }
    if (raw.startsWith('+')) {
      rows.push({ kind: 'add', text: raw.slice(1), line: line++ });
      added++;
    } else if (raw.startsWith('-')) {
      rows.push({ kind: 'del', text: raw.slice(1), line: null });
      removed++;
    } else if (raw.startsWith(' ')) {
      rows.push({ kind: 'ctx', text: raw.slice(1), line: line++ });
    }
  }
  return { rows, added, removed };
}
