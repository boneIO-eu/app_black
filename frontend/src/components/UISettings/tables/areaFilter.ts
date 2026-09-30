/**
 * Whether a row's area matches a table filter, by the area's name or its id.
 *
 * The tables show the name, so that is what people type; the id still
 * matches for an area that is no longer configured.
 */
export function areaMatches(
  areaId: string | undefined | null,
  areas: Array<{ id: string; name?: string }>,
  lowerFilter: string,
): boolean {
  if (!areaId) return false;
  const name = areas.find((a) => a.id === areaId)?.name;
  return (
    areaId.toLowerCase().includes(lowerFilter) ||
    (!!name && name.toLowerCase().includes(lowerFilter))
  );
}
