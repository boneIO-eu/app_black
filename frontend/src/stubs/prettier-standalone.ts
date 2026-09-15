/**
 * Stands in for `prettier/standalone` inside monaco-yaml's worker.
 *
 * monaco-yaml imports Prettier unconditionally to back its optional "format
 * document" feature, which only registers when `configureMonacoYaml` is given
 * `format: { enable: true }`. boneIO never enables it, so the real Prettier was
 * ~420 kB of the YAML worker that could never run. See the aliases in
 * vite.config.ts.
 *
 * If YAML formatting is ever wanted, drop those aliases rather than filling
 * this in.
 */
export function format(): never {
  throw new Error(
    'YAML formatting is not bundled in this build. Remove the prettier aliases ' +
      'in vite.config.ts to enable it.',
  );
}
