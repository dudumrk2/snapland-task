import React from 'react';
import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { ApiProvider, useApi } from '../../../src/providers/ApiProvider';
import { MockAreaApi } from '../../../src/api/mock/mockAreaApi';
import { AreaApi } from '../../../src/api/http/areaApi';
import { AuthApi } from '../../../src/api/http/authApi';
import { WebSocketService } from '../../../src/services/websocket/WebSocketService';

const ConsumerComponent: React.FC<{ onServices: (services: any) => void }> = ({ onServices }) => {
  const services = useApi();
  onServices(services);
  return <div>Api Consumer</div>;
};

describe('ApiProvider', () => {
  it('injects real services by default in production/real mode', () => {
    let captured: any;
    render(
      <ApiProvider>
        <ConsumerComponent onServices={(s) => (captured = s)} />
      </ApiProvider>
    );

    expect(captured).toBeDefined();
    expect(captured.areaApi).toBeInstanceOf(AreaApi);
    expect(captured.authApi).toBeInstanceOf(AuthApi);
    expect(captured.wsService).toBeInstanceOf(WebSocketService);
  });

  it('allows overriding services via props for testing or isolation', () => {
    let captured: any;
    const customMockAreaApi = new MockAreaApi();

    render(
      <ApiProvider areaApi={customMockAreaApi}>
        <ConsumerComponent onServices={(s) => (captured = s)} />
      </ApiProvider>
    );

    expect(captured.areaApi).toBe(customMockAreaApi);
  });

  it('injects mock services when VITE_USE_MOCK_API is true', () => {
    const origEnv = import.meta.env.VITE_USE_MOCK_API;
    import.meta.env.VITE_USE_MOCK_API = 'true';

    try {
      let captured: any;
      render(
        <ApiProvider>
          <ConsumerComponent onServices={(s) => (captured = s)} />
        </ApiProvider>
      );

      expect(captured.areaApi).toBeInstanceOf(MockAreaApi);
    } finally {
      import.meta.env.VITE_USE_MOCK_API = origEnv;
    }
  });
});
