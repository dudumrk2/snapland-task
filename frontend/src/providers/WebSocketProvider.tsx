import React, { createContext, useContext, useEffect, useRef, useCallback, ReactNode } from 'react';
import type { ClientMessageType, Coordinate, WsMessage } from '@snapland/shared-types';
import { useApi } from './ApiProvider';
import { setupWebSocketSubscriptions } from '../services/realtime/wsSubscriptions';

interface WebSocketContextValue {
  sendCursorMove: (coord: Coordinate) => void;
  sendMessage: <T extends ClientMessageType>(msg: WsMessage<T>) => void;
  connect: () => void;
  disconnect: () => void;
}

const WebSocketContext = createContext<WebSocketContextValue | null>(null);

export const WebSocketProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const { wsService, authApi } = useApi();
  const lastCursorSentRef = useRef<number>(0);

  useEffect(() => {
    const cleanupSubscriptions = setupWebSocketSubscriptions(wsService, {
      enableProactiveConflict: true,
    });

    // Auto-connect once on mount
    wsService.connect(async () => {
      return authApi.getWsTicket();
    });

    return () => {
      cleanupSubscriptions();
      wsService.disconnect();
    };
  }, [wsService, authApi]);

  const sendCursorMove = useCallback(
    (coord: Coordinate) => {
      const now = Date.now();
      // Throttle cursor moves to max 10 Hz (every 100ms) as per HLD §9.1
      if (now - lastCursorSentRef.current >= 100) {
        lastCursorSentRef.current = now;
        wsService.send({
          type: 'CURSOR_MOVE',
          payload: { lat: coord.lat, lng: coord.lng },
        });
      }
    },
    [wsService]
  );

  const sendMessage = useCallback(
    <T extends ClientMessageType>(msg: WsMessage<T>) => {
      wsService.send(msg);
    },
    [wsService]
  );

  const connect = useCallback(() => {
    wsService.connect(() => authApi.getWsTicket());
  }, [wsService, authApi]);

  const disconnect = useCallback(() => {
    wsService.disconnect();
  }, [wsService]);

  return (
    <WebSocketContext.Provider value={{ sendCursorMove, sendMessage, connect, disconnect }}>
      {children}
    </WebSocketContext.Provider>
  );
};

export const useWebSocketContext = () => {
  return useContext(WebSocketContext);
};
