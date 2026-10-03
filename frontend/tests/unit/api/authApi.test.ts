import { describe, it, expect, vi, beforeEach } from 'vitest';
import { AuthApi } from '../../../src/api/http/authApi';
import { useAuthStore } from '../../../src/store/authStore';

describe('authApi (HTTP client)', () => {
  let authApi: AuthApi;

  beforeEach(() => {
    vi.restoreAllMocks();
    useAuthStore.getState().clearSession();
    authApi = new AuthApi('/api/v1');
  });

  it('configures withCredentials: true so httpOnly refresh cookie is sent', () => {
    const client = (authApi as any).client;
    expect(client.defaults.withCredentials).toBe(true);
  });

  it('never writes access token to localStorage on login', async () => {
    const setItemSpy = vi.spyOn(Storage.prototype, 'setItem');
    const client = (authApi as any).client;

    vi.spyOn(client, 'post').mockResolvedValueOnce({
      data: {
        access_token: 'jwt-access-123',
        token_type: 'Bearer',
        expires_in: 900,
      },
    });

    const res = await authApi.login({
      email: 'user@snapland.io',
      password: 'password123',
    });

    expect(client.post).toHaveBeenCalledWith('/auth/login', {
      email: 'user@snapland.io',
      password: 'password123',
    });
    expect(res.accessToken).toBe('jwt-access-123');

    // Strict security guarantee: No tokens stored in localStorage!
    expect(setItemSpy).not.toHaveBeenCalled();
  });

  it('register calls POST /auth/register then logs in to return TokenResponse', async () => {
    const client = (authApi as any).client;

    vi.spyOn(client, 'post')
      .mockResolvedValueOnce({
        data: {
          id: 'u-new',
          email: 'new@snapland.io',
          display_name: 'Newbie',
        },
      })
      .mockResolvedValueOnce({
        data: {
          access_token: 'jwt-reg-token',
          token_type: 'Bearer',
          expires_in: 900,
        },
      });

    const res = await authApi.register({
      email: 'new@snapland.io',
      password: 'password123',
      displayName: 'Newbie',
    });

    expect(client.post).toHaveBeenNthCalledWith(1, '/auth/register', {
      email: 'new@snapland.io',
      password: 'password123',
      display_name: 'Newbie',
    });
    expect(client.post).toHaveBeenNthCalledWith(2, '/auth/login', {
      email: 'new@snapland.io',
      password: 'password123',
    });
    expect(res.accessToken).toBe('jwt-reg-token');
  });

  it('refresh calls POST /auth/refresh with cookie and returns TokenResponse', async () => {
    const client = (authApi as any).client;

    vi.spyOn(client, 'post').mockResolvedValueOnce({
      data: {
        access_token: 'jwt-refreshed-token',
        token_type: 'Bearer',
        expires_in: 900,
      },
    });

    const res = await authApi.refresh();
    expect(client.post).toHaveBeenCalledWith('/auth/refresh');
    expect(res.accessToken).toBe('jwt-refreshed-token');
  });

  it('logout calls POST /auth/logout and clears session in authStore', async () => {
    useAuthStore.getState().setSession(
      { id: 'u1', email: 'test@snapland.io', displayName: 'User' },
      'my-token'
    );

    const client = (authApi as any).client;
    vi.spyOn(client, 'post').mockResolvedValueOnce({ data: { status: 'ok' } });

    await authApi.logout();

    expect(client.post).toHaveBeenCalledWith('/auth/logout', null, {
      headers: { Authorization: 'Bearer my-token' },
    });
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
    expect(useAuthStore.getState().accessToken).toBeNull();
  });

  it('getWsTicket calls POST /auth/ws-ticket with Bearer token', async () => {
    useAuthStore.getState().setSession(
      { id: 'u1', email: 'test@snapland.io', displayName: 'User' },
      'valid-jwt-token'
    );

    const client = (authApi as any).client;
    vi.spyOn(client, 'post').mockResolvedValueOnce({
      data: { ticket: 'ws-ticket-abc-123' },
    });

    const ticket = await authApi.getWsTicket();
    expect(client.post).toHaveBeenCalledWith('/auth/ws-ticket', null, {
      headers: { Authorization: 'Bearer valid-jwt-token' },
    });
    expect(ticket).toBe('ws-ticket-abc-123');
  });

  it('getCurrentUser fetches /users/me using Bearer token', async () => {
    useAuthStore.getState().setSession(
      { id: 'u1', email: 'test@snapland.io', displayName: 'User' },
      'valid-jwt-token'
    );

    const client = (authApi as any).client;
    vi.spyOn(client, 'get').mockResolvedValueOnce({
      data: {
        id: 'u1-id',
        email: 'test@snapland.io',
        display_name: 'Dudu Dev',
      },
    });

    const user = await authApi.getCurrentUser();
    expect(client.get).toHaveBeenCalledWith('/users/me', {
      headers: { Authorization: 'Bearer valid-jwt-token' },
    });
    expect(user).toEqual({
      id: 'u1-id',
      email: 'test@snapland.io',
      displayName: 'Dudu Dev',
    });
  });
});
