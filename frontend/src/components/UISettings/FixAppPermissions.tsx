import { useState } from 'react';
import { FaSpinner, FaSync, FaUserShield } from 'react-icons/fa';
import axios from '@/api/axios';
import { useTranslation } from '@/hooks/useTranslation';
import SudoPasswordDialog from './SudoPasswordDialog';
import { SettingsCard, FormActions, NoticeCallout, StatGrid } from './ui';

/**
 * Component for diagnosing and fixing app file permissions via sudo.
 * Currently handles docker-compose.yaml; uses shared SudoPasswordDialog for password input.
 */
export default function FixAppPermissions() {
  const { t } = useTranslation();
  const [permInfo, setPermInfo] = useState<any>(null);
  const [fixResult, setFixResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [fixing, setFixing] = useState(false);
  const [showSudoDialog, setShowSudoDialog] = useState(false);
  const [sudoError, setSudoError] = useState<string | null>(null);

  const testPermissions = async () => {
    setLoading(true);
    setPermInfo(null);
    try {
      const { data } = await axios.get('/api/cloud/test-permissions');
      setPermInfo(data);
    } catch (err: any) {
      setPermInfo({ error: err.message || 'Request failed' });
    } finally {
      setLoading(false);
    }
  };

  const fixPermissions = async (password: string) => {
    setFixing(true);
    setFixResult(null);
    setSudoError(null);
    try {
      const { data } = await axios.post('/api/cloud/fix-permissions', { password });
      setFixResult(data);
      if (data.status === 'success') {
        setShowSudoDialog(false);
        testPermissions();
      } else {
        setSudoError(data.message || t('common.error'));
      }
    } catch (err: any) {
      setSudoError(err.response?.data?.detail || err.message || 'Request failed');
    } finally {
      setFixing(false);
    }
  };

  return (
    <>
      <SettingsCard
        icon={<FaUserShield />}
        title={t('sudo_dialog.fix_app_permissions')}
        description={t('sudo_dialog.app_permissions_description')}
        footer={
          <FormActions>
            {permInfo?.file_exists && !permInfo.writable && (
              <button
                className="btn btn-primary btn-sm"
                onClick={() => {
                  setSudoError(null);
                  setShowSudoDialog(true);
                }}
              >
                {t('sudo_dialog.fix_permissions')}
              </button>
            )}
            <button
              className="btn btn-outline btn-sm gap-2"
              onClick={testPermissions}
              disabled={loading}
            >
              {loading ? <FaSpinner className="animate-spin" /> : <FaSync />}
              {t('sudo_dialog.check_file_permissions')}
            </button>
          </FormActions>
        }
      >
        {permInfo || fixResult ? (
          <div className="space-y-3">
            {permInfo && (
              <>
                {/* The raw JSON this used to dump was a diagnostic, not an
                    answer. The question is "can the app write the file", so
                    say that, and show the three facts that explain a no. */}
                <NoticeCallout
                  variant={
                    !permInfo.file_exists
                      ? 'error'
                      : permInfo.writable
                        ? 'success'
                        : 'warning'
                  }
                  message={
                    !permInfo.file_exists
                      ? t('sudo_dialog.file_missing')
                      : permInfo.writable
                        ? t('sudo_dialog.permissions_ok')
                        : t('sudo_dialog.permissions_missing')
                  }
                />
                <StatGrid
                  columns={3}
                  items={[
                    {
                      label: t('sudo_dialog.file_path'),
                      value: permInfo.compose_path || '—',
                      mono: true,
                    },
                    {
                      label: t('sudo_dialog.file_owner'),
                      value: permInfo.file_owner || '—',
                      mono: true,
                    },
                    {
                      label: t('sudo_dialog.file_mode'),
                      value: permInfo.file_mode || '—',
                      mono: true,
                    },
                  ]}
                />
              </>
            )}
            {fixResult && (
              <NoticeCallout
                variant={fixResult.status === 'success' ? 'success' : 'error'}
                message={fixResult.message}
              />
            )}
          </div>
        ) : null}
      </SettingsCard>

      <SudoPasswordDialog
        open={showSudoDialog}
        onOpenChange={setShowSudoDialog}
        title={t('sudo_dialog.fix_app_permissions')}
        description={t('sudo_dialog.fix_permissions_description')}
        submitLabel={t('sudo_dialog.fix_permissions')}
        isSubmitting={fixing}
        error={sudoError}
        onSubmit={fixPermissions}
      />
    </>
  );
}
