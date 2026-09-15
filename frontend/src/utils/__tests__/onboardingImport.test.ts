import { describe, it, expect } from 'vitest';
import {
  MAX_IMPORT_BYTES,
  checkImportFile,
  interpretRestoreResponse,
} from '../onboardingImport';

describe('checkImportFile', () => {
  it('accepts the extensions the restore endpoint accepts', () => {
    expect(checkImportFile({ name: 'boneio_config_20260101.tar.gz', size: 4096 })).toBeNull();
    expect(checkImportFile({ name: 'backup.tgz', size: 4096 })).toBeNull();
  });

  it('accepts an uppercased extension', () => {
    expect(checkImportFile({ name: 'BACKUP.TAR.GZ', size: 4096 })).toBeNull();
  });

  it('rejects an archive that is not a config backup', () => {
    expect(checkImportFile({ name: 'holiday.zip', size: 4096 })).toEqual({
      reason: 'invalid_type',
    });
    // .gz alone is not what the backend unpacks.
    expect(checkImportFile({ name: 'config.gz', size: 4096 })).toEqual({
      reason: 'invalid_type',
    });
  });

  it('rejects a file too large to be a config archive', () => {
    expect(checkImportFile({ name: 'huge.tar.gz', size: MAX_IMPORT_BYTES + 1 })).toEqual({
      reason: 'too_large',
      maxMegabytes: 10,
    });
  });

  it('allows a file exactly on the limit', () => {
    expect(checkImportFile({ name: 'edge.tar.gz', size: MAX_IMPORT_BYTES })).toBeNull();
  });
});

describe('interpretRestoreResponse', () => {
  it('reports a failure the backend delivered with HTTP 200', () => {
    expect(
      interpretRestoreResponse({
        status: 'error',
        message: 'Failed to extract archive: not a gzip file',
      }),
    ).toEqual({ status: 'error', message: 'Failed to extract archive: not a gzip file' });
  });

  it('reports an error with no message so the caller can fall back', () => {
    expect(interpretRestoreResponse({ status: 'error' })).toEqual({
      status: 'error',
      message: undefined,
    });
  });

  it('treats an archive that restored nothing as a failed import', () => {
    expect(
      interpretRestoreResponse({
        status: 'success',
        message: 'Restored 0 files from backup',
        restored_files: [],
      }),
    ).toEqual({ status: 'empty' });
  });

  it('passes through a restore that succeeded', () => {
    expect(
      interpretRestoreResponse({
        status: 'success',
        restored_files: ['config.yaml'],
        validation_status: 'success',
      }),
    ).toEqual({ status: 'ok' });
  });

  it('surfaces a restored config that does not validate', () => {
    expect(
      interpretRestoreResponse({
        status: 'success',
        restored_files: ['config.yaml'],
        validation_status: 'warning',
        validation_message: 'Configuration restored but validation failed: bad key',
      }),
    ).toEqual({
      status: 'warning',
      message: 'Configuration restored but validation failed: bad key',
    });
  });

  it('still flags a validation warning that carries no message', () => {
    expect(
      interpretRestoreResponse({
        status: 'success',
        restored_files: ['config.yaml'],
        validation_status: 'warning',
      }),
    ).toEqual({ status: 'warning', message: undefined });
  });

  it('does not mistake a missing body for success detail', () => {
    expect(interpretRestoreResponse(null)).toEqual({ status: 'ok' });
    expect(interpretRestoreResponse(undefined)).toEqual({ status: 'ok' });
  });
});
