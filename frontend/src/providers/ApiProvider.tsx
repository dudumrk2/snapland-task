import React, { createContext, useContext, ReactNode } from 'react';
import type { IAreaApi } from '../api/interfaces/IAreaApi';
import type { IAuthApi } from '../api/interfaces/IAuthApi';
import type { IWebSocketService } from '../api/interfaces/IWebSocketService';
import { mockAreaApi } from '../api/mock/mockAreaApi';
import { mockAuthApi } from '../api/mock/mockAuthApi';
import { mockWebSocketService } from '../api/mock/mockWebSocketService';

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
  areaApi = mockAreaApi,
  authApi = mockAuthApi,
  wsService = mockWebSocketService,
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
