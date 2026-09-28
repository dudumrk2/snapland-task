import os

files = {
    "frontend/src/pages/MapPage.tsx": """
import React from 'react';
import { MapView } from '../components/map/MapView';
export const MapPage = () => (
  <div style={{ height: '100vh', width: '100vw' }}>
    <MapView />
  </div>
);
""",
    "frontend/src/components/map/MapView.tsx": """
import React, { useEffect, useRef } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

export const MapView = () => {
  const mapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!mapRef.current) return;
    const map = L.map(mapRef.current).setView([31.5, 34.8], 8); // Centered on Israel
    
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; OpenStreetMap contributors'
    }).addTo(map);

    return () => {
      map.remove();
    };
  }, []);

  return <div ref={mapRef} style={{ height: '100%', width: '100%' }} />;
};
"""
}

for filepath, content in files.items():
    full_path = os.path.join(r"D:\AICode\snapland", filepath)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content.strip() + "\\n")
print("Map components updated.")
