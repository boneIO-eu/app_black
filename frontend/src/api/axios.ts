import axios from 'axios';
import { getBasePath } from './basePath';

const baseURL = getBasePath();

/** Fired when the backend rejects our token, so the session can be reset. */
export const UNAUTHORIZED_EVENT = 'boneio:unauthorized';

const axiosInstance = axios.create({
  baseURL,
  timeout: 5000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add a request interceptor to add the token
axiosInstance.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Add a response interceptor to handle errors and invalidate config cache
axiosInstance.interceptors.response.use(
  (response) => {
    // Auto-invalidate config cache on any mutating request to config endpoints.
    // This covers UISettings, ConfigEditorUI, TeachMode, QuickActionSheet, etc.
    const method = response.config.method?.toLowerCase();
    const url = response.config.url || '';
    if (
      (method === 'put' || method === 'post' || method === 'delete') &&
      (url.includes('/api/config') || url.includes('/api/pwa_name'))
    ) {
      // Lazy import to avoid circular dependency (configCache imports axios)
      import('./configCache').then(({ invalidateConfigCache }) => {
        invalidateConfigCache();
      });
    }
    return response;
  },
  (error) => {
    if (error.response?.status === 401) {
      // Drop the dead token AND tell the auth layer, which owns the React
      // state. Clearing storage alone left the app believing it was signed in:
      // every later request went out without a token, so views came back
      // empty and role-gated controls vanished, while the login screen never
      // appeared because isAuthenticated was still true.
      //
      // An event rather than an import: useAuth imports axios, so calling into
      // it from here would be circular.
      localStorage.removeItem('token');
      window.dispatchEvent(new CustomEvent(UNAUTHORIZED_EVENT));
    }
    return Promise.reject(error);
  }
);

export default axiosInstance;
