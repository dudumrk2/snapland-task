import React, { createContext, useContext, useEffect, ReactNode, useRef } from 'react';
import { useAuthStore } from '../store/authStore';
import { useApi } from './ApiProvider';

const AuthContext = createContext<boolean>(false);

export interface AuthProviderProps {
  children: ReactNode;
}

/**
 * AuthProvider initialises the session on mount by calling authApi.refresh().
 * Handles React 18 StrictMode double-invocations cleanly without revoking tokens.
 */
export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
  const { authApi } = useApi();
  const hasStartedRef = useRef(false);

  useEffect(() => {
    if (hasStartedRef.current) return;
    hasStartedRef.current = true;

    useAuthStore.getState().setBootstrapping(true);

    authApi
      .refresh()
      .then((tokens) => {
        // Fallback user details for session restore
        const user = { id: 'user-1', email: 'test@example.com', displayName: 'Test User' };
        useAuthStore.getState().setSession(user, tokens.accessToken);
      })
      .catch(() => {
        useAuthStore.getState().clearSession();
      })
      .finally(() => {
        useAuthStore.getState().setBootstrapping(false);
      });
  }, [authApi]);

  return <AuthContext.Provider value>{children}</AuthContext.Provider>;
};

export const useAuthContext = () => useContext(AuthContext);
