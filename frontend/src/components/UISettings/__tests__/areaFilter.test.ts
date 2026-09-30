import { describe, expect, it } from 'vitest';
import { areaMatches } from '../tables/areaFilter';

const areas = [{ id: 'living_room', name: 'Salon' }, { id: 'gabinet', name: 'Gabinet' }];

describe('areaMatches', () => {
  it('matches the area name the table shows', () => {
    expect(areaMatches('living_room', areas, 'salo')).toBe(true);
  });

  it('matches the id too', () => {
    expect(areaMatches('living_room', areas, 'living')).toBe(true);
  });

  it('matches an area no longer configured by its id', () => {
    expect(areaMatches('strych', areas, 'stry')).toBe(true);
  });

  it('does not match a row with no area', () => {
    expect(areaMatches(undefined, areas, 'salon')).toBe(false);
  });

  it('does not match another area', () => {
    expect(areaMatches('gabinet', areas, 'salon')).toBe(false);
  });
});
