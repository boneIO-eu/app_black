import axios from 'axios';
import { getBasePath } from './basePath';

const baseURL = getBasePath();

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
      // Clear token and redirect to login
      localStorage.removeItem('token');
      console.log("Error 401", error)
    }
    return Promise.reject(error);
  }
);

export default axiosInstance;
