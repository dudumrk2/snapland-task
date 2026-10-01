import { useCallback, useEffect, useRef } from 'react';
import type {
  ClientMessageType,
  Coordinate,
  WsMessage,
} from '@snapland/shared-types';
import { useCollaborationStore } from '../store/collaborationStore';
import { useWebSocketContext } from '../providers/WebSocketProvider';
import { useApi } from '../providers/ApiProvider';

import { setupWebSocketSubscriptions } from '../services/realtime/wsSubscriptions';

export function useWebSocket(autoConnect = true) {
  const { wsService, authApi } = useApi();
  const wsContext = useWebSocketContext();
  const lastCursorSentRef = useRef<number>(0);

  const connectionState = useCollaborationStore((s) => s.connectionState);
  const presenceUsers = useCollaborationStore((s) => s.presenceUsers);
  const remoteCursors = useCollaborationStore((s) => s.remoteCursors);
  const remoteShapes = useCollaborationStore((s) => s.remoteShapes);

  // Fallback lifecycle when outside WebSocketProvider
  useEffect(() => {
    if (wsContext) return;

    const cleanupSubscriptions = setupWebSocketSubscriptions(wsService, {
      enableProactiveConflict: true,
    });

    if (autoConnect) {
      wsService.connect(async () => {
        return authApi.getWsTicket();
      });
    }

    return () => {
      cleanupSubscriptions();
      if (autoConnect) {
        wsService.disconnect();
      }
    };
  }, [wsContext, wsService, authApi, autoConnect]);

  const sendCursorMove = useCallback(
    (coord: Coordinate) => {
      if (wsContext) {
        wsContext.sendCursorMove(coord);
      } else {
        const now = Date.now();
        // Throttle cursor moves to max 10 Hz (every 100ms) as per HLD §9.1
        if (now - lastCursorSentRef.current >= 100) {
          lastCursorSentRef.current = now;
          wsService.send({
            type: 'CURSOR_MOVE',
            payload: { lat: coord.lat, lng: coord.lng },
          });
        }
      }
    },
    [wsContext, wsService]
  );

  const sendMessage = useCallback(
    <T extends ClientMessageType>(msg: WsMessage<T>) => {
      if (wsContext) {
        wsContext.sendMessage(msg);
      } else {
        wsService.send(msg);
      }
    },
    [wsContext, wsService]
  );

  const connect = useCallback(() => {
    if (wsContext) {
      wsContext.connect();
    } else {
      wsService.connect(() => authApi.getWsTicket());
    }
  }, [wsContext, wsService, authApi]);

  const disconnect = useCallback(() => {
    if (wsContext) {
      wsContext.disconnect();
    } else {
      wsService.disconnect();
    }
  }, [wsContext, wsService]);

  return {
    connectionState,
    presenceUsers,
    remoteCursors,
    remoteShapes,
    sendCursorMove,
    sendMessage,
    connect,
    disconnect,
  };
}
