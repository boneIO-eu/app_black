import { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';
import axios, { UNAUTHORIZED_EVENT } from '@/api/axios';
import { closeWebSocket } from './useWebSocket';
import { useAppInit } from '@/contexts/AppInitContext';

/** Roles the backend can report. Mirrors boneio.core.auth.models.Role. */
export type Role = 'admin' | 'viewer';

export interface AuthContextType {
  isAuthenticated: boolean;
  isLoading: boolean;
  isAuthRequired: boolean;
  /** Username of the signed-in account, null when anonymous access is on. */
  username: string | null;
  /** Role of the signed-in account, null until known or when anonymous. */
  role: Role | null;
  /**
   * Whether the current session may change configuration.
   *
   * A UI hint only — the auth middleware enforces the same policy on every
   * request, so hiding a control is about not offering an action that would
   * fail, never about security. Defaults to false while the role is unknown,
   * so a slow /api/account/me shows fewer controls rather than more.
   */
  isAdmin: boolean;
  login: (username: string, password: string) => Promise<void>;
  /**
   * Adopt a token the backend already issued — used by the first-run wizard,
   * which gets one back when it creates the administrator. Re-sending the
   * password just to obtain a second token would cost another scrypt hash on
   * the device for no benefit.
   */
  loginWithToken: (token: string) => void;
  logout: () => void;
}

interface AuthProviderProps {
  children: ReactNode;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}

export function AuthProvider({ children }: AuthProviderProps) {
  const [isAuthenticated, setIsAuthenticated] = useState(() => !!localStorage.getItem('token'));
  const [isLoading, setIsLoading] = useState(true);
  const [isAuthRequired, setIsAuthRequired] = useState(true);
  const [username, setUsername] = useState<string | null>(null);
  const [role, setRole] = useState<Role | null>(null);
  const { data: initData, isLoading: initLoading } = useAppInit();

  // Ask the backend who we are. The token carries a role claim, but decoding it
  // client-side would mean trusting a value the client can rewrite; asking is
  // both simpler and authoritative.
  const refreshIdentity = useCallback(async () => {
    try {
      const { data } = await axios.get('/api/account/me');
      setUsername(data.username ?? null);
      setRole((data.role as Role) ?? null);
    } catch {
      setUsername(null);
      setRole(null);
    }
  }, []);

  // Read auth_required from /api/init data instead of making a separate call
  useEffect(() => {
    if (initLoading) return;
    if (initData) {
      setIsAuthRequired(initData.auth_required);
      const token = localStorage.getItem('token');
      if (token) {
        setIsAuthenticated(true);
        void refreshIdentity();
      } else if (!initData.auth_required) {
        // Anonymous access is on; there is no account to describe.
        void refreshIdentity();
      }
      setIsLoading(false);
    } else {
      // Fallback if init data is not available
      setIsLoading(false);
    }
  }, [initData, initLoading, refreshIdentity]);

  const login = async (username: string, password: string) => {
    try {
      const response = await axios.post('/api/login', { username, password });
      const { token } = response.data;
      localStorage.setItem('token', token);
      // Token is automatically added by axios interceptor from localStorage
      setIsAuthenticated(true);
      setUsername(response.data.username ?? null);
      setRole((response.data.role as Role) ?? null);
    } catch (error) {
      console.error('Login error:', error);
      throw error;
    }
  };

  const loginWithToken = useCallback((token: string) => {
    localStorage.setItem('token', token);
    setIsAuthenticated(true);
    setIsAuthRequired(true);
    void refreshIdentity();
  }, [refreshIdentity]);

  // A rejected token must end the session, or the UI sits in a half-signed-in
  // state: no token on the wire, every view empty, and no login prompt.
  useEffect(() => {
    const onUnauthorized = () => {
      closeWebSocket();
      setIsAuthenticated(false);
      setUsername(null);
      setRole(null);
    };
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem('token');
    // Token removal from localStorage is enough - interceptor reads from localStorage
    closeWebSocket(); // Close WebSocket connection
    setIsAuthenticated(false);
    setUsername(null);
    setRole(null);
  }, []);

  return (
    <AuthContext.Provider value={{
        isAuthenticated,
        isLoading,
        isAuthRequired,
        username,
        role,
        isAdmin: role === 'admin',
        login,
        loginWithToken,
        logout,
      }}>
      {children}
    </AuthContext.Provider>
  );
}
