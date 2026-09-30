/**
 * Splitting a dashboard's entities into one group per area.
 */
import type { AreaEntity } from '@/types/config';

export interface AreaGroup<T> {
  /** Area id, or null for the entities that have none. */
  id: string | null;
  /** Area name as configured; the id when the area is no longer configured. */
  name: string | null;
  items: T[];
}

/**
 * Groups `items` by area, in the order the areas are configured.
 *
 * Only areas that have something in them appear. An entity pointing at an
 * area that is no longer configured still gets a group, named by its id, so
 * it is not silently filed as "no area". The entities with no area come last.
 * Items keep their order within a group.
 */
export function groupByArea<T>(
  items: T[],
  areaOf: (item: T) => string | null | undefined,
  areas: AreaEntity[],
): AreaGroup<T>[] {
  const byArea = new Map<string, T[]>();
  const unassigned: T[] = [];

  for (const item of items) {
    const area = areaOf(item);
    if (!area) {
      unassigned.push(item);
      continue;
    }
    const bucket = byArea.get(area);
    if (bucket) bucket.push(item);
    else byArea.set(area, [item]);
  }

  const groups: AreaGroup<T>[] = [];
  for (const area of areas) {
    const bucket = byArea.get(area.id);
    if (!bucket) continue;
    groups.push({ id: area.id, name: area.name || area.id, items: bucket });
    byArea.delete(area.id);
  }
  for (const [id, bucket] of byArea) {
    groups.push({ id, name: id, items: bucket });
  }
  if (unassigned.length > 0) {
    groups.push({ id: null, name: null, items: unassigned });
  }
  return groups;
}
