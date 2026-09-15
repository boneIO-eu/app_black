/**
 * Collapsing repeated log lines.
 *
 * A controller with a failing Modbus device writes the same pair of lines
 * every few seconds for days. Showing each one is how a log viewer becomes
 * useless: the thing that happened once, and matters, is buried under the
 * thing that happened nine hundred times.
 *
 * This lives outside the component because the previous version was wrong in
 * a way nobody could see. It collapsed identical *consecutive* lines and then
 * looked for repeating sequences of two to five — both of which need the
 * pattern to be uninterrupted, and on a real device it never is. One
 * unrelated line between two repeats ended the run. The screenshot that
 * started this had pages of alternating Modbus errors with the occasional
 * INFO through them: exactly what the feature was for, and it collapsed
 * almost none of it.
 */

export interface LogLine {
  timestamp: string;
  message: string;
  level: string;
}

export interface AggregatedLog extends LogLine {
  /**
   * When this first appeared; differs from `timestamp` once count > 1.
   *
   * `timestamp` is the most recent occurrence, not the first, because that is
   * where the row sits. Showing the first would make the times run backwards
   * against the order of the list — which is what the old version did, and it
   * read as a bug.
   */
  firstTimestamp: string;
  /** How many lines were folded into this one. */
  count: number;
}

/**
 * Normalise a message so repetitions that differ only in noise match.
 *
 * Deliberately shallow. Thread names and elapsed seconds change between
 * otherwise identical lines, so they go; device numbers and addresses stay,
 * because "device 1 is failing" and "device 10 is failing" are two problems
 * and folding them into one would hide the second.
 */
export function fingerprint(message: string): string {
  return (
    message
      // "(MainThread)" / "(modbus_worker_0)" becomes "(...)"
      .replace(/\([A-Za-z_]+[\w]*\)/g, '(...)')
      // "45.0 seconds" becomes "... seconds"
      .replace(/\d+\.\d+\s*(seconds?|s\b)/gi, '... $1')
  );
}

/**
 * Fold repeated lines into one entry each.
 *
 * Grouping is by level and fingerprint across the whole window, wherever the
 * occurrences sit — the way Home Assistant reports "first occurred at ... and
 * shows up N times".
 *
 * Each group takes the position of its most recent occurrence rather than its
 * first. The list runs oldest to newest with auto-scroll pinned to the bottom,
 * so a group anchored at its first appearance would freeze halfway up the page
 * while its counter ticked, and a live tail would look dead. Anchored at the
 * newest, a message that starts repeating moves down to where the reader is
 * looking.
 *
 * @param lines Filtered log lines, oldest first.
 * @param normalize How to reduce a message to its repeatable shape.
 * @returns One entry per distinct message, in the input's order.
 */
export function aggregateLogs(
  lines: LogLine[],
  normalize: (message: string) => string = fingerprint,
): AggregatedLog[] {
  const groups = new Map<string, AggregatedLog>();
  const lastIndex = new Map<string, number>();

  lines.forEach((line, index) => {
    const key = `${line.level} ${normalize(line.message)}`;
    const existing = groups.get(key);
    if (existing) {
      existing.count += 1;
      existing.timestamp = line.timestamp;
    } else {
      groups.set(key, {
        timestamp: line.timestamp,
        firstTimestamp: line.timestamp,
        message: line.message,
        level: line.level,
        count: 1,
      });
    }
    lastIndex.set(key, index);
  });

  return Array.from(groups.entries())
    .sort(([a], [b]) => (lastIndex.get(a) ?? 0) - (lastIndex.get(b) ?? 0))
    .map(([, entry]) => entry);
}
