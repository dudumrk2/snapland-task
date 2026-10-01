import React, { useState } from 'react';
import { MapView } from '../components/map/MapView';
import { AreaPanel } from '../components/ui/AreaPanel';
import { UserPresenceBar } from '../components/ui/UserPresenceBar';
import { ConflictDialog } from '../components/ui/ConflictDialog';
import { Toast } from '../components/ui/Toast';
import { useDrawing } from '../hooks/useDrawing';
import { WebSocketProvider } from '../providers/WebSocketProvider';

export const MapPage: React.FC = () => {
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const drawingController = useDrawing();

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
