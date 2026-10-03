import React, { useState, useEffect } from 'react';
import { MapView } from '../components/map/MapView';
import { AreaPanel } from '../components/ui/AreaPanel';
import { UserPresenceBar } from '../components/ui/UserPresenceBar';
import { ConflictDialog } from '../components/ui/ConflictDialog';
import { Toast } from '../components/ui/Toast';
import { useDrawing } from '../hooks/useDrawing';
import { WebSocketProvider } from '../providers/WebSocketProvider';
import { useCollaborationStore } from '../store/collaborationStore';
import { subscribeToast } from '../utils/toastService';

export const MapPage: React.FC = () => {
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const drawingController = useDrawing();
  const connectionState = useCollaborationStore((s) => s.connectionState);

  useEffect(() => {
    return subscribeToast((msg) => {
      setToastMessage(msg);
    });
  }, []);

  return (
    <WebSocketProvider>
      <div
        style={{
          position: 'relative',
          width: '100vw',
          height: '100vh',
          overflow: 'hidden',
        }}
      >
        <UserPresenceBar />

        {/* Degraded Mode Banner (Task 8 / HLD §9.7) */}
        {connectionState === 'polling' && (
          <div
            role="status"
            className="degraded-mode-banner"
            style={{
              position: 'absolute',
              top: 16,
              left: '50%',
              transform: 'translateX(-50%)',
              zIndex: 1500,
              backgroundColor: '#fef3c7',
              color: '#92400e',
              border: '1px solid #fcd34d',
              padding: '6px 16px',
              borderRadius: '8px',
              fontSize: '13px',
              fontWeight: 600,
              boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
              display: 'flex',
              alignItems: 'center',
              gap: 6,
            }}
          >
            <span>⚠️ Live updates unavailable</span>
          </div>
        )}

        <MapView
          drawingController={drawingController}
          onToast={(msg) => setToastMessage(msg)}
        />

        <AreaPanel
          isDrawing={drawingController.isDrawing}
          onStartDrawing={drawingController.startDrawing}
          onCancelDrawing={drawingController.cancelDrawing}
        />

        <ConflictDialog />

        <Toast
          message={toastMessage}
          onClose={() => setToastMessage(null)}
        />
      </div>
    </WebSocketProvider>
  );
};
