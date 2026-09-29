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
 * Redirects unauthenticated users to /login and authenticated users away from /login.
 */
export const Router: React.FC = () => {
  const [pathname, setPathname] = useState(
    typeof window !== 'undefined' ? window.location.pathname : ROUTES.MAP
  );

  const { isAuthenticated, isLoading } = useAuthStore();

  // Sync pathname with history events
  useEffect(() => {
    const handlePopState = () => setPathname(window.location.pathname);
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  // Redirect logic — runs after auth state is settled
  useEffect(() => {
    if (isLoading) return;

    if (isAuthenticated && pathname === ROUTES.LOGIN) {
      window.history.pushState({}, '', ROUTES.MAP);
      setPathname(ROUTES.MAP);
    } else if (!isAuthenticated && pathname !== ROUTES.LOGIN) {
      window.history.pushState({}, '', ROUTES.LOGIN);
      setPathname(ROUTES.LOGIN);
    }
  }, [isAuthenticated, isLoading, pathname]);

  // Show nothing while auth is initialising to avoid flash
  if (isLoading) {
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
