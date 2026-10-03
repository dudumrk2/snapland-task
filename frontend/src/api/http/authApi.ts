import axios, { AxiosInstance } from 'axios';
import type {
  LoginRequest,
  RegisterRequest,
  TokenResponse,
} from '@snapland/shared-types';
import type { IAuthApi, AuthUser } from '../interfaces/IAuthApi';
import { useAuthStore } from '../../store/authStore';

export class AuthApi implements IAuthApi {
  private client: AxiosInstance;
  private refreshPromise: Promise<TokenResponse> | null = null;

  constructor(baseURL: string = '/api/v1') {
    this.client = axios.create({
      baseURL,
      withCredentials: true,
      headers: {
        'Content-Type': 'application/json',
      },
    });
  }

  async login(req: LoginRequest): Promise<TokenResponse> {
    const res = await this.client.post('/auth/login', {
      email: req.email.trim(),
      password: req.password,
    });
    const data = res.data;
    const tokenResponse: TokenResponse = {
      accessToken: data.access_token ?? data.accessToken,
      tokenType: data.token_type ?? data.tokenType ?? 'Bearer',
      expiresIn: data.expires_in ?? data.expiresIn ?? 900,
    };
    return tokenResponse;
  }

  async register(req: RegisterRequest): Promise<TokenResponse> {
    await this.client.post('/auth/register', {
      email: req.email.trim(),
      password: req.password,
      display_name: req.displayName.trim(),
    });
    return this.login({
      email: req.email,
      password: req.password,
    });
  }

  async refresh(): Promise<TokenResponse> {
    if (!this.refreshPromise) {
      this.refreshPromise = this.client
        .post('/auth/refresh')
        .then((res) => {
          const data = res.data;
          const tokenResponse: TokenResponse = {
            accessToken: data.access_token ?? data.accessToken,
            tokenType: data.token_type ?? data.tokenType ?? 'Bearer',
            expiresIn: data.expires_in ?? data.expiresIn ?? 900,
          };
          useAuthStore.getState().setAccessToken(tokenResponse.accessToken);
          return tokenResponse;
        })
        .finally(() => {
          this.refreshPromise = null;
        });
    }
    return this.refreshPromise;
  }

  async logout(): Promise<void> {
    const token = useAuthStore.getState().accessToken;
    const headers: Record<string, string> = {};
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
    try {
      await this.client.post('/auth/logout', null, { headers });
    } finally {
      useAuthStore.getState().clearSession();
    }
  }

  async getWsTicket(): Promise<string> {
    let token = useAuthStore.getState().accessToken;
    if (!token) {
      const refreshed = await this.refresh();
      token = refreshed.accessToken;
    }

    try {
      const res = await this.client.post(
        '/auth/ws-ticket',
        null,
        {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        }
      );
      return res.data.ticket;
    } catch (err: any) {
      if (err?.response?.status === 401) {
        const refreshed = await this.refresh();
        const res = await this.client.post(
          '/auth/ws-ticket',
          null,
          {
            headers: {
              Authorization: `Bearer ${refreshed.accessToken}`,
            },
          }
        );
        return res.data.ticket;
      }
      throw err;
    }
  }

  async getCurrentUser(tokenOverride?: string): Promise<AuthUser | null> {
    const token = tokenOverride || useAuthStore.getState().accessToken;
    if (!token) return null;
    const res = await this.client.get('/users/me', {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });
    const data = res.data;
    return {
      id: String(data.id),
      email: data.email,
      displayName: data.display_name ?? data.displayName ?? data.email.split('@')[0],
    };
  }
}

export const realAuthApi = new AuthApi();
