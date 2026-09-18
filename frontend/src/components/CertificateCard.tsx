import { useCallback, useEffect, useRef, useState } from 'react';
import { FaLock } from 'react-icons/fa';
import axios from '../api/axios';
import { useTranslation } from '../hooks/useTranslation';
import { SettingsCard, FormField, FormActions } from './UISettings/ui';

interface CertificateDetails {
  subject: string;
  issuer: string;
  not_after: string;
  days_left: number;
  names: string[];
  uncovered: string[];
}

interface CertificateState {
  custom: boolean;
  certificate: CertificateDetails | null;
  reached_by: string[];
  root_ca_available: boolean;
}

/**
 * The certificate this device serves, and how to replace it.
 *
 * Three routes to a panel a browser accepts, in the order they cost the
 * operator anything: cloud registration (elsewhere on this page), trusting
 * this device's own authority, or uploading a certificate of their own. The
 * device never talks to an ACME server itself — doing that from behind a
 * router would mean making the controller reachable from the internet, which
 * is a far larger hole than the warning it would close.
 */
export default function CertificateCard() {
  const { t } = useTranslation();
  const [state, setState] = useState<CertificateState | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const certInput = useRef<HTMLInputElement>(null);
  const keyInput = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    try {
      const { data } = await axios.get<CertificateState>('/api/security/certificate');
      setState(data);
    } catch {
      setState(null);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const detail = (err: unknown): string =>
    (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
    (err as Error).message;

  const upload = async () => {
    const cert = certInput.current?.files?.[0];
    const key = keyInput.current?.files?.[0];
    if (!cert || !key) return;

    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const body = new FormData();
      body.append('certificate', cert);
      body.append('key', key);
      const { data } = await axios.post('/api/security/certificate', body);
      // Said out loud rather than left to be discovered in a browser: a
      // certificate that does not cover the address people type leaves exactly
      // the warning it was meant to remove.
      const uncovered: string[] = data?.certificate?.uncovered ?? [];
      setNotice(
        uncovered.length
          ? t('security.cert.installed_uncovered', { names: uncovered.join(', ') })
          : t('security.cert.installed'),
      );
      if (certInput.current) certInput.current.value = '';
      if (keyInput.current) keyInput.current.value = '';
      await load();
    } catch (err) {
      setError(detail(err));
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!window.confirm(t('security.cert.remove_confirm'))) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await axios.delete('/api/security/certificate');
      setNotice(t('security.cert.removed'));
      await load();
    } catch (err) {
      setError(detail(err));
    } finally {
      setBusy(false);
    }
  };

  const downloadRootCa = async () => {
    try {
      const { data } = await axios.get('/api/security/root-ca', { responseType: 'blob' });
      const url = URL.createObjectURL(new Blob([data]));
      const link = document.createElement('a');
      link.href = url;
      link.download = 'boneio-root-ca.crt';
      link.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(detail(err));
    }
  };

  if (!state) return null;

  const cert = state.certificate;

  return (
    <SettingsCard title={t('security.cert.title')} icon={<FaLock />}>
      <p className="text-sm text-base-content/70">
        {state.custom ? t('security.cert.using_custom') : t('security.cert.using_internal')}
      </p>

      {cert && (
        <dl className="text-xs mt-2 space-y-1">
          <div>
            <dt className="inline font-semibold">{t('security.cert.issuer')}: </dt>
            <dd className="inline break-all">{cert.issuer}</dd>
          </div>
          <div>
            <dt className="inline font-semibold">{t('security.cert.valid_for')}: </dt>
            <dd className="inline break-all">{cert.names.join(', ') || '—'}</dd>
          </div>
          <div>
            <dt className="inline font-semibold">{t('security.cert.expires')}: </dt>
            <dd className="inline">
              {new Date(cert.not_after).toLocaleDateString()} ({cert.days_left} d)
            </dd>
          </div>
          {cert.uncovered.length > 0 && (
            <div className="text-warning">
              {t('security.cert.uncovered', { names: cert.uncovered.join(', ') })}
            </div>
          )}
        </dl>
      )}

      <p className="text-xs text-base-content/60 mt-2">
        {t('security.cert.reached_by', { names: state.reached_by.join(', ') })}
      </p>

      {error && <div className="alert alert-error text-sm mt-3">{error}</div>}
      {notice && <div className="alert alert-success text-sm mt-3">{notice}</div>}

      <FormField label={t('security.cert.file_cert')} help={t('security.cert.file_cert_help')}>
        <input ref={certInput} type="file" accept=".pem,.crt,.cer" className="file-input file-input-bordered w-full" />
      </FormField>
      <FormField label={t('security.cert.file_key')} help={t('security.cert.file_key_help')}>
        <input ref={keyInput} type="file" accept=".pem,.key" className="file-input file-input-bordered w-full" />
      </FormField>

      <FormActions>
        <button className="btn btn-primary" disabled={busy} onClick={() => void upload()}>
          {t('security.cert.upload')}
        </button>
        {state.custom && (
          <button className="btn btn-outline" disabled={busy} onClick={() => void remove()}>
            {t('security.cert.remove')}
          </button>
        )}
        {state.root_ca_available && !state.custom && (
          <button className="btn btn-ghost" onClick={() => void downloadRootCa()}>
            {t('security.cert.download_root_ca')}
          </button>
        )}
      </FormActions>

      {state.root_ca_available && !state.custom && (
        <p className="text-xs text-base-content/60">{t('security.cert.root_ca_help')}</p>
      )}
    </SettingsCard>
  );
}
