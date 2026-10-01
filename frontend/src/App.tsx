import React from 'react';
import { ApiProvider } from './providers/ApiProvider';
import { AuthProvider } from './providers/AuthProvider';
import { Router } from './providers/Router';

/**
 * App follows HLD §11.1 component tree:
 *   App → ApiProvider → AuthProvider → Router → [LoginPage | MapPage]
 *
 * - ApiProvider: injects IAreaApi, IAuthApi, IWebSocketService (mock in Phase 1)
 * - AuthProvider: bootstraps session via authApi.refresh() on mount
 * - Router: maps pathname to page; redirects based on auth state (no mock leakage)
 */
const App: React.FC = () => {
  return (
    <ApiProvider>
      <AuthProvider>
        <Router />
      </AuthProvider>
    </ApiProvider>
  );
};

export default App;
