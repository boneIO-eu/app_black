// @vitest-environment jsdom
/**
 * File uploads through the shared axios instance, and the errors they bring.
 *
 * The instance defaults to JSON, and axios turns FormData into JSON under
 * that header — the server then answers 422 for a missing file. The 422's
 * detail is a list of objects, which a page must not render as-is.
 */
import { beforeAll, describe, expect, it, vi } from 'vitest';
import type { InternalAxiosRequestConfig } from 'axios';
import axiosInstance from '../axios';
import { apiErrorMessage } from '../errorMessage';

beforeAll(() => {
  // The request interceptor reads the token from here.
  vi.stubGlobal('localStorage', { getItem: () => null, setItem: () => {}, removeItem: () => {} });
});

async function sent(data: unknown, headers?: Record<string, string>) {
  let seen: InternalAxiosRequestConfig | null = null;
  await axiosInstance.post('/api/x', data, {
    headers,
    adapter: async (config) => {
      seen = config;
      return { data: {}, status: 200, statusText: 'OK', headers: {}, config };
    },
  });
  return seen as unknown as InternalAxiosRequestConfig;
}

describe('uploads', () => {
  it('a FormData body goes out as multipart, with the file in it', async () => {
    const body = new FormData();
    body.append('certificate', new Blob(['pem']), 'ca.crt');
    const config = await sent(body);
    expect(config.data).toBeInstanceOf(FormData);
    expect((config.data as FormData).get('certificate')).toBeTruthy();
    expect(String(config.headers['Content-Type'])).not.toContain('application/json');
  });

  it('JSON bodies stay JSON', async () => {
    const config = await sent({ mode: 'optional' });
    expect(config.data).toBe('{"mode":"optional"}');
    expect(String(config.headers['Content-Type'])).toContain('application/json');
  });
});

describe('apiErrorMessage', () => {
  it('reads a plain detail', () => {
    expect(apiErrorMessage({ response: { data: { detail: 'That CA did not sign this certificate.' } } })).toBe(
      'That CA did not sign this certificate.',
    );
  });

  it("turns FastAPI's validation list into a sentence", () => {
    const err = {
      response: {
        data: {
          detail: [{ type: 'missing', loc: ['body', 'certificate'], msg: 'Field required', input: null }],
        },
      },
    };
    expect(apiErrorMessage(err)).toBe('certificate: Field required');
  });

  it('falls back to the error message', () => {
    expect(apiErrorMessage(new Error('Network Error'))).toBe('Network Error');
  });
});
