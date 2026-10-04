import React, { useState, useEffect } from 'react';
import { LayerManager, BaseLayerType } from '../../services/map/LayerManager';

export interface BaseLayerControlProps {
  layerManager: LayerManager | null;
  onToast?: (message: string) => void;
}

export const BaseLayerControl: React.FC<BaseLayerControlProps> = ({
  layerManager,
  onToast,
}) => {
  const [activeLayer, setActiveLayer] = useState<BaseLayerType>('osm');
  const [isSwitching, setIsSwitching] = useState(false);

  useEffect(() => {
    if (layerManager) {
      setActiveLayer(layerManager.getCurrentLayerType());
    }
  }, [layerManager]);

  const handleSwitch = async (type: BaseLayerType) => {
    if (!layerManager || activeLayer === type || isSwitching) return;

    setIsSwitching(true);
    try {
      await layerManager.switchLayer(type);
      setActiveLayer(type);
      if (layerManager.isFallbackActive() && onToast) {
        onToast('Satellite imagery unavailable, switched to Fallback (GovMap)');
      }
    } catch (err: any) {
      if (onToast) {
        onToast(`Layer switch error: ${err.message}`);
      }
    } finally {
      setIsSwitching(false);
    }
  };

  return (
    <div
      style={{
        position: 'absolute',
        top: 16,
        right: 16,
        zIndex: 1000,
        backgroundColor: '#ffffff',
        borderRadius: 8,
        boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
        padding: '6px',
        display: 'flex',
        gap: '6px',
      }}
      className="base-layer-control"
    >
      <button
        type="button"
        onClick={() => handleSwitch('osm')}
        disabled={isSwitching}
        style={{
          padding: '6px 12px',
          border: 'none',
          borderRadius: 6,
          backgroundColor: activeLayer === 'osm' ? '#2563eb' : '#f3f4f6',
          color: activeLayer === 'osm' ? '#ffffff' : '#374151',
          cursor: isSwitching ? 'not-allowed' : 'pointer',
          fontWeight: 600,
          fontSize: '13px',
          transition: 'all 0.2s ease',
        }}
      >
        OSM
      </button>

      <button
        type="button"
        onClick={() => handleSwitch('satellite')}
        disabled={isSwitching}
        style={{
          padding: '6px 12px',
          border: 'none',
          borderRadius: 6,
          backgroundColor: activeLayer === 'satellite' ? '#2563eb' : '#f3f4f6',
          color: activeLayer === 'satellite' ? '#ffffff' : '#374151',
          cursor: isSwitching ? 'not-allowed' : 'pointer',
          fontWeight: 600,
          fontSize: '13px',
          transition: 'all 0.2s ease',
        }}
      >
        Satellite
      </button>
    </div>
  );
};
