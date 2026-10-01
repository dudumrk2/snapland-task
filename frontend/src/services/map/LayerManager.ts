import L from 'leaflet';

export type BaseLayerType = 'osm' | 'satellite';

export interface LayerManagerOptions {
  onFallback?: (reason: string) => void;
  crossFadeDurationMs?: number;
}

export class LayerManager {
  private map: L.Map | null = null;
  private currentLayerType: BaseLayerType = 'osm';
  private currentTileLayer: L.TileLayer | null = null;
  private pendingTileLayer: L.TileLayer | null = null;
  private isTransitioning = false;
  private onFallbackCallback?: (reason: string) => void;
  private crossFadeDurationMs = 300;
  private isUsingFallback = false;
  private activeInterval: any = null;
  private fallbackTimer: any = null;

  // Clean OpenStreetMap tile URL (no deprecated {s} subdomain)
  private static readonly OSM_URL =
    'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
  private static readonly GOVMAP_URL =
    (typeof import.meta !== 'undefined' &&
      import.meta.env &&
      import.meta.env.VITE_SATELLITE_TILE_URL) ||
    'https://cdnil.govmap.gov.il/xyz/heb/{z}/{x}/{y}.png';
  private static readonly ESRI_URL =
    'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';

  constructor(options?: LayerManagerOptions) {
    this.onFallbackCallback = options?.onFallback;
    if (options?.crossFadeDurationMs !== undefined) {
      this.crossFadeDurationMs = options.crossFadeDurationMs;
    }
  }

  /**
   * Initializes LayerManager with the Leaflet map and configures custom panes.
   */
  initialize(map: L.Map, initialLayer: BaseLayerType = 'osm'): void {
    this.map = map;
    this.ensureCustomPanes(map);

    this.currentLayerType = initialLayer;
    const layer = this.createTileLayer(initialLayer);
    layer.setOpacity(1);
    layer.addTo(map);
    this.currentTileLayer = layer;
  }

  /**
   * Creates dedicated panes above tilePane (tilePane is z-index 200).
   * Polygons pane at z-index 450 ensures vector layers never flicker or move.
   */
  private ensureCustomPanes(map: L.Map): void {
    if (!map.getPane('polygonsPane')) {
      const pane = map.createPane('polygonsPane');
      pane.style.zIndex = '450';
      pane.style.pointerEvents = 'auto';
    }

    if (!map.getPane('drawingPane')) {
      const pane = map.createPane('drawingPane');
      pane.style.zIndex = '460';
      pane.style.pointerEvents = 'auto';
    }

    if (!map.getPane('collaborationPane')) {
      const pane = map.createPane('collaborationPane');
      pane.style.zIndex = '470';
      pane.style.pointerEvents = 'none';
    }
  }

  getCurrentLayerType(): BaseLayerType {
    return this.currentLayerType;
  }

  getCurrentTileLayer(): L.TileLayer | null {
    return this.currentTileLayer;
  }

  isFallbackActive(): boolean {
    return this.isUsingFallback;
  }

  /**
   * Switches base layer with smooth cross-fade transition.
   */
  async switchLayer(targetType: BaseLayerType): Promise<void> {
    if (!this.map || this.currentLayerType === targetType || this.isTransitioning) {
      return;
    }

    this.isTransitioning = true;
    const oldLayer = this.currentTileLayer;
    const initialTargetLayer = this.createTileLayer(targetType);

    try {
      // Step 1: Add initial target layer at opacity 0 to tilePane
      initialTargetLayer.setOpacity(0);
      initialTargetLayer.addTo(this.map);
      this.pendingTileLayer = initialTargetLayer;

      // Step 2: Await load or fallback (which might replace this.pendingTileLayer)
      await this.prepareLayerReady(initialTargetLayer, targetType);

      // Verify map wasn't destroyed while waiting
      if (!this.map) return;

      // Always cross-fade into the ACTUAL active target layer (initial or fallback)
      const layerToFadeIn = this.pendingTileLayer || initialTargetLayer;
      await this.crossFade(oldLayer, layerToFadeIn);

      if (!this.map) return;

      // Step 4: Clean up old layer
      if (oldLayer && this.map.hasLayer(oldLayer)) {
        this.map.removeLayer(oldLayer);
      }

      this.currentTileLayer = layerToFadeIn;
      this.pendingTileLayer = null;
      this.currentLayerType = targetType;
    } finally {
      this.isTransitioning = false;
    }
  }

  private createTileLayer(type: BaseLayerType, forceFallback = false): L.TileLayer {
    if (type === 'osm') {
      this.isUsingFallback = false;
      return L.tileLayer(LayerManager.OSM_URL, {
        maxZoom: 19,
        attribution: '© OpenStreetMap contributors',
      });
    }

    // Satellite
    if (forceFallback || this.isUsingFallback) {
      this.isUsingFallback = true;
      return L.tileLayer(LayerManager.ESRI_URL, {
        maxZoom: 19,
        attribution: '© Esri, Maxar, Earthstar Geographics',
      });
    }

    return L.tileLayer(LayerManager.GOVMAP_URL, {
      maxZoom: 19,
      maxNativeZoom: 19,
      attribution: '© Survey of Israel — GovMap',
    });
  }

  private prepareLayerReady(layer: L.TileLayer, targetType: BaseLayerType): Promise<void> {
    return new Promise<void>((resolve) => {
      let resolved = false;
      let errorCount = 0;
      const MAX_TILE_ERRORS = 3;

      const finish = () => {
        if (!resolved) {
          resolved = true;
          if (this.fallbackTimer) {
            clearTimeout(this.fallbackTimer);
            this.fallbackTimer = null;
          }
          layer.off('load', onLoad);
          layer.off('tileerror', onError);
          resolve();
        }
      };

      const onLoad = () => {
        finish();
      };

      const onError = () => {
        errorCount++;
        if (targetType === 'satellite' && !this.isUsingFallback && errorCount >= MAX_TILE_ERRORS) {
          this.triggerFallback(layer).then(finish);
        }
      };

      layer.once('load', onLoad);
      layer.on('tileerror', onError);

      // 5 second fallback timeout for satellite
      this.fallbackTimer = setTimeout(() => {
        if (!resolved && targetType === 'satellite' && !this.isUsingFallback) {
          this.triggerFallback(layer).then(finish);
        } else {
          finish();
        }
      }, 5000);
    });
  }

  private async triggerFallback(failedLayer: L.TileLayer): Promise<void> {
    if (!this.map || this.isUsingFallback) return;
    this.isUsingFallback = true;

    if (this.map.hasLayer(failedLayer)) {
      this.map.removeLayer(failedLayer);
    }

    const fallbackLayer = this.createTileLayer('satellite', true);
    fallbackLayer.setOpacity(0);
    fallbackLayer.addTo(this.map);
    this.pendingTileLayer = fallbackLayer;

    if (this.onFallbackCallback) {
      this.onFallbackCallback('GovMap satellite unavailable, switched to Fallback (Esri World Imagery)');
    }
  }

  private crossFade(oldLayer: L.TileLayer | null, newLayer: L.TileLayer): Promise<void> {
    return new Promise((resolve) => {
      const steps = 10;
      const stepDuration = this.crossFadeDurationMs / steps;
      let step = 0;

      if (this.activeInterval) {
        clearInterval(this.activeInterval);
        this.activeInterval = null;
      }

      this.activeInterval = setInterval(() => {
        step++;
        const progress = step / steps;

        if (this.map && this.map.hasLayer(newLayer)) {
          newLayer.setOpacity(progress);
        }
        if (oldLayer && this.map && this.map.hasLayer(oldLayer)) {
          oldLayer.setOpacity(1 - progress);
        }

        if (step >= steps) {
          clearInterval(this.activeInterval);
          this.activeInterval = null;
          if (this.map && this.map.hasLayer(newLayer)) {
            newLayer.setOpacity(1);
          }
          if (oldLayer && this.map && this.map.hasLayer(oldLayer)) {
            oldLayer.setOpacity(0);
          }
          resolve();
        }
      }, stepDuration);
    });
  }

  destroy(): void {
    if (this.activeInterval) {
      clearInterval(this.activeInterval);
      this.activeInterval = null;
    }
    if (this.fallbackTimer) {
      clearTimeout(this.fallbackTimer);
      this.fallbackTimer = null;
    }
    if (this.map) {
      if (this.currentTileLayer && this.map.hasLayer(this.currentTileLayer)) {
        this.map.removeLayer(this.currentTileLayer);
      }
      if (this.pendingTileLayer && this.map.hasLayer(this.pendingTileLayer)) {
        this.map.removeLayer(this.pendingTileLayer);
      }
      this.map = null;
    }
  }
}
