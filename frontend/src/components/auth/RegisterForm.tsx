import React, { useState } from 'react';
import { useAuth } from '../../hooks/useAuth';

export interface RegisterFormProps {
  onSwitchToLogin: () => void;
  onRegisteredSuccess: () => void;
}

export const RegisterForm: React.FC<RegisterFormProps> = ({
  onSwitchToLogin,
  onRegisteredSuccess,
}) => {
  const { register, isLoading, error } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [displayName, setDisplayName] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password || !displayName || isLoading) return;
    try {
      await register({ email, password, displayName });
      onRegisteredSuccess();
    } catch {
      // error handled in useAuth
    }
  };

  return (
    <div
      style={{
        maxWidth: '400px',
        width: '100%',
        margin: '0 auto',
        padding: '32px',
        backgroundColor: '#ffffff',
        borderRadius: '12px',
        boxShadow: '0 4px 20px rgba(0,0,0,0.1)',
      }}
    >
      <div style={{ textAlign: 'center', marginBottom: '24px' }}>
        <h1 style={{ fontSize: '24px', fontWeight: 700, color: '#1e3a8a', margin: '0 0 8px 0' }}>
          Create Account
        </h1>
        <p style={{ margin: 0, color: '#6b7280', fontSize: '14px' }}>
          Join the Snapland collaborative team
        </p>
      </div>

      {error && (
        <div
          style={{
            padding: '10px 14px',
            backgroundColor: '#fee2e2',
            color: '#dc2626',
            borderRadius: '6px',
            fontSize: '13px',
            marginBottom: '16px',
          }}
        >
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        <div>
          <label
            htmlFor="registerDisplayName"
            style={{ display: 'block', fontSize: '13px', fontWeight: 500, color: '#374151', marginBottom: '4px' }}
          >
            Display Name
          </label>
          <input
            id="registerDisplayName"
            name="displayName"
            type="text"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            placeholder="Jane Doe"
            required
            style={{
              width: '100%',
              padding: '10px 12px',
              borderRadius: '6px',
              border: '1px solid #d1d5db',
              fontSize: '14px',
              boxSizing: 'border-box',
            }}
          />
        </div>

        <div>
          <label
            htmlFor="registerEmail"
            style={{ display: 'block', fontSize: '13px', fontWeight: 500, color: '#374151', marginBottom: '4px' }}
          >
            Email
          </label>
          <input
            id="registerEmail"
            name="email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            required
            style={{
              width: '100%',
              padding: '10px 12px',
              borderRadius: '6px',
              border: '1px solid #d1d5db',
              fontSize: '14px',
              boxSizing: 'border-box',
            }}
          />
        </div>

        <div>
          <label
            htmlFor="registerPassword"
            style={{ display: 'block', fontSize: '13px', fontWeight: 500, color: '#374151', marginBottom: '4px' }}
          >
            Password
          </label>
          <input
            id="registerPassword"
            name="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••"
            required
            style={{
              width: '100%',
              padding: '10px 12px',
              borderRadius: '6px',
              border: '1px solid #d1d5db',
              fontSize: '14px',
              boxSizing: 'border-box',
            }}
          />
        </div>

        <button
          type="submit"
          disabled={isLoading}
          style={{
            marginTop: '8px',
            padding: '12px',
            backgroundColor: '#2563eb',
            color: '#ffffff',
            border: 'none',
            borderRadius: '6px',
            fontSize: '14px',
            fontWeight: 600,
            cursor: isLoading ? 'wait' : 'pointer',
            transition: 'background-color 0.15s ease',
          }}
        >
          {isLoading ? 'Creating account...' : 'Submit'}
        </button>
      </form>

      <div style={{ marginTop: '20px', textAlign: 'center', fontSize: '13px', color: '#6b7280' }}>
        Already have an account?{' '}
        <button
          type="button"
          onClick={onSwitchToLogin}
          style={{
            background: 'none',
            border: 'none',
            color: '#2563eb',
            fontWeight: 600,
            cursor: 'pointer',
            padding: 0,
          }}
        >
          Login
        </button>
      </div>
    </div>
  );
};
