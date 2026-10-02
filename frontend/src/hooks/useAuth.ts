import { useCallback } from 'react';
import type { LoginRequest, RegisterRequest } from '@snapland/shared-types';
import { useApi } from '../providers/ApiProvider';
import { useAuthStore } from '../store/authStore';

export function useAuth() {
  const { authApi } = useApi();
  const {
    user,
    accessToken,
    isAuthenticated,
    isBootstrapping,
    isActionLoading,
    error,
    setSession,
    clearSession,
    setActionLoading,
    setError,
  } = useAuthStore();

  const login = useCallback(
    async (req: LoginRequest) => {
      setActionLoading(true);
      setError(null);
      try {
        const tokens = await authApi.login(req);
        const userProfile = await authApi.getCurrentUser();
        const currentUser = userProfile || {
          id: 'user-1',
          email: req.email,
          displayName: req.email.split('@')[0],
        };
        setSession(currentUser, tokens.accessToken);
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : 'Login failed';
        setError(msg);
        throw err;
      } finally {
        setActionLoading(false);
      }
    },
    [authApi, setSession, setActionLoading, setError]
  );

  const register = useCallback(
    async (req: RegisterRequest) => {
      setActionLoading(true);
      setError(null);
      try {
        await authApi.register(req);
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : 'Registration failed';
        setError(msg);
        throw err;
      } finally {
        setActionLoading(false);
      }
    },
    [authApi, setActionLoading, setError]
  );

  const logout = useCallback(async () => {
    setActionLoading(true);
    try {
      await authApi.logout();
    } finally {
      clearSession();
      setActionLoading(false);
    }
  }, [authApi, clearSession, setActionLoading]);

  return {
    user,
    accessToken,
    isAuthenticated,
    isBootstrapping,
    isLoading: isActionLoading,
    error,
    login,
    register,
    logout,
  };
}
