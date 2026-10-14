import { describe, expect, it } from 'vitest';
import { mustNotBeActiveAtStartup } from '../inputFilterUtils';

describe('mustNotBeActiveAtStartup', () => {
  it('flags the boot-pin inputs in any case', () => {
    for (const pin of ['IN_01', 'in_02', 'IN_10', 'in_19', 'IN_21', 'in_29', 'IN_34']) {
      expect(mustNotBeActiveAtStartup(pin)).toBe(true);
    }
  });

  it('leaves the others and an empty pick alone', () => {
    for (const pin of ['IN_03', 'in_08', 'IN_22', 'in_28', 'IN_35', 'in_49', undefined, '']) {
      expect(mustNotBeActiveAtStartup(pin)).toBe(false);
    }
  });
});
