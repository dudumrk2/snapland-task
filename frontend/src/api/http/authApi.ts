import type {
  LoginRequest,
  RegisterRequest,
  TokenResponse,
} from '@snapland/shared-types';
import { IAuthApi, AuthUser } from '../interfaces/IAuthApi';
import { apiClient, registerRefreshHandler } from './client';
import { useAuthStore } from '../../store/authStore';

export class RealAuthApi implements IAuthApi {
  constructor() {
    // Register the refresh handler with axios client so 401 interceptor can invoke it
    registerRefreshHandler(async () => {
      try {
        const res = await this.refresh();
        return res.accessToken;
      } catch {
        return null;
      }
    });
  }

  async login(req: LoginRequest): Promise<TokenResponse> {
    const response = await apiClient.post<{
      access_token: string;
      token_type?: string;
      expires_in?: number;
    }>('/api/v1/auth/login', {
      email: req.email.trim(),
      password: req.password,
    });

    const tokenResponse: TokenResponse = {
      accessToken: response.data.access_token,
      tokenType: response.data.token_type || 'Bearer',
      expiresIn: response.data.expires_in || 900,
    };

    // Temporarily set accessToken in store so getCurrentUser request has Bearer token
    useAuthStore.setState({ accessToken: tokenResponse.accessToken });

    // Fetch user profile — required to establish a valid session.
    // If this fails we must not silently store a synthetic user id.
    const user = await this.getCurrentUser();
    if (!user) {
      throw new Error('Login succeeded but user profile could not be retrieved. Please try again.');
    }
    useAuthStore.getState().setSession(user, tokenResponse.accessToken);

    return tokenResponse;
  }

  async register(req: RegisterRequest): Promise<void> {
    await apiClient.post<unknown>('/api/v1/auth/register', {
      email: req.email.trim(),
      password: req.password,
      display_name: req.displayName.trim(),
    });
  }

  async refresh(): Promise<TokenResponse> {
    // Cookie is sent automatically via withCredentials: true.
    // Refresh token is NEVER read or stored in JavaScript / localStorage.
    const response = await apiClient.post<{
      access_token: string;
      token_type?: string;
      expires_in?: number;
    }>('/api/v1/auth/refresh');

    const tokenResponse: TokenResponse = {
      accessToken: response.data.access_token,
      tokenType: response.data.token_type || 'Bearer',
      expiresIn: response.data.expires_in || 900,
    };

    // Keep access token in memory (authStore)
    useAuthStore.setState({ accessToken: tokenResponse.accessToken });

    return tokenResponse;
  }

  async logout(): Promise<void> {
    try {
      await apiClient.post('/api/v1/auth/logout');
    } finally {
      useAuthStore.getState().clearSession();
    }
  }

  async getWsTicket(): Promise<string> {
    const response = await apiClient.post<{ ticket: string }>(
      '/api/v1/auth/ws-ticket'
    );
    return response.data.ticket;
  }

  async getCurrentUser(): Promise<AuthUser | null> {
    try {
      const response = await apiClient.get<{
        id: string;
        email: string;
        display_name: string;
      }>('/api/v1/users/me');

      return {
        id: response.data.id,
        email: response.data.email,
        displayName: response.data.display_name,
      };
    } catch {
      return null;
    }
  }
}

export const realAuthApi = new RealAuthApi();
