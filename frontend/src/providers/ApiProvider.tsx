import React, { createContext, useContext, ReactNode } from 'react';
import type { IAreaApi } from '../api/interfaces/IAreaApi';
import type { IAuthApi } from '../api/interfaces/IAuthApi';
import type { IWebSocketService } from '../api/interfaces/IWebSocketService';
import { mockAreaApi } from '../api/mock/mockAreaApi';
import { mockAuthApi } from '../api/mock/mockAuthApi';
import { mockWebSocketService } from '../api/mock/mockWebSocketService';
import { realAreaApi } from '../api/http/areaApi';
import { realAuthApi } from '../api/http/authApi';
import { realWebSocketService } from '../services/websocket/WebSocketService';

export interface ApiContextValue {
  areaApi: IAreaApi;
  authApi: IAuthApi;
  wsService: IWebSocketService;
}

const ApiContext = createContext<ApiContextValue | null>(null);

export interface ApiProviderProps {
  children: ReactNode;
  areaApi?: IAreaApi;
  authApi?: IAuthApi;
  wsService?: IWebSocketService;
}

const isMock = import.meta.env.VITE_USE_MOCK_API === 'true';

const defaultAreaApi = isMock ? mockAreaApi : realAreaApi;
const defaultAuthApi = isMock ? mockAuthApi : realAuthApi;
const defaultWsService = isMock ? mockWebSocketService : realWebSocketService;

export const ApiProvider: React.FC<ApiProviderProps> = ({
  children,
  areaApi = defaultAreaApi,
  authApi = defaultAuthApi,
  wsService = defaultWsService,
}) => {
  const value: ApiContextValue = {
    areaApi,
    authApi,
    wsService,
  };

  return <ApiContext.Provider value={value}>{children}</ApiContext.Provider>;
};

export const useApi = (): ApiContextValue => {
  const context = useContext(ApiContext);
  if (!context) {
    throw new Error('useApi must be used within an ApiProvider');
  }
  return context;
};

export const useApiContext = useApi;
