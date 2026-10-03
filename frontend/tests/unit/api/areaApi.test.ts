import { describe, it, expect, vi, beforeEach } from 'vitest';
import axios from 'axios';
import { AreaApi, normalizeArea, normalizeAreaVersion } from '../../../src/api/http/areaApi';
import { ConflictError } from '../../../src/api/interfaces/IAreaApi';
import { useAuthStore } from '../../../src/store/authStore';
import type { IAuthApi } from '../../../src/api/interfaces/IAuthApi';

describe('areaApi (HTTP client)', () => {
  let mockAuthApi: IAuthApi;
  let areaApi: AreaApi;

  beforeEach(() => {
    vi.restoreAllMocks();
    useAuthStore.getState().clearSession();

    mockAuthApi = {
      login: vi.fn(),
      register: vi.fn(),
      refresh: vi.fn().mockResolvedValue({
        accessToken: 'new-token-123',
        tokenType: 'Bearer',
        expiresIn: 900,
      }),
      logout: vi.fn(),
      getWsTicket: vi.fn().mockResolvedValue('test-ticket'),
      getCurrentUser: vi.fn().mockResolvedValue({
        id: 'u1',
        email: 'user@test.com',
        displayName: 'User',
      }),
    };

    areaApi = new AreaApi(mockAuthApi, '/api/v1/areas');
  });

  describe('Normalization', () => {
    it('normalizes snake_case backend area to camelCase Area', () => {
      const raw = {
        id: '123',
        name: 'Zone Alpha',
        coordinates: [{ lat: 32.1, lng: 34.8 }],
        area_km2: 1.45,
        version: 2,
        created_by: 'user-1',
        last_edited_by: 'user-2',
        created_at: '2026-10-01T00:00:00Z',
        updated_at: '2026-10-02T00:00:00Z',
      };
      const normalized = normalizeArea(raw);

      expect(normalized.id).toBe('123');
      expect(normalized.name).toBe('Zone Alpha');
      expect(normalized.areaKm2).toBe(1.45);
      expect(normalized.version).toBe(2);
      expect(normalized.createdBy).toBe('user-1');
      expect(normalized.lastEditedBy).toBe('user-2');
    });

    it('normalizes snake_case AreaVersion to camelCase', () => {
      const raw = {
        version_number: 3,
        edited_by: 'user-9',
        change_type: 'update',
        area_km2: 2.1,
        created_at: '2026-10-01T00:00:00Z',
        diff: { geomChanged: true },
      };
      const normalized = normalizeAreaVersion(raw);

      expect(normalized.versionNumber).toBe(3);
      expect(normalized.editedBy).toBe('user-9');
      expect(normalized.changeType).toBe('update');
      expect(normalized.areaKm2).toBe(2.1);
    });
  });

  describe('CRUD operations & query building', () => {
    it('getAreasInBounds calls GET / with bounds and zoom params and maps to AreasPage', async () => {
      const client = (areaApi as any).client;
      vi.spyOn(client, 'get').mockResolvedValueOnce({
        data: {
          areas: [
            {
              id: 'a1',
              name: 'Area 1',
              coordinates: [{ lat: 32, lng: 34 }],
              area_km2: 0.5,
              version: 1,
            },
          ],
          truncated: false,
        },
      });

      const page = await areaApi.getAreasInBounds(
        { minLng: 34.0, minLat: 31.0, maxLng: 35.0, maxLat: 32.0 },
        12
      );

      expect(client.get).toHaveBeenCalledWith('', {
        params: {
          bounds: '34,31,35,32',
          zoom: 12,
          limit: 500,
        },
      });
      expect(page.areas.length).toBe(1);
      expect(page.areas[0].id).toBe('a1');
      expect(page.areas[0].areaKm2).toBe(0.5);
      expect(page.truncated).toBe(false);
    });

    it('createArea calls POST / with name and coordinates', async () => {
      const client = (areaApi as any).client;
      vi.spyOn(client, 'post').mockResolvedValueOnce({
        data: {
          id: 'new-id',
          name: 'My Polygon',
          coordinates: [{ lat: 32, lng: 34 }],
          area_km2: 1.2,
          version: 1,
        },
      });

      const created = await areaApi.createArea({
        name: 'My Polygon',
        coordinates: [{ lat: 32, lng: 34 }],
      });

      expect(client.post).toHaveBeenCalledWith('', {
        name: 'My Polygon',
        coordinates: [{ lat: 32, lng: 34 }],
      });
      expect(created.id).toBe('new-id');
      expect(created.areaKm2).toBe(1.2);
    });

    it('updateArea calls PUT /:id with version, name and coordinates', async () => {
      const client = (areaApi as any).client;
      vi.spyOn(client, 'put').mockResolvedValueOnce({
        data: {
          id: 'area-123',
          name: 'Updated Name',
          coordinates: [{ lat: 32, lng: 34 }],
          area_km2: 1.5,
          version: 2,
        },
      });

      const updated = await areaApi.updateArea('area-123', {
        version: 1,
        name: 'Updated Name',
        coordinates: [{ lat: 32, lng: 34 }],
      });

      expect(client.put).toHaveBeenCalledWith('/area-123', {
        version: 1,
        name: 'Updated Name',
        coordinates: [{ lat: 32, lng: 34 }],
      });
      expect(updated.version).toBe(2);
    });

    it('deleteArea calls DELETE /:id', async () => {
      const client = (areaApi as any).client;
      vi.spyOn(client, 'delete').mockResolvedValueOnce({ data: { status: 'ok' } });

      await areaApi.deleteArea('area-999');
      expect(client.delete).toHaveBeenCalledWith('/area-999');
    });

    it('getAreaHistory calls GET /:id/history', async () => {
      const client = (areaApi as any).client;
      vi.spyOn(client, 'get').mockResolvedValueOnce({
        data: [
          {
            version_number: 1,
            edited_by: 'u1',
            change_type: 'create',
            area_km2: 1.0,
            diff: {},
          },
        ],
      });

      const history = await areaApi.getAreaHistory('area-1');
      expect(client.get).toHaveBeenCalledWith('/area-1/history');
      expect(history.length).toBe(1);
      expect(history[0].versionNumber).toBe(1);
    });
  });

  describe('Interceptors and error handling', () => {
    it('injects Bearer token in request header from authStore', async () => {
      useAuthStore.getState().setSession(
        { id: 'u1', email: 'test@snapland.io', displayName: 'Tester' },
        'secret-token-xyz'
      );

      const client = (areaApi as any).client;
      vi.spyOn(client, 'request').mockResolvedValueOnce({
        data: { id: 'a1', name: 'A', coordinates: [], area_km2: 1, version: 1 },
      });

      // Execute request interceptor manually or via mock
      const interceptor = client.interceptors.request.handlers[0].fulfilled;
      const config = interceptor({ headers: {} });
      expect(config.headers.Authorization).toBe('Bearer secret-token-xyz');
    });

    it('on 401: calls authApi.refresh() once, updates token, and retries the request', async () => {
      const client = (areaApi as any).client;

      // Mock client(originalRequest) retry
      const retryResponse = {
        data: { id: 'retry-success', name: 'Area', coordinates: [], area_km2: 1, version: 1 },
      };
      const clientCallable = vi.fn().mockResolvedValue(retryResponse);
      (areaApi as any).client = clientCallable;
      Object.assign(clientCallable, client);

      const error401 = {
        response: { status: 401 },
        config: { headers: {}, _retry: false },
      };

      const responseInterceptor = client.interceptors.response.handlers[0].rejected;
      const result = await responseInterceptor(error401);

      expect(mockAuthApi.refresh).toHaveBeenCalledTimes(1);
      expect(error401.config.headers['Authorization']).toBe('Bearer new-token-123');
      expect(result).toBe(retryResponse);
    });

    it('on 409 (Conflict): throws ConflictError carrying currentArea and currentVersion', async () => {
      const client = (areaApi as any).client;
      const responseInterceptor = client.interceptors.response.handlers[0].rejected;

      const error409 = {
        response: {
          status: 409,
          data: {
            error: 'CONFLICT',
            message: 'OCC Version Mismatch',
            details: {
              current_version: 5,
              current_area: {
                id: 'area-occ',
                name: 'Server Area',
                coordinates: [{ lat: 31, lng: 35 }],
                area_km2: 2.5,
                version: 5,
                created_by: 'u1',
                last_edited_by: 'u2',
              },
            },
          },
        },
        config: { headers: {} },
      };

      await expect(responseInterceptor(error409)).rejects.toThrow(ConflictError);

      try {
        await responseInterceptor(error409);
      } catch (err: any) {
        expect(err.name).toBe('ConflictError');
        expect(err.currentVersion).toBe(5);
        expect(err.currentArea.id).toBe('area-occ');
        expect(err.currentArea.areaKm2).toBe(2.5);
      }
    });

    it('on 429: parses Retry-After header and dispatches snapland:toast event without auto-retrying', async () => {
      const client = (areaApi as any).client;
      const responseInterceptor = client.interceptors.response.handlers[0].rejected;

      const toastListener = vi.fn();
      window.addEventListener('snapland:toast', toastListener);

      const error429 = {
        response: {
          status: 429,
          headers: { 'retry-after': '45' },
          data: {
            error: 'RATE_LIMITED',
            details: { retryAfterMs: 45000 },
          },
        },
        config: { headers: {} },
      };

      await expect(responseInterceptor(error429)).rejects.toBe(error429);
      expect(toastListener).toHaveBeenCalled();
      const customEvent = toastListener.mock.calls[0][0] as CustomEvent;
      expect(customEvent.detail.message).toContain('45s');

      window.removeEventListener('snapland:toast', toastListener);
    });
  });
});
