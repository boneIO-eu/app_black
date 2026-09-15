/**
 * Bridges monaco-yaml's worker bootstrap to the Monaco >= 0.52 worker API.
 *
 * monaco-yaml 5.5 spawns its language worker through monaco-worker-manager
 * 2.0.1, which still calls the pre-0.52 signature
 * `monaco.editor.createWebWorker({ createData, label, moduleId })`. Monaco
 * 0.52 replaced those options with `{ worker, host, keepIdleModels }`, so
 * `opts.worker` is undefined, Monaco's worker factory throws
 * "Cannot use 'in' operator to search for 'then' in undefined", and the error
 * is swallowed into a main-thread fallback built on `EditorWorker(null)`.
 * That fallback has no foreign module, so every monaco-yaml request rejects
 * with "Missing requestHandler or method: doValidation" (and getFoldingRanges,
 * findDocumentSymbols, findLinks, getCodeAction, ...) while the YAML worker is
 * never even started.
 *
 * The shim recognises the legacy option shape and performs the handshake the
 * current Monaco runtime expects — the same one Monaco's own language workers
 * use in `vs/common/workers.js`: create the worker for `label`, post a wake-up
 * message so the worker installs its real message handler, post `createData`,
 * then hand the live worker to the real `createWebWorker`.
 */

interface LegacyWebWorkerOptions {
  /** Pre-0.52 only: payload passed to the worker's `create()` callback. */
  createData?: unknown;
  /** Worker label, matched by `MonacoEnvironment.getWorker`. */
  label?: string;
  /** Pre-0.52 only: AMD module id. Unused by current Monaco. */
  moduleId?: string;
  host?: unknown;
  keepIdleModels?: boolean;
  /** Present only when the caller already uses the current API. */
  worker?: unknown;
}

type CreateWebWorker = (opts: LegacyWebWorkerOptions) => unknown;

/**
 * The one slice of the Monaco namespace this shim touches, so it accepts both
 * the full `monaco-editor` barrel and the trimmed entry in monaco-editor.ts.
 */
interface MonacoWithEditor {
  editor: object;
}

const patched = new WeakSet<object>();

export function installMonacoWorkerCompat(monaco: MonacoWithEditor): void {
  const editor = monaco.editor as unknown as { createWebWorker: CreateWebWorker };
  if (patched.has(editor)) return;
  patched.add(editor);

  const createWebWorker = editor.createWebWorker;

  editor.createWebWorker = (opts: LegacyWebWorkerOptions) => {
    // Callers on the current API already supply a worker — leave them alone.
    if (opts.worker) {
      return createWebWorker.call(editor, opts);
    }

    const label = opts.label ?? 'monaco-editor-worker';
    const environment = (self as unknown as {
      MonacoEnvironment?: { getWorker?(moduleId: string, label: string): Worker | Promise<Worker> };
    }).MonacoEnvironment;

    if (typeof environment?.getWorker !== 'function') {
      throw new Error('MonacoEnvironment.getWorker is required to create the ' + label + ' worker');
    }

    const worker = Promise.resolve(environment.getWorker('workerMain.js', label)).then((w) => {
      // First message only wakes the worker up so it swaps in the handler that
      // reads createData; the second carries createData itself.
      w.postMessage('ignore');
      w.postMessage(opts.createData);
      return w;
    });

    return createWebWorker.call(editor, {
      worker,
      host: opts.host,
      keepIdleModels: opts.keepIdleModels,
    });
  };
}
