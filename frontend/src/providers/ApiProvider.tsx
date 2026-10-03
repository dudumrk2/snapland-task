import React, { createContext, useContext, ReactNode, useMemo } from 'react';
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

export const ApiProvider: React.FC<ApiProviderProps> = ({
  children,
  areaApi,
  authApi,
  wsService,
}) => {
  const isMock = import.meta.env.VITE_USE_MOCK_API === 'true';

  const value: ApiContextValue = useMemo(
    () => ({
      areaApi: areaApi ?? (isMock ? mockAreaApi : realAreaApi),
      authApi: authApi ?? (isMock ? mockAuthApi : realAuthApi),
      wsService: wsService ?? (isMock ? mockWebSocketService : realWebSocketService),
    }),
    [areaApi, authApi, wsService, isMock]
  );

  return <ApiContext.Provider value={value}>{children}</ApiContext.Provider>;
};

export const useApi = (): ApiContextValue => {
  const context = useContext(ApiContext);
  if (!context) {
    throw new Error('useApi must be used within an ApiProvider');
  }
  return context;
};
