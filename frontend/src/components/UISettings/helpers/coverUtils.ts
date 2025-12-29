import type { CoverEntity } from '@/types/config';

/**
 * Normalize cover entity to ensure it has an ID.
 * If no explicit ID is set, generates one from open_relay and close_relay.
 */
export function normalizeCover(cover: CoverEntity, index: number = 0): CoverEntity & { id: string } {
  if (cover.id) {
    return { ...cover, id: cover.id };
  }
  
  // Generate ID from relays if available
  if (cover.open_relay && cover.close_relay) {
    return {
      ...cover,
      id: `cover_${cover.open_relay}_${cover.close_relay}`.toLowerCase()
    };
  }
  
  // Fallback to index-based ID
  return {
    ...cover,
    id: `cover_${index}`
  };
}

/**
 * Normalize array of covers to ensure all have IDs
 */
export function normalizeCovers(covers: CoverEntity[]): Array<CoverEntity & { id: string }> {
  return covers
    .filter(cover => cover && typeof cover === 'object')
    .map((cover, index) => normalizeCover(cover, index));
}
