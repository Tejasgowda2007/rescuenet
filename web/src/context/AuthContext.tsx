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
  enableOfflineEmergencySession: (role?: string) => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

// Configurable backend API base URL for Render/Vercel split deployments
const API_BASE_URL = (import.meta as any).env?.VITE_API_URL || '';

export const AuthProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(() => {
    try {
      const stored = localStorage.getItem('rescuenet_user');
      return stored ? JSON.parse(stored) : null;
    } catch {
      return null;
    }
  });
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
        localStorage.removeItem('rescuenet_user');
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
      const storedUserStr = localStorage.getItem('rescuenet_user');

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
          localStorage.setItem('rescuenet_user', JSON.stringify(data.user));
        } else if (res.status === 401) {
          localStorage.removeItem('rescuenet_token');
          localStorage.removeItem('rescuenet_user');
          setToken(null);
          setUser(null);
        }
      } catch (e) {
        // Network unreachable / offline mode:
        // If a previously authenticated user exists in storage, preserve the offline session
        if (storedUserStr) {
          try {
            const cachedUser = JSON.parse(storedUserStr);
            setUser(cachedUser);
            setToken(storedToken);
            console.log('[Auth] Operating in offline mode with cached operator session:', cachedUser.username);
          } catch {}
        }
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
      localStorage.setItem('rescuenet_user', JSON.stringify(data.user));

      return { success: true };
    } catch (err: any) {
      // Offline fallback: check if logging in with known cached operator offline
      const storedUserStr = localStorage.getItem('rescuenet_user');
      if (storedUserStr) {
        try {
          const cachedUser = JSON.parse(storedUserStr);
          if (cachedUser.username === username.trim()) {
            setUser(cachedUser);
            return { success: true };
          }
        } catch {}
      }
      return { success: false, error: err.message || 'Unable to connect to RescueNet authentication service (Offline).' };
    }
  };

  const enableOfflineEmergencySession = (role: string = 'RESPONDER') => {
    const offlineUser: User = {
      id: `offline-operator-${Date.now()}`,
      username: 'field-responder',
      role: role.toUpperCase(),
      full_name: 'Field Disaster Responder (Offline)',
    };
    const syntheticToken = `offline-token-${Date.now()}`;
    setUser(offlineUser);
    setToken(syntheticToken);
    localStorage.setItem('rescuenet_token', syntheticToken);
    localStorage.setItem('rescuenet_user', JSON.stringify(offlineUser));
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
      localStorage.removeItem('rescuenet_user');
    }
  };

  return (
    <AuthContext.Provider value={{ user, token, isLoading, login, logout, apiFetch, enableOfflineEmergencySession }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
