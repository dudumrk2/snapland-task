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
 * It sets the global auth store and ensures loading state finishes cleanly.
 */
export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
  const { authApi } = useApi();

  useEffect(() => {
    let cancelled = false;
    useAuthStore.getState().setLoading(true);

    authApi
      .refresh()
      .then((tokens) => {
        if (cancelled) return;
        let user = null;
        if (authApi instanceof MockAuthApi) {
          user = authApi.getCurrentUser();
        }
        useAuthStore.getState().setSession(
          user ?? { id: 'restored', email: '', displayName: 'User' },
          tokens.accessToken
        );
      })
      .catch(() => {
        if (!cancelled) {
          useAuthStore.getState().clearSession();
        }
      })
      .finally(() => {
        if (!cancelled) {
          useAuthStore.getState().setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [authApi]);

  return <AuthContext.Provider value>{children}</AuthContext.Provider>;
};

export const useAuthContext = () => useContext(AuthContext);
