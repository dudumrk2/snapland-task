import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import { ApiProvider } from './providers/ApiProvider';
import 'leaflet/dist/leaflet.css';

const style = document.createElement('style');
style.innerHTML = `
  * {
    box-sizing: border-box;
  }
  html, body, #root {
    width: 100%;
    height: 100%;
    margin: 0;
    padding: 0;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
  }
  .leaflet-container {
    width: 100%;
    height: 100%;
    outline: none;
  }
  .live-area-tooltip {
    background-color: rgba(17, 24, 39, 0.9) !important;
    color: #ffffff !important;
    border: none !important;
    border-radius: 4px !important;
    font-size: 12px !important;
    font-weight: 600 !important;
    padding: 4px 8px !important;
    box-shadow: 0 2px 6px rgba(0,0,0,0.2) !important;
  }
  .snapland-polygon-tooltip {
    background-color: rgba(255, 255, 255, 0.95) !important;
    color: #1f2937 !important;
    border: 1px solid #e5e7eb !important;
    border-radius: 6px !important;
    font-size: 12px !important;
    padding: 4px 8px !important;
    box-shadow: 0 2px 8px rgba(0,0,0,0.1) !important;
  }
`;
document.head.appendChild(style);

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ApiProvider>
      <App />
    </ApiProvider>
  </React.StrictMode>
);
