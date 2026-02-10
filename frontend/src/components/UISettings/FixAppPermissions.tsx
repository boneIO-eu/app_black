import { useState } from 'react';
import { FaSpinner } from 'react-icons/fa';
import axios from '@/api/axios';

/**
 * Component for diagnosing and fixing app file permissions via sudo.
 * Currently handles docker-compose.yaml; will be extended for sudoers etc.
 */
export default function FixAppPermissions() {
  const [permInfo, setPermInfo] = useState<any>(null);
  const [fixResult, setFixResult] = useState<any>(null);
  const [sudoPass, setSudoPass] = useState('');
  const [loading, setLoading] = useState(false);
  const [fixing, setFixing] = useState(false);

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

  const fixPermissions = async () => {
    if (!sudoPass) return;
    setFixing(true);
    setFixResult(null);
    try {
      const { data } = await axios.post('/api/cloud/fix-permissions', { password: sudoPass });
      setFixResult(data);
      if (data.status === 'success') {
        setSudoPass('');
        testPermissions();
      }
    } catch (err: any) {
      setFixResult({ status: 'error', message: err.response?.data?.detail || err.message || 'Request failed' });
    } finally {
      setFixing(false);
    }
  };

  return (
    <div className="card bg-base-200 shadow-sm mt-4">
      <div className="card-body p-4">
        <h3 className="card-title text-sm">Fix App Permissions</h3>

        <button
          className={`btn btn-sm btn-outline ${loading ? 'loading' : ''}`}
          onClick={testPermissions}
          disabled={loading}
        >
          {loading ? <FaSpinner className="animate-spin" /> : null}
          Check file permissions
        </button>

        {permInfo && (
          <pre className="bg-base-300 p-3 rounded text-xs overflow-x-auto mt-2 whitespace-pre-wrap">
            {JSON.stringify(permInfo, null, 2)}
          </pre>
        )}

        {permInfo && !permInfo.writable && permInfo.file_exists && (
          <div className="flex gap-2 mt-2 items-center">
            <input
              type="password"
              className="input input-bordered input-sm flex-1"
              placeholder="sudo password"
              value={sudoPass}
              onChange={(e) => setSudoPass(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && sudoPass) fixPermissions(); }}
              disabled={fixing}
            />
            <button
              className={`btn btn-sm btn-primary ${fixing ? 'loading' : ''}`}
              onClick={fixPermissions}
              disabled={!sudoPass || fixing}
            >
              {fixing ? <FaSpinner className="animate-spin" /> : 'Fix permissions'}
            </button>
          </div>
        )}

        {fixResult && (
          <pre className={`p-3 rounded text-xs overflow-x-auto mt-2 whitespace-pre-wrap ${fixResult.status === 'success' ? 'bg-success/20' : 'bg-error/20'}`}>
            {JSON.stringify(fixResult, null, 2)}
          </pre>
        )}
      </div>
    </div>
  );
}
