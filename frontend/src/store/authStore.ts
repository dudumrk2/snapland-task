import { create } from 'zustand';

export interface UserSession {
  id: string;
  email: string;
  displayName: string;
}

export interface AuthState {
  user: UserSession | null;
  accessToken: string | null;
  isAuthenticated: boolean;
  isBootstrapping: boolean; // Only true during initial session restore
  isActionLoading: boolean;  // True during login/register/logout actions
  error: string | null;
  setSession: (user: UserSession, accessToken: string) => void;
  clearSession: () => void;
  setBootstrapping: (isBootstrapping: boolean) => void;
  setActionLoading: (isActionLoading: boolean) => void;
  setError: (error: string | null) => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  accessToken: null,
  isAuthenticated: false,
  isBootstrapping: true,
  isActionLoading: false,
  error: null,
  setSession: (user, accessToken) =>
    set({
      user,
      accessToken,
      isAuthenticated: true,
      isBootstrapping: false,
      isActionLoading: false,
      error: null,
    }),
  clearSession: () =>
    set({
      user: null,
      accessToken: null,
      isAuthenticated: false,
      isBootstrapping: false,
      isActionLoading: false,
      error: null,
    }),
  setBootstrapping: (isBootstrapping) => set({ isBootstrapping }),
  setActionLoading: (isActionLoading) => set({ isActionLoading }),
  setError: (error) => set({ error, isActionLoading: false }),
}));
