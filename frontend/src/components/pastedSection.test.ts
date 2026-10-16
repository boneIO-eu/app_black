import { describe, expect, it } from 'vitest';
import { parsePastedSection } from './pastedSection';

describe('parsePastedSection', () => {
  it('takes the section from its one top-level key, fenced or not', () => {
    const yaml = 'output:\n  - name: Lamp\n    boneio_output: OUT_01\n';
    expect(parsePastedSection(yaml)).toEqual({ section: 'output', data: [{ name: 'Lamp', boneio_output: 'OUT_01' }] });
    expect(parsePastedSection('Here you go:\n```yaml\n' + yaml + '```\nDone.')).toMatchObject({ section: 'output' });
    expect(parsePastedSection('{"mqtt": {"host": "h"}}')).toEqual({ section: 'mqtt', data: { host: 'h' } });
  });

  it('says what is wrong with anything else', () => {
    expect(parsePastedSection('  ')).toEqual({ error: 'empty' });
    expect(parsePastedSection('output: [\n')).toEqual({ error: 'unparsable' });
    expect(parsePastedSection('- name: Lamp')).toEqual({ error: 'shape' });
    expect(parsePastedSection('output: []\nevent: []')).toEqual({ error: 'shape' });
    expect(parsePastedSection('output: 5')).toEqual({ error: 'shape' });
  });
});
