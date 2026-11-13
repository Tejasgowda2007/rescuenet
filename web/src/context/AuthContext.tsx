import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';

export interface User {
  id: string;
  username: string;
  role: 'ADMIN' | 'COORDINATOR' | 'RESPONDER' | string;
  full_name: string;
}

interface AuthContextType {
  user: User | null;
  token: string | null;
  isLoading: boolean;
  login: (username: string, password: string) => Promise<{ success: boolean; error?: string }>;
  logout: () => Promise<void>;
  apiFetch: (url: string, options?: RequestInit) => Promise<Response>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

// Configurable backend API base URL for Render/Vercel split deployments
const API_BASE_URL = (import.meta as any).env?.VITE_API_URL || '';

export const AuthProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(() => localStorage.getItem('rescuenet_token'));
  const [isLoading, setIsLoading] = useState<boolean>(true);

  // Helper to resolve full API URL
  const resolveUrl = (path: string) => {
    if (path.startsWith('http://') || path.startsWith('https://')) return path;
    const base = API_BASE_URL.replace(/\/+$/, '');
    const cleanPath = path.startsWith('/') ? path : `/${path}`;
    return base ? `${base}${cleanPath}` : cleanPath;
  };

  // Authenticated fetch wrapper
  const apiFetch = async (url: string, options: RequestInit = {}): Promise<Response> => {
    const fullUrl = resolveUrl(url);
    const headers = new Headers(options.headers || {});

    // Attach Bearer token if present
    const currentToken = token || localStorage.getItem('rescuenet_token');
    if (currentToken && !headers.has('Authorization')) {
      headers.set('Authorization', `Bearer ${currentToken}`);
    }

    const mergedOptions: RequestInit = {
      ...options,
      headers,
      credentials: 'include', // Include HttpOnly cookies
    };

    try {
      const response = await fetch(fullUrl, mergedOptions);
      if (response.status === 401 && !url.includes('/api/auth/login')) {
        // Token expired or revoked; invalidate session
        setToken(null);
        setUser(null);
        localStorage.removeItem('rescuenet_token');
      }
      return response;
    } catch (err) {
      throw err;
    }
  };

  // Verify stored session on boot
  useEffect(() => {
    const checkAuth = async () => {
      const storedToken = localStorage.getItem('rescuenet_token');
      if (!storedToken) {
        setIsLoading(false);
        return;
      }

      try {
        const res = await apiFetch('/api/auth/me');
        if (res.ok) {
          const data = await res.json();
          setUser(data.user);
          setToken(storedToken);
        } else {
          localStorage.removeItem('rescuenet_token');
          setToken(null);
          setUser(null);
        }
      } catch (e) {
        // Offline or connection failure; keep token in case it's local
        console.warn('Authentication verify offline or unreachable', e);
      } finally {
        setIsLoading(false);
      }
    };

    checkAuth();
  }, []);

  const login = async (username: string, password: string): Promise<{ success: boolean; error?: string }> => {
    try {
      const res = await fetch(resolveUrl('/api/auth/login'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ username, password }),
      });

      const data = await res.json();

      if (!res.ok) {
        return { success: false, error: data.detail || 'Authentication failed. Please verify credentials.' };
      }

      const receivedToken = data.access_token;
      setToken(receivedToken);
      setUser(data.user);
      localStorage.setItem('rescuenet_token', receivedToken);

      return { success: true };
    } catch (err: any) {
      return { success: false, error: err.message || 'Unable to connect to RescueNet authentication service.' };
    }
  };

  const logout = async (): Promise<void> => {
    try {
      await apiFetch('/api/auth/logout', { method: 'POST' });
    } catch (e) {
      // Ignore network errors on logout
    } finally {
      setToken(null);
      setUser(null);
      localStorage.removeItem('rescuenet_token');
    }
  };

  return (
    <AuthContext.Provider value={{ user, token, isLoading, login, logout, apiFetch }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
