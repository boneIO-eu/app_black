import { describe, expect, it } from 'vitest';
import { groupByArea } from '../groupByArea';

const areas = [
  { id: 'salon', name: 'Salon' },
  { id: 'kuchnia', name: 'Kuchnia' },
  { id: 'garaz', name: 'Garaż' },
];

type Item = { id: string; area?: string | null };
const areaOf = (i: Item) => i.area;

describe('groupByArea', () => {
  it('orders groups as the areas are configured, not as the items come', () => {
    const groups = groupByArea<Item>(
      [{ id: 'a', area: 'kuchnia' }, { id: 'b', area: 'salon' }, { id: 'c', area: 'kuchnia' }],
      areaOf,
      areas,
    );
    expect(groups.map((g) => g.name)).toEqual(['Salon', 'Kuchnia']);
    expect(groups[1].items.map((i) => i.id)).toEqual(['a', 'c']);
  });

  it('leaves out areas with nothing in them', () => {
    const groups = groupByArea<Item>([{ id: 'a', area: 'garaz' }], areaOf, areas);
    expect(groups.map((g) => g.id)).toEqual(['garaz']);
  });

  it('puts items with no area last, in a group without a name', () => {
    const groups = groupByArea<Item>(
      [{ id: 'a' }, { id: 'b', area: 'salon' }, { id: 'c', area: null }, { id: 'd', area: '' }],
      areaOf,
      areas,
    );
    expect(groups.map((g) => g.id)).toEqual(['salon', null]);
    expect(groups[1].name).toBeNull();
    expect(groups[1].items.map((i) => i.id)).toEqual(['a', 'c', 'd']);
  });

  it('keeps an area that is no longer configured as its own group, named by id', () => {
    const groups = groupByArea<Item>(
      [{ id: 'a', area: 'strych' }, { id: 'b', area: 'salon' }],
      areaOf,
      areas,
    );
    expect(groups.map((g) => [g.id, g.name])).toEqual([
      ['salon', 'Salon'],
      ['strych', 'strych'],
    ]);
  });
});
