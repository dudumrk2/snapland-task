import React from 'react';
import { useAuth } from '../../hooks/useAuth';
import { useWebSocket } from '../../hooks/useWebSocket';

export const UserPresenceBar: React.FC = () => {
  const { user, logout } = useAuth();
  const { connectionState, presenceUsers } = useWebSocket();

  const getStatusColor = () => {
    switch (connectionState) {
      case 'connected':
        return '#10b981';
      case 'connecting':
      case 'reconnecting':
        return '#f59e0b';
      case 'polling':
        return '#6366f1';
      case 'disconnected':
      default:
        return '#ef4444';
    }
  };

  return (
    <div
      style={{
        position: 'absolute',
        top: 16,
        left: 16,
        zIndex: 1000,
        backgroundColor: '#ffffff',
        borderRadius: 8,
        boxShadow: '0 2px 8px rgba(0,0,0,0.12)',
        padding: '6px 14px',
        display: 'flex',
        alignItems: 'center',
        gap: 16,
        fontSize: '13px',
      }}
    >
      {/* Brand & Connection State */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <strong style={{ color: '#1e3a8a', fontSize: '15px' }}>Snapland</strong>
        <div
          title={`Connection: ${connectionState}`}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 4,
            fontSize: '11px',
            backgroundColor: '#f3f4f6',
            padding: '2px 6px',
            borderRadius: 10,
          }}
        >
          <span
            style={{
              width: 8,
              height: 8,
              borderRadius: '50%',
              backgroundColor: getStatusColor(),
            }}
          />
          <span style={{ textTransform: 'capitalize', color: '#4b5563' }}>
            {connectionState}
          </span>
        </div>
      </div>

      {/* Online Collaborators */}
      {presenceUsers.length > 0 && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ color: '#6b7280', fontSize: '12px' }}>Online:</span>
          <div style={{ display: 'flex', gap: 4 }}>
            {presenceUsers.map((u) => (
              <span
                key={u.userId}
                style={{
                  backgroundColor: '#e0e7ff',
                  color: '#3730a3',
                  padding: '1px 6px',
                  borderRadius: 4,
                  fontSize: '11px',
                  fontWeight: 500,
                }}
              >
                {u.displayName}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* User Info & Logout Button */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          marginLeft: 'auto',
          borderLeft: '1px solid #e5e7eb',
          paddingLeft: 12,
        }}
      >
        <span style={{ color: '#374151', fontWeight: 500 }}>
          {user?.displayName || user?.email || 'User'}
        </span>
        <button
          type="button"
          onClick={logout}
          style={{
            padding: '4px 10px',
            backgroundColor: '#f3f4f6',
            color: '#374151',
            border: '1px solid #d1d5db',
            borderRadius: 6,
            fontSize: '12px',
            fontWeight: 500,
            cursor: 'pointer',
          }}
        >
          Logout
        </button>
      </div>
    </div>
  );
};
