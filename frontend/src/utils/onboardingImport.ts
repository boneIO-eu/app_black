/**
 * Pure helpers behind the onboarding wizard's "import old configuration" step.
 *
 * They live outside the component so the rules can be tested directly: the
 * restore endpoint's habit of reporting failure with HTTP 200 is exactly the
 * kind of thing that quietly regresses into a green success message.
 */

/** Extensions POST /api/config/restore accepts (see routes/config_backups.py). */
export const IMPORT_EXTENSIONS = ['.tar.gz', '.tgz'];

/**
 * Refuse archives larger than this before uploading them.
 *
 * A config archive holds YAML only and runs to a few kilobytes; anything this
 * size is the wrong file, and catching it here saves pushing megabytes at a
 * BeagleBone over Wi-Fi only to be told no.
 */
export const MAX_IMPORT_BYTES = 10 * 1024 * 1024;

/** Why a chosen file cannot be uploaded. */
export type ImportFileRejection =
  | { reason: 'invalid_type' }
  | { reason: 'too_large'; maxMegabytes: number };

/**
 * Vet a chosen archive before it is uploaded.
 *
 * @param file - Name and size of the picked file.
 * @returns The rejection, or null when the file looks importable.
 */
export function checkImportFile(file: { name: string; size: number }): ImportFileRejection | null {
  const name = file.name.toLowerCase();
  if (!IMPORT_EXTENSIONS.some((ext) => name.endsWith(ext))) {
    return { reason: 'invalid_type' };
  }
  if (file.size > MAX_IMPORT_BYTES) {
    return { reason: 'too_large', maxMegabytes: Math.round(MAX_IMPORT_BYTES / (1024 * 1024)) };
  }
  return null;
}

/**
 * What actually happened, once the restore response has been read properly.
 *
 * `warning` means the files landed but the config does not load — worth
 * saying, not worth blocking on, since the editor can fix it afterwards.
 */
export type RestoreOutcome =
  | { status: 'error'; message?: string }
  | { status: 'empty' }
  | { status: 'warning'; message?: string }
  | { status: 'ok' };

/**
 * Work out whether a restore succeeded.
 *
 * `POST /api/config/restore` answers HTTP 200 for every outcome, including a
 * corrupt archive and a rejected file type, so the body is the only signal
 * there is. It also calls an archive holding no YAML a success, with an empty
 * `restored_files` — nothing was imported, so this reports that separately.
 *
 * @param data - Parsed response body, trusted no further than it deserves.
 */
export function interpretRestoreResponse(data: unknown): RestoreOutcome {
  const body = (data ?? {}) as Record<string, unknown>;

  if (body.status === 'error') {
    return {
      status: 'error',
      message: typeof body.message === 'string' ? body.message : undefined,
    };
  }

  if (Array.isArray(body.restored_files) && body.restored_files.length === 0) {
    return { status: 'empty' };
  }

  if (body.validation_status === 'warning') {
    return {
      status: 'warning',
      message:
        typeof body.validation_message === 'string' ? body.validation_message : undefined,
    };
  }

  return { status: 'ok' };
}
