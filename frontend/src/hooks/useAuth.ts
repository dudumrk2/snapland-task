import { useCallback } from 'react';
import type { LoginRequest, RegisterRequest } from '@snapland/shared-types';
import { useApi } from '../providers/ApiProvider';
import { useAuthStore } from '../store/authStore';
import { MockAuthApi } from '../api/mock/mockAuthApi';

export function useAuth() {
  const { authApi } = useApi();
  const {
    user,
    accessToken,
    isAuthenticated,
    isLoading,
    error,
    setSession,
    clearSession,
    setLoading,
    setError,
  } = useAuthStore();

  const initAuth = useCallback(async () => {
    setLoading(true);
    try {
      const tokens = await authApi.refresh();
      let currentUser = null;
      if (authApi instanceof MockAuthApi) {
        currentUser = authApi.getCurrentUser();
      }
      if (!currentUser) {
        currentUser = {
          id: 'restored-user',
          email: 'user@example.com',
          displayName: 'Authenticated User',
        };
      }
      setSession(currentUser, tokens.accessToken);
    } catch {
      clearSession();
    } finally {
      setLoading(false);
    }
  }, [authApi, setSession, clearSession, setLoading]);

  const login = useCallback(
    async (req: LoginRequest) => {
      setLoading(true);
      setError(null);
      try {
        const tokens = await authApi.login(req);
        let currentUser = null;
        if (authApi instanceof MockAuthApi) {
          currentUser = authApi.getCurrentUser();
        }
        if (!currentUser) {
          currentUser = {
            id: 'user-1',
            email: req.email,
            displayName: req.email.split('@')[0],
          };
        }
        setSession(currentUser, tokens.accessToken);
      } catch (err: any) {
        setError(err.message || 'Login failed');
        throw err;
      } finally {
        setLoading(false);
      }
    },
    [authApi, setSession, setLoading, setError]
  );

  const register = useCallback(
    async (req: RegisterRequest) => {
      setLoading(true);
      setError(null);
      try {
        const tokens = await authApi.register(req);
        let currentUser = null;
        if (authApi instanceof MockAuthApi) {
          currentUser = authApi.getCurrentUser();
        }
        if (!currentUser) {
          currentUser = {
            id: 'user-new',
            email: req.email,
            displayName: req.displayName,
          };
        }
        setSession(currentUser, tokens.accessToken);
      } catch (err: any) {
        setError(err.message || 'Registration failed');
        throw err;
      } finally {
        setLoading(false);
      }
    },
    [authApi, setSession, setLoading, setError]
  );

  const logout = useCallback(async () => {
    setLoading(true);
    try {
      await authApi.logout();
    } finally {
      clearSession();
      setLoading(false);
    }
  }, [authApi, clearSession, setLoading]);

  return {
    user,
    accessToken,
    isAuthenticated,
    isLoading,
    error,
    login,
    register,
    logout,
    initAuth,
  };
}
