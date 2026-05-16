/**
 * Convert a JSON path (clicked in the topic inspector) into a Jinja2 value_template.
 *
 * Examples:
 *   ['val']                  → '{{ value_json.val }}'
 *   ['zones', 0]             → '{{ value_json.zones[0] }}'
 *   ['status', 'time']       → '{{ value_json.status.time }}'
 *   []                       → '{{ value_json }}'
 *
 * Identifiers that aren't valid Jinja2 attribute names fall back to subscript:
 *   ['weird-key']            → "{{ value_json['weird-key'] }}"
 */

const VALID_IDENT = /^[A-Za-z_][A-Za-z0-9_]*$/;

export type JsonPathSegment = string | number;

export function jsonPathToJinja(path: JsonPathSegment[]): string {
  if (path.length === 0) return '{{ value_json }}';
  let expr = 'value_json';
  for (const seg of path) {
    if (typeof seg === 'number') {
      expr += `[${seg}]`;
    } else if (VALID_IDENT.test(seg)) {
      expr += `.${seg}`;
    } else {
      const escaped = seg.replace(/'/g, "\\'");
      expr += `['${escaped}']`;
    }
  }
  return `{{ ${expr} }}`;
}
