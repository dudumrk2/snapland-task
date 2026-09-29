import type {
  LoginRequest,
  RegisterRequest,
  TokenResponse,
} from '@snapland/shared-types';
import { IAuthApi } from '../interfaces/IAuthApi';

interface StoredUser {
  id: string;
  email: string;
  password: string;
  displayName: string;
}

const STORAGE_SESSION_KEY = 'snapland_mock_session';

export class MockAuthApi implements IAuthApi {
  private users: Map<string, StoredUser> = new Map();
  private simulatedLatencyMs = 50;

  constructor() {
    // Seed default test user
    this.users.set('test@example.com', {
      id: 'user-default-1',
      email: 'test@example.com',
      password: 'password123',
      displayName: 'Test User',
    });
  }

  private async delay(): Promise<void> {
    if (this.simulatedLatencyMs > 0) {
      await new Promise((resolve) => setTimeout(resolve, this.simulatedLatencyMs));
    }
  }

  async login(req: LoginRequest): Promise<TokenResponse> {
    await this.delay();
    const user = this.users.get(req.email.toLowerCase().trim());
    if (!user || user.password !== req.password) {
      throw new Error('Invalid email or password');
    }

    const tokenResponse: TokenResponse = {
      accessToken: `mock-jwt-${user.id}-${Date.now()}`,
      tokenType: 'Bearer',
      expiresIn: 900,
    };

    if (typeof window !== 'undefined' && window.localStorage) {
      window.localStorage.setItem(
        STORAGE_SESSION_KEY,
        JSON.stringify({
          user: { id: user.id, email: user.email, displayName: user.displayName },
          accessToken: tokenResponse.accessToken,
        })
      );
    }

    return tokenResponse;
  }

  async register(req: RegisterRequest): Promise<TokenResponse> {
    await this.delay();
    const emailKey = req.email.toLowerCase().trim();
    if (this.users.has(emailKey)) {
      throw new Error('User already exists with this email');
    }

    const id = `user-${Date.now()}`;
    const newUser: StoredUser = {
      id,
      email: emailKey,
      password: req.password,
      displayName: req.displayName.trim() || 'User',
    };
    this.users.set(emailKey, newUser);

    const tokenResponse: TokenResponse = {
      accessToken: `mock-jwt-${id}-${Date.now()}`,
      tokenType: 'Bearer',
      expiresIn: 900,
    };

    if (typeof window !== 'undefined' && window.localStorage) {
      window.localStorage.setItem(
        STORAGE_SESSION_KEY,
        JSON.stringify({
          user: { id: newUser.id, email: newUser.email, displayName: newUser.displayName },
          accessToken: tokenResponse.accessToken,
        })
      );
    }

    return tokenResponse;
  }

  async refresh(): Promise<TokenResponse> {
    await this.delay();
    if (typeof window !== 'undefined' && window.localStorage) {
      const stored = window.localStorage.getItem(STORAGE_SESSION_KEY);
      if (stored) {
        try {
          const parsed = JSON.parse(stored);
          if (parsed && parsed.user && parsed.accessToken) {
            return {
              accessToken: parsed.accessToken,
              tokenType: 'Bearer',
              expiresIn: 900,
            };
          }
        } catch {
          // ignore corrupted json
        }
      }
    }

    throw new Error('No active session to refresh');
  }

  getCurrentUser(): { id: string; email: string; displayName: string } | null {
    if (typeof window !== 'undefined' && window.localStorage) {
      const stored = window.localStorage.getItem(STORAGE_SESSION_KEY);
      if (stored) {
        try {
          const parsed = JSON.parse(stored);
          return parsed.user || null;
        } catch {
          return null;
        }
      }
    }
    return null;
  }

  async logout(): Promise<void> {
    await this.delay();
    if (typeof window !== 'undefined' && window.localStorage) {
      window.localStorage.removeItem(STORAGE_SESSION_KEY);
    }
  }

  async getWsTicket(): Promise<string> {
    await this.delay();
    return `ws-ticket-${Date.now()}-${Math.random().toString(36).substring(2, 8)}`;
  }
}

export const mockAuthApi = new MockAuthApi();
