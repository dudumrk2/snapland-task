import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import L from 'leaflet';
import { LayerManager } from '../../../src/services/map/LayerManager';

describe('LayerManager', () => {
  let container: HTMLDivElement;
  let map: L.Map;
  let layerManager: LayerManager;

  beforeEach(() => {
    container = document.createElement('div');
    container.style.width = '800px';
    container.style.height = '600px';
    document.body.appendChild(container);

    map = L.map(container, {
      center: [32.0853, 34.7818],
      zoom: 13,
    });
  });

  afterEach(() => {
    if (layerManager) layerManager.destroy();
    if (map) map.remove();
    if (container && container.parentNode) {
      container.parentNode.removeChild(container);
    }
    vi.restoreAllMocks();
  });

  it('creates dedicated panes (polygonsPane at zIndex 450)', () => {
    layerManager = new LayerManager();
    layerManager.initialize(map, 'osm');

    const polygonsPane = map.getPane('polygonsPane');
    expect(polygonsPane).toBeDefined();
    expect(polygonsPane?.style.zIndex).toBe('450');

    const drawingPane = map.getPane('drawingPane');
    expect(drawingPane).toBeDefined();
    expect(drawingPane?.style.zIndex).toBe('460');

    const collabPane = map.getPane('collaborationPane');
    expect(collabPane).toBeDefined();
    expect(collabPane?.style.zIndex).toBe('470');
  });

  it('initializes with OSM layer by default', () => {
    layerManager = new LayerManager();
    layerManager.initialize(map, 'osm');

    expect(layerManager.getCurrentLayerType()).toBe('osm');
    expect(layerManager.isFallbackActive()).toBe(false);
  });

  it('triggers fallback callback when satellite fails', async () => {
    const fallbackSpy = vi.fn();
    layerManager = new LayerManager({
      onFallback: fallbackSpy,
      crossFadeDurationMs: 10,
    });
    layerManager.initialize(map, 'osm');

    // Trigger satellite switch
    const switchPromise = layerManager.switchLayer('satellite');

    // Simulate tile errors on the pending layer
    const layers: any[] = [];
    map.eachLayer((l) => layers.push(l));
    const targetLayer = layers[layers.length - 1];
    if (targetLayer) {
      targetLayer.fire('tileerror');
      targetLayer.fire('tileerror');
      targetLayer.fire('tileerror');
    }

    await switchPromise;
    expect(layerManager.isFallbackActive()).toBe(true);
    expect(fallbackSpy).toHaveBeenCalled();
  });
});
