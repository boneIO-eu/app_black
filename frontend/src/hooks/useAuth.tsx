import { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';
import axios from '@/api/axios';
import { closeWebSocket } from './useWebSocket';

export interface AuthContextType {
  isAuthenticated: boolean;
  isLoading: boolean;
  isAuthRequired: boolean;
  login: (username: string, password: string) => Promise<void>;
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
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isAuthRequired, setIsAuthRequired] = useState(true);

  useEffect(() => {
    const checkAuth = async () => {
      try {
        const response = await axios.get('/api/auth/required');
        setIsAuthRequired(response.data.required);
        console.log("required", response.data.required);
        
        const token = localStorage.getItem('token');
        if (token) {
          // Token is automatically added by axios interceptor from localStorage
          setIsAuthenticated(true);
        }
      } catch (error) {
        console.error('Error checking auth:', error);
      } finally {
        setIsLoading(false);
      }
    };

    checkAuth();
  }, []);

  const login = async (username: string, password: string) => {
    try {
      const response = await axios.post('/api/login', { username, password });
      const { token } = response.data;
      localStorage.setItem('token', token);
      // Token is automatically added by axios interceptor from localStorage
      setIsAuthenticated(true);
    } catch (error) {
      console.error('Login error:', error);
      throw error;
    }
  };

  const logout = useCallback(() => {
    localStorage.removeItem('token');
    // Token removal from localStorage is enough - interceptor reads from localStorage
    closeWebSocket(); // Close WebSocket connection
    setIsAuthenticated(false);
  }, []);

  return (
    <AuthContext.Provider value={{ isAuthenticated, isLoading, isAuthRequired, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}
