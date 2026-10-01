import React from 'react';

export interface ToastProps {
  message: string | null;
  onClose?: () => void;
}

export const Toast: React.FC<ToastProps> = ({ message, onClose }) => {
  if (!message) return null;

  return (
    <div
      className="toast"
      style={{
        position: 'fixed',
        bottom: 24,
        right: 24,
        zIndex: 3000,
        backgroundColor: '#1f2937',
        color: '#ffffff',
        padding: '12px 20px',
        borderRadius: 8,
        boxShadow: '0 10px 15px -3px rgba(0,0,0,0.1), 0 4px 6px -2px rgba(0,0,0,0.05)',
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        fontSize: '14px',
        animation: 'fadeIn 0.2s ease',
      }}
    >
      <span>ℹ️ {message}</span>
      {onClose && (
        <button
          type="button"
          onClick={onClose}
          aria-label="Close notification"
          style={{
            background: 'none',
            border: 'none',
            color: '#9ca3af',
            cursor: 'pointer',
            fontSize: '16px',
            padding: 0,
          }}
        >
          ×
        </button>
      )}
    </div>
  );
};
