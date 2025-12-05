import React from 'react';

interface WebServerFormProps {
  data: any;
  onChange: (data: any) => void;
}

/**
 * Custom form for Web Server section configuration.
 * Fields: port, auth (username, password)
 */
const WebServerForm: React.FC<WebServerFormProps> = ({ data, onChange }) => {
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
          <span className="label-text font-medium">Port</span>
        </label>
        <input
          type="number"
          className="input input-bordered w-full"
          value={data?.port ?? 8090}
          onChange={(e) => handleChange('port', parseInt(e.target.value) || 8090)}
          placeholder="8090"
        />
        <label className="label">
          <span className="label-text-alt text-base-content/60">Port to run web server (default: 8090)</span>
        </label>
      </div>

      {/* Auth Section */}
      <div className="divider">Authentication (optional)</div>

      {/* Username */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">Username</span>
        </label>
        <input
          type="text"
          className="input input-bordered w-full"
          value={data?.auth?.username || ''}
          onChange={(e) => handleAuthChange('username', e.target.value)}
          placeholder="admin"
        />
        <label className="label">
          <span className="label-text-alt text-base-content/60">Username to connect to web interface</span>
        </label>
      </div>

      {/* Password */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">Password</span>
        </label>
        <input
          type="password"
          className="input input-bordered w-full"
          value={data?.auth?.password || ''}
          onChange={(e) => handleAuthChange('password', e.target.value)}
          placeholder="••••••••"
        />
        <label className="label">
          <span className="label-text-alt text-base-content/60">Password to web interface</span>
        </label>
      </div>
    </div>
  );
};

export default WebServerForm;
