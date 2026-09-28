import os

files = {
    "frontend/src/api/interfaces/IAreaApi.ts": """
import type { Area, AreasPage, AreaVersion, CreateAreaRequest, UpdateAreaRequest, BoundingBox } from '@snapland/shared-types';

export interface IAreaApi {
  getAreasInBounds(bounds: BoundingBox, zoom: number): Promise<AreasPage>;
  getAreaById(id: string): Promise<Area>;
  createArea(req: CreateAreaRequest): Promise<Area>;
  updateArea(id: string, req: UpdateAreaRequest): Promise<Area>;
  deleteArea(id: string): Promise<void>;
  getAreaHistory(id: string): Promise<AreaVersion[]>;
}
""",
    "frontend/src/api/interfaces/IWebSocketService.ts": """
import type { WsMessage, ClientMessageType, ServerMessageType } from '@snapland/shared-types';

export type ConnectionState = 'connecting' | 'connected' | 'reconnecting' | 'polling' | 'disconnected';
export type MessageHandler<T extends ServerMessageType> = (payload: WsMessage<T>['payload'], eventId?: string) => void;

export interface IWebSocketService {
  connect(ticketProvider: () => Promise<string>): void;
  disconnect(): void;
  send<T extends ClientMessageType>(message: WsMessage<T>): void;
  on<T extends ServerMessageType>(type: T, handler: MessageHandler<T>): () => void;
  onStateChange(handler: (state: ConnectionState) => void): () => void;
  readonly connectionState: ConnectionState;
  readonly lastEventId: string | null;
}
""",
    "frontend/src/api/interfaces/IAuthApi.ts": """
import type { LoginRequest, RegisterRequest, TokenResponse } from '@snapland/shared-types';

export interface IAuthApi {
  login(req: LoginRequest): Promise<TokenResponse>;
  register(req: RegisterRequest): Promise<TokenResponse>;
  refresh(): Promise<TokenResponse>;
  logout(): Promise<void>;
  getWsTicket(): Promise<string>;
}
""",
    "frontend/src/api/mock/mockAreaApi.ts": """
import { IAreaApi } from '../interfaces/IAreaApi';
import type { Area, AreasPage, AreaVersion, CreateAreaRequest, UpdateAreaRequest, BoundingBox } from '@snapland/shared-types';

const areas: Area[] = [];
let nextId = 1;

export const mockAreaApi: IAreaApi = {
  getAreasInBounds: async (bounds, zoom) => ({ areas, truncated: false }),
  getAreaById: async (id) => areas.find(a => a.id === id) as Area,
  createArea: async (req) => {
    const area = {
      id: String(nextId++), name: req.name, coordinates: req.coordinates, areaKm2: 1,
      version: 1, createdBy: '1', lastEditedBy: '1', createdAt: new Date().toISOString(), updatedAt: new Date().toISOString()
    };
    areas.push(area);
    return area;
  },
  updateArea: async (id, req) => {
    const idx = areas.findIndex(a => a.id === id);
    if (idx >= 0) {
      if (areas[idx].version !== req.version) {
        throw { name: 'ConflictError', currentArea: areas[idx] };
      }
      areas[idx] = { ...areas[idx], ...req, version: areas[idx].version + 1, updatedAt: new Date().toISOString() };
      return areas[idx];
    }
    throw new Error('Not found');
  },
  deleteArea: async (id) => {
    const idx = areas.findIndex(a => a.id === id);
    if (idx >= 0) areas.splice(idx, 1);
  },
  getAreaHistory: async (id) => []
};
""",
    "frontend/src/api/mock/mockWebSocketService.ts": """
import { IWebSocketService, ConnectionState, MessageHandler } from '../interfaces/IWebSocketService';
import type { WsMessage, ClientMessageType, ServerMessageType } from '@snapland/shared-types';

export const mockWebSocketService: IWebSocketService = {
  connect: async (provider) => { await provider(); },
  disconnect: () => {},
  send: (msg) => {},
  on: (type, handler) => () => {},
  onStateChange: (handler) => () => {},
  get connectionState() { return 'connected'; },
  get lastEventId() { return null; }
};
""",
    "frontend/src/providers/ApiProvider.tsx": """
import React, { createContext, useContext } from 'react';
import { IAreaApi } from '../api/interfaces/IAreaApi';
import { IWebSocketService } from '../api/interfaces/IWebSocketService';
import { mockAreaApi } from '../api/mock/mockAreaApi';
import { mockWebSocketService } from '../api/mock/mockWebSocketService';

interface ApiContextType {
  areaApi: IAreaApi;
  wsService: IWebSocketService;
}

const ApiContext = createContext<ApiContextType | null>(null);

export const ApiProvider: React.FC<{children: React.ReactNode}> = ({ children }) => {
  return (
    <ApiContext.Provider value={{ areaApi: mockAreaApi, wsService: mockWebSocketService }}>
      {children}
    </ApiContext.Provider>
  );
};

export const useApi = () => {
  const ctx = useContext(ApiContext);
  if (!ctx) throw new Error('useApi outside ApiProvider');
  return ctx;
};
""",
    "frontend/src/utils/geoUtils.ts": """
import { Coordinate } from '@snapland/shared-types';
export const flipCoordinates = (coords: Coordinate[]) => coords; // placeholder
""",
    "frontend/src/utils/areaCalculation.ts": """
import area from '@turf/area';
import kinks from '@turf/kinks';
import { Coordinate } from '@snapland/shared-types';

export const calculateArea = (coords: Coordinate[]): number => 0;
export const hasSelfIntersections = (coords: Coordinate[]): boolean => false;
""",
    "frontend/src/hooks/useAreas.ts": """
export const useAreas = () => { return {}; };
""",
    "frontend/src/hooks/useDrawing.ts": """
export const useDrawing = () => { return { isDrawing: false, startDrawing: () => {} }; };
""",
    "frontend/src/hooks/useMapBounds.ts": """
export const useMapBounds = () => { return {}; };
""",
    "frontend/src/hooks/useWebSocket.ts": """
export const useWebSocket = () => { return {}; };
""",
    "frontend/src/hooks/useAuth.ts": """
export const useAuth = () => { return { isAuthenticated: true, user: null }; };
""",
    "frontend/src/store/areasStore.ts": """
import { create } from 'zustand';
export const useAreasStore = create(() => ({}));
""",
    "frontend/src/store/collaborationStore.ts": """
import { create } from 'zustand';
export const useCollaborationStore = create(() => ({}));
""",
    "frontend/src/store/authStore.ts": """
import { create } from 'zustand';
export const useAuthStore = create(() => ({}));
""",
    "frontend/src/services/map/LayerManager.ts": """
export class LayerManager {}
""",
    "frontend/src/services/map/ProjectionUtils.ts": """
export class ProjectionUtils {}
""",
    "frontend/src/pages/MapPage.tsx": """
import React from 'react';
export const MapPage = () => <div>Map Page</div>;
""",
    "frontend/src/pages/LoginPage.tsx": """
import React from 'react';
export const LoginPage = () => <div>Login Page</div>;
""",
    "frontend/src/App.tsx": """
import React from 'react';
import { ApiProvider } from './providers/ApiProvider';
import { MapPage } from './pages/MapPage';

function App() {
  return (
    <ApiProvider>
      <MapPage />
    </ApiProvider>
  );
}

export default App;
""",
    "frontend/src/main.tsx": """
import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
"""
}

for filepath, content in files.items():
    full_path = os.path.join(r"D:\AICode\snapland", filepath)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content.strip() + "\\n")
print("Files generated.")
