import React, { useState, useEffect, ReactNode } from 'react';
import { LoginPage } from '../pages/LoginPage';
import { MapPage } from '../pages/MapPage';
import { useAuthStore } from '../store/authStore';

const ROUTES = {
  LOGIN: '/login',
  MAP: '/',
} as const;

export interface RouterProps {
  children?: ReactNode;
}

/**
 * Minimal client-side Router.
 * Listens to popstate and maps pathname → page component.
 * Redirects unauthenticated users to /login and authenticated users away from /login using replaceState to avoid history traps.
 */
export const Router: React.FC = () => {
  const [pathname, setPathname] = useState(
    typeof window !== 'undefined' ? window.location.pathname : ROUTES.MAP
  );

  const { isAuthenticated, isBootstrapping } = useAuthStore();

  // Sync pathname with history events
  useEffect(() => {
    const handlePopState = () => setPathname(window.location.pathname);
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  // Redirect logic — runs after initial session bootstrap is settled
  useEffect(() => {
    if (isBootstrapping) return;

    if (isAuthenticated && pathname === ROUTES.LOGIN) {
      window.history.replaceState({}, '', ROUTES.MAP);
      setPathname(ROUTES.MAP);
    } else if (!isAuthenticated && pathname !== ROUTES.LOGIN) {
      window.history.replaceState({}, '', ROUTES.LOGIN);
      setPathname(ROUTES.LOGIN);
    }
  }, [isAuthenticated, isBootstrapping, pathname]);

  // Show nothing while initial bootstrap is in progress
  if (isBootstrapping) {
    return (
      <div
        style={{
          width: '100vw',
          height: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          backgroundColor: '#f9fafb',
          fontSize: '14px',
          color: '#6b7280',
        }}
      >
        Loading…
      </div>
    );
  }

  if (!isAuthenticated) {
    return <LoginPage />;
  }

  return <MapPage />;
};
