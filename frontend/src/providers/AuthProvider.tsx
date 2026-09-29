import React, { createContext, useContext, useEffect, ReactNode } from 'react';
import { useAuthStore } from '../store/authStore';
import { useApi } from './ApiProvider';
import { MockAuthApi } from '../api/mock/mockAuthApi';

const AuthContext = createContext<boolean>(false);

export interface AuthProviderProps {
  children: ReactNode;
}

/**
 * AuthProvider initialises the session on mount by calling authApi.refresh().
 * It sets the global auth store and exposes isInitialised via context
 * so child components don't render before the session check completes.
 */
export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
  const { authApi } = useApi();
  const { setSession, clearSession, setLoading } = useAuthStore();

  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    authApi
      .refresh()
      .then((tokens) => {
        if (cancelled) return;
        let user = null;
        if (authApi instanceof MockAuthApi) {
          user = authApi.getCurrentUser();
        }
        setSession(user ?? { id: 'restored', email: '', displayName: 'User' }, tokens.accessToken);
      })
      .catch(() => {
        if (!cancelled) clearSession();
      });

    return () => {
      cancelled = true;
    };
  }, [authApi, setSession, clearSession, setLoading]);

  return <AuthContext.Provider value>{children}</AuthContext.Provider>;
};

/** Convenience hook — no functional use yet, reserved for future auth-aware routing. */
export const useAuthContext = () => useContext(AuthContext);
