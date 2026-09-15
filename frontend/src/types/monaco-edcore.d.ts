/**
 * `edcore.main.js` is Monaco's "editor core" entry: the same public API as
 * `monaco-editor`, with every editor contribution, but without the language
 * packs. It ships no typings of its own, so borrow the barrel's.
 */
declare module 'monaco-editor/esm/vs/editor/edcore.main.js' {
  export * from 'monaco-editor';
}
