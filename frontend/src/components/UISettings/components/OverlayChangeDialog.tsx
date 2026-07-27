/**
 * Dialog shown when the board version has been changed and the device tree
 * overlay in /boot/uEnv.txt needs updating.
 *
 * Includes a sudo password field since boneIO runs as user `boneio`
 * without write access to /boot/.
 */
import React, { useState } from 'react';
import { useTranslation } from '@/hooks/useTranslation';

interface OverlayChangeDialogProps {
  open: boolean;
  currentOverlay: string | null;
  expectedOverlay: string | null;
  newVersion: string;
  isChanging: boolean;
  changeResult: 'success' | 'error' | null;
  changeError: string | null;
  onApply: (password: string) => void;
  onDismiss: () => void;
}

/**
 * Confirmation dialog for device tree overlay changes.
 *
 * Shows a warning that changing the overlay is potentially dangerous,
 * displays current vs expected overlay, asks for sudo password,
 * and requests user confirmation.
 */
const OverlayChangeDialog: React.FC<OverlayChangeDialogProps> = ({
  open,
  currentOverlay,
  expectedOverlay,
  newVersion,
  isChanging,
  changeResult,
  changeError,
  onApply,
  onDismiss,
}) => {
  const { t } = useTranslation();
  const [password, setPassword] = useState('');

  if (!open) return null;

  const handleApply = () => {
    if (!password.trim()) return;
    onApply(password);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && password.trim() && !isChanging && changeResult !== 'success') {
      handleApply();
    }
  };

  return (
    <div className="dialog-backdrop" onClick={onDismiss}>
      <div
        className="dialog-content"
        style={{ maxWidth: 520 }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="dialog-header">
          <span style={{ fontSize: '1.3em' }}>⚠️</span>
          <h3 className="dialog-title">{t('overlay.title')}</h3>
        </div>

        <div className="dialog-body" style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          <p style={{ color: 'var(--color-warning, #f59e0b)', fontWeight: 600 }}>
            {t('overlay.warning')}
          </p>

          <p>{t('overlay.description', { version: newVersion })}</p>

          <div style={{
            background: 'var(--color-surface, #1e293b)',
            borderRadius: 8,
            padding: '0.75rem 1rem',
            fontSize: '0.875rem',
            fontFamily: 'monospace',
          }}>
            <div style={{ marginBottom: '0.25rem' }}>
              <span style={{ opacity: 0.6 }}>{t('overlay.current')}:</span>{' '}
              <strong>{currentOverlay || '—'}</strong>
            </div>
            <div>
              <span style={{ opacity: 0.6 }}>{t('overlay.expected')}:</span>{' '}
              <strong style={{ color: 'var(--color-success, #22c55e)' }}>
                {expectedOverlay || '—'}
              </strong>
            </div>
          </div>

          {/* Sudo password input */}
          <div>
            <label
              htmlFor="overlay-sudo-password"
              style={{ display: 'block', fontSize: '0.85rem', marginBottom: '0.25rem', opacity: 0.8 }}
            >
              {t('overlay.password_label')}
            </label>
            <input
              id="overlay-sudo-password"
              type="password"
              className="input input-bordered w-full"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={t('overlay.password_placeholder')}
              disabled={isChanging || changeResult === 'success'}
              autoFocus
            />
          </div>

          <p style={{ fontSize: '0.85rem', opacity: 0.7 }}>
            {t('overlay.restart_notice')}
          </p>

          {changeResult === 'success' && (
            <p style={{ color: 'var(--color-success, #22c55e)', fontWeight: 600 }}>
              ✅ {t('overlay.success')}
            </p>
          )}

          {changeResult === 'error' && (
            <p style={{ color: 'var(--color-error, #ef4444)', fontWeight: 600 }}>
              ❌ {changeError || t('overlay.change_failed')}
            </p>
          )}
        </div>

        <div className="dialog-footer">
          <button
            className="btn btn-secondary"
            onClick={onDismiss}
            disabled={isChanging}
          >
            {t('overlay.dismiss')}
          </button>
          <button
            className="btn btn-warning"
            onClick={handleApply}
            disabled={isChanging || changeResult === 'success' || !password.trim()}
            style={{
              background: 'var(--color-warning, #f59e0b)',
              color: '#000',
              fontWeight: 600,
            }}
          >
            {isChanging ? t('overlay.changing') : t('overlay.apply')}
          </button>
        </div>
      </div>
    </div>
  );
};

export default OverlayChangeDialog;
