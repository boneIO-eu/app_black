import { useState } from 'react';
import { FaSpinner } from 'react-icons/fa';
import axios from '@/api/axios';
import { useTranslation } from '@/hooks/useTranslation';
import SudoPasswordDialog from './SudoPasswordDialog';

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
    <div className="card bg-base-200 shadow-sm mt-4">
      <div className="card-body p-4">
        <h3 className="card-title text-sm">{t('sudo_dialog.fix_app_permissions')}</h3>

        <button
          className={`btn btn-sm btn-outline ${loading ? 'loading' : ''}`}
          onClick={testPermissions}
          disabled={loading}
        >
          {loading ? <FaSpinner className="animate-spin" /> : null}
          {t('sudo_dialog.check_file_permissions')}
        </button>

        {permInfo && (
          <pre className="bg-base-300 p-3 rounded text-xs overflow-x-auto mt-2 whitespace-pre-wrap">
            {JSON.stringify(permInfo, null, 2)}
          </pre>
        )}

        {permInfo && !permInfo.writable && permInfo.file_exists && (
          <button
            className="btn btn-sm btn-primary mt-2"
            onClick={() => {
              setSudoError(null);
              setShowSudoDialog(true);
            }}
          >
            {t('sudo_dialog.fix_permissions')}
          </button>
        )}

        {fixResult && (
          <pre className={`p-3 rounded text-xs overflow-x-auto mt-2 whitespace-pre-wrap ${fixResult.status === 'success' ? 'bg-success/20' : 'bg-error/20'}`}>
            {JSON.stringify(fixResult, null, 2)}
          </pre>
        )}
      </div>

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
    </div>
  );
}
