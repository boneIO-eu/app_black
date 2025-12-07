import React from 'react';
import { useTranslation } from '@/hooks/useTranslation';

interface WebServerFormProps {
  data: any;
  onChange: (data: any) => void;
}

/**
 * Custom form for Web Server section configuration.
 * Fields: port, auth (username, password)
 */
const WebServerForm: React.FC<WebServerFormProps> = ({ data, onChange }) => {
  const { t } = useTranslation();
  const handleChange = (field: string, value: any) => {
    onChange({ ...data, [field]: value });
  };

  const handleAuthChange = (field: string, value: any) => {
    const auth = data?.auth || {};
    const newAuth = { ...auth, [field]: value || undefined };
    
    // Remove auth object if both fields are empty
    if (!newAuth.username && !newAuth.password) {
      const { auth: _, ...rest } = data || {};
      onChange(rest);
    } else {
      onChange({ ...data, auth: newAuth });
    }
  };

  return (
    <div className="space-y-4">
      {/* Port */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('webserver.port')}</span>
        </label>
        <input
          type="number"
          className="input input-bordered w-full"
          value={data?.port ?? 8090}
          onChange={(e) => handleChange('port', parseInt(e.target.value) || 8090)}
          placeholder="8090"
        />
        <label className="label">
          <span className="label-text-alt text-base-content/60">{t('webserver.port_help')}</span>
        </label>
      </div>

      {/* Auth Section */}
      <div className="divider">{t('webserver.auth')}</div>

      {/* Username */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('webserver.username')}</span>
        </label>
        <input
          type="text"
          className="input input-bordered w-full"
          value={data?.auth?.username || ''}
          onChange={(e) => handleAuthChange('username', e.target.value)}
          placeholder="admin"
        />
        <label className="label">
          <span className="label-text-alt text-base-content/60">{t('webserver.username_help')}</span>
        </label>
      </div>

      {/* Password */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('webserver.password')}</span>
        </label>
        <input
          type="password"
          className="input input-bordered w-full"
          value={data?.auth?.password || ''}
          onChange={(e) => handleAuthChange('password', e.target.value)}
          placeholder="••••••••"
        />
        <label className="label">
          <span className="label-text-alt text-base-content/60">{t('webserver.password_help')}</span>
        </label>
      </div>
    </div>
  );
};

export default WebServerForm;
