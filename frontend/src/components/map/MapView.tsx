import React, { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { LayerManager } from '../../services/map/LayerManager';
import { BaseLayerControl } from './BaseLayerControl';
import { AreaOverlay } from './AreaOverlay';
import { DrawingLayer } from './DrawingLayer';
import { VertexEditor } from './VertexEditor';
import { CollaborationLayer } from './CollaborationLayer';
import { useDrawing } from '../../hooks/useDrawing';
import { useMapBounds } from '../../hooks/useMapBounds';
import { useAreas } from '../../hooks/useAreas';
import { useWebSocket } from '../../hooks/useWebSocket';

export interface MapViewProps {
  drawingController: ReturnType<typeof useDrawing>;
  onToast?: (message: string) => void;
}

export const MapView: React.FC<MapViewProps> = ({
  drawingController,
  onToast,
}) => {
  const mapContainerRef = useRef<HTMLDivElement | null>(null);
  const [mapInstance, setMapInstance] = useState<L.Map | null>(null);
  const [layerManager, setLayerManager] = useState<LayerManager | null>(null);

  const onToastRef = useRef(onToast);
  onToastRef.current = onToast;

  const { fetchAreasInBounds } = useAreas();
  const { sendCursorMove } = useWebSocket();

  // Initialize Map
  useEffect(() => {
    if (!mapContainerRef.current || mapInstance) return;

    // Default center: Tel Aviv, Israel
    const map = L.map(mapContainerRef.current, {
      center: [32.0853, 34.7818],
      zoom: 13,
      zoomControl: false,
    });

    // Add zoom control at bottom right
    L.control.zoom({ position: 'bottomright' }).addTo(map);

    // Initialize LayerManager with fallback notification
    const lm = new LayerManager({
      onFallback: (reason) => {
        onToastRef.current?.(reason);
      },
    });
    lm.initialize(map, 'osm');

    setMapInstance(map);
    setLayerManager(lm);

    return () => {
      lm.destroy();
      map.remove();
    };
  }, []);

  // Track map bounds and refetch areas
  useMapBounds(mapInstance, {
    onBoundsChange: (bounds, zoom) => {
      fetchAreasInBounds(bounds, zoom);
    },
    debounceMs: 250,
  });

  // Track cursor movement for collaborative presence
  useEffect(() => {
    if (!mapInstance) return;

    const handleMouseMove = (e: L.LeafletMouseEvent) => {
      sendCursorMove({ lat: e.latlng.lat, lng: e.latlng.lng });
    };

    mapInstance.on('mousemove', handleMouseMove);
    return () => {
      mapInstance.off('mousemove', handleMouseMove);
    };
  }, [mapInstance, sendCursorMove]);

  return (
    <div
      style={{
        position: 'relative',
        width: '100%',
        height: '100%',
        overflow: 'hidden',
      }}
    >
      <div
        ref={mapContainerRef}
        className="leaflet-container"
        style={{ width: '100%', height: '100%' }}
      />

      {mapInstance && (
        <>
          <BaseLayerControl layerManager={layerManager} onToast={onToast} />
          <AreaOverlay map={mapInstance} />
          <DrawingLayer map={mapInstance} drawingController={drawingController} />
          <VertexEditor map={mapInstance} />
          <CollaborationLayer map={mapInstance} />
        </>
      )}
    </div>
  );
};
