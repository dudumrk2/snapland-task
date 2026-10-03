import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { RealAreaApi, mapServerVersionToVersion } from '../../../src/api/http/areaApi';
import { RealAuthApi } from '../../../src/api/http/authApi';
import { apiClient, mapServerAreaToArea, registerRefreshHandler } from '../../../src/api/http/client';
import { ConflictError } from '../../../src/api/interfaces/IAreaApi';
import { useAuthStore } from '../../../src/store/authStore';

describe('HTTP API & Mapping', () => {
  beforeEach(() => {
    useAuthStore.getState().clearSession();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    registerRefreshHandler(null);
  });

  it('maps server area snake_case to frontend Area camelCase', () => {
    const serverArea = {
      id: 'area-uuid-1',
      name: 'Test Area',
      coordinates: [{ lat: 32.1, lng: 34.8 }],
      area_km2: 12.34,
      version: 2,
      created_by: 'user-1',
      last_edited_by: 'user-2',
      created_at: '2026-01-01T12:00:00Z',
      updated_at: '2026-01-02T12:00:00Z',
    };

    const area = mapServerAreaToArea(serverArea);
    expect(area.id).toBe('area-uuid-1');
    expect(area.name).toBe('Test Area');
    expect(area.areaKm2).toBe(12.34);
    expect(area.version).toBe(2);
    expect(area.createdBy).toBe('user-1');
    expect(area.lastEditedBy).toBe('user-2');
    expect(area.createdAt).toBe('2026-01-01T12:00:00Z');
    expect(area.updatedAt).toBe('2026-01-02T12:00:00Z');
  });

  it('maps server version to frontend AreaVersion', () => {
    const serverVersion = {
      version_number: 3,
      edited_by: 'user-123',
      change_type: 'update',
      area_km2: 4.56,
      created_at: '2026-01-01T10:00:00Z',
      diff: { name: 'old' },
    };

    const version = mapServerVersionToVersion(serverVersion);
    expect(version.versionNumber).toBe(3);
    expect(version.editedBy).toBe('user-123');
    expect(version.changeType).toBe('update');
    expect(version.areaKm2).toBe(4.56);
  });

  it('getAreasInBounds maps response to AreasPage', async () => {
    const areaApi = new RealAreaApi();
    vi.spyOn(apiClient, 'get').mockResolvedValue({
      data: {
        areas: [
          {
            id: 'area-1',
            name: 'A1',
            coordinates: [{ lat: 32, lng: 34 }],
            area_km2: 5.0,
            version: 1,
            created_by: 'u1',
            last_edited_by: 'u1',
            created_at: '2026-01-01T00:00:00Z',
            updated_at: '2026-01-01T00:00:00Z',
          },
        ],
        truncated: false,
      },
    });

    const page = await areaApi.getAreasInBounds(
      { minLng: 34.0, minLat: 31.0, maxLng: 35.0, maxLat: 32.0 },
      12
    );

    expect(page.areas).toHaveLength(1);
    expect(page.areas[0].areaKm2).toBe(5.0);
    expect(page.truncated).toBe(false);
  });

  it('createArea sends coordinates and name', async () => {
    const areaApi = new RealAreaApi();
    const postSpy = vi.spyOn(apiClient, 'post').mockResolvedValue({
      data: {
        id: 'new-id',
        name: 'New Polygon',
        coordinates: [{ lat: 32, lng: 34 }],
        area_km2: 2.1,
        version: 1,
        created_by: 'u1',
        last_edited_by: 'u1',
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      },
    });

    const created = await areaApi.createArea({
      name: 'New Polygon',
      coordinates: [{ lat: 32, lng: 34 }],
      shapeId: 'shape-123',
    });

    expect(created.id).toBe('new-id');
    expect(postSpy).toHaveBeenCalledWith(
      '/api/v1/areas',
      expect.objectContaining({
        name: 'New Polygon',
        shape_id: 'shape-123',
      })
    );
  });

  it('authApi login sets session with user and access token', async () => {
    const authApi = new RealAuthApi();
    vi.spyOn(apiClient, 'post').mockResolvedValue({
      data: {
        access_token: 'jwt-token-123',
        token_type: 'Bearer',
        expires_in: 900,
      },
    });
    vi.spyOn(apiClient, 'get').mockResolvedValue({
      data: {
        id: 'user-1',
        email: 'user@example.com',
        display_name: 'User 1',
      },
    });

    const tokenResponse = await authApi.login({
      email: 'user@example.com',
      password: 'password123',
    });

    expect(tokenResponse.accessToken).toBe('jwt-token-123');
    expect(useAuthStore.getState().isAuthenticated).toBe(true);
    expect(useAuthStore.getState().accessToken).toBe('jwt-token-123');
    expect(useAuthStore.getState().user?.email).toBe('user@example.com');
  });

  it('authApi getWsTicket calls POST /auth/ws-ticket', async () => {
    const authApi = new RealAuthApi();
    vi.spyOn(apiClient, 'post').mockResolvedValue({
      data: { ticket: 'ticket-xyz-456' },
    });

    const ticket = await authApi.getWsTicket();
    expect(ticket).toBe('ticket-xyz-456');
  });

  it('deduplicates concurrent 401s into a single refresh call', async () => {
    let refreshCount = 0;
    registerRefreshHandler(async () => {
      refreshCount++;
      await new Promise((r) => setTimeout(r, 10));
      return 'refreshed-token-abc';
    });

    vi.spyOn(apiClient, 'request').mockResolvedValue({ data: { success: true } });

    const rejectedHandler = (apiClient.interceptors.response as unknown as {
      handlers: Array<{ rejected: (err: unknown) => Promise<unknown> }>;
    }).handlers[0].rejected;

    const mockAdapter = async (config: unknown) => ({
      data: { success: true },
      status: 200,
      statusText: 'OK',
      headers: {},
      config,
    });

    const req1 = { headers: {} as Record<string, string>, url: '/api/v1/areas/1', adapter: mockAdapter };
    const req2 = { headers: {} as Record<string, string>, url: '/api/v1/areas/2', adapter: mockAdapter };

    // Fire two 401s concurrently
    const p1 = rejectedHandler({ config: req1, response: { status: 401 } });
    const p2 = rejectedHandler({ config: req2, response: { status: 401 } });

    await Promise.allSettled([p1, p2]);

    expect(refreshCount).toBe(1);
    expect(req1.headers.Authorization).toBe('Bearer refreshed-token-abc');
    expect(req2.headers.Authorization).toBe('Bearer refreshed-token-abc');
  });
});
