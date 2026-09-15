/**
 * The Monaco build boneIO actually uses: editor core plus YAML, nothing else.
 *
 * Importing the `monaco-editor` barrel pulls in `editor.main.js`, which
 * registers four worker-backed language services (TypeScript, CSS, HTML, JSON)
 * and ~85 Monarch grammars. The config editor only ever opens YAML — monaco-yaml
 * supplies the language service and `yaml.contribution` the highlighting — so
 * everything else was emitted into the dist and shipped to the device for
 * nothing (the TypeScript worker alone was 6.9 MB).
 *
 * Import this module instead of `monaco-editor` anywhere in the app. Adding a
 * language means adding its `basic-languages/<lang>/<lang>.contribution.js`
 * import here.
 */
import 'monaco-editor/esm/vs/basic-languages/yaml/yaml.contribution.js';

export * from 'monaco-editor/esm/vs/editor/edcore.main.js';
