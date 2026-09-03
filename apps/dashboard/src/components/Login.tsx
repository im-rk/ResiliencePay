import React, { useState, useEffect } from 'react';
import { Shield, Key, Loader2, CheckCircle2 } from 'lucide-react';

interface LoginProps {
  onLogin: () => void;
}

export const Login: React.FC<LoginProps> = ({ onLogin }) => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [status, setStatus] = useState<'idle' | 'authenticating' | 'checking_permissions' | 'success'>('idle');
  const [error, setError] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.endsWith('@razorpay.com')) {
      setError('Please use your @razorpay.com employee email address.');
      return;
    }
    setError('');
    setStatus('authenticating');
  };

  useEffect(() => {
    if (status === 'authenticating') {
      const t = setTimeout(() => setStatus('checking_permissions'), 1200);
      return () => clearTimeout(t);
    }
    if (status === 'checking_permissions') {
      const t = setTimeout(() => setStatus('success'), 1200);
      return () => clearTimeout(t);
    }
    if (status === 'success') {
      const t = setTimeout(() => onLogin(), 600);
      return () => clearTimeout(t);
    }
  }, [status, onLogin]);

  return (
    <div style={{
      display: 'flex',
      justifyContent: 'center',
      alignItems: 'center',
      minHeight: '100vh',
      width: '100%',
      padding: '20px',
      boxSizing: 'border-box'
    }}>
      <div className="glass-panel animate-fade-in" style={{ 
        width: '100%', 
        maxWidth: '440px',
        padding: '48px',
        position: 'relative',
        overflow: 'hidden'
      }}>
        {/* Glow effect in background of card */}
        <div style={{
          position: 'absolute',
          top: '-50%', left: '-50%', right: '-50%', bottom: '-50%',
          background: 'radial-gradient(circle at 50% 0%, rgba(14, 165, 233, 0.15), transparent 50%)',
          pointerEvents: 'none'
        }} />

        <div style={{ textAlign: 'center', marginBottom: '32px', position: 'relative' }}>
          <div style={{ 
            width: '72px', 
            height: '72px', 
            borderRadius: '20px', 
            background: 'linear-gradient(135deg, var(--color-accent), #3b82f6)',
            margin: '0 auto 24px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            boxShadow: '0 8px 32px var(--color-accent-glow)'
          }}>
            <Shield size={36} color="white" />
          </div>
          <h1 style={{ fontSize: '28px', marginBottom: '8px' }}>ResiliencePay</h1>
          <p className="text-muted" style={{ margin: 0 }}>Enterprise Authentication</p>
        </div>

        {status === 'idle' ? (
          <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '24px', position: 'relative' }}>
            <div>
              <label style={{ display: 'block', marginBottom: '8px', fontSize: '13px', textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--color-text-secondary)', fontWeight: 600 }}>
                Work Email
              </label>
              <input 
                type="email" 
                className="input-field" 
                placeholder="you@razorpay.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>
            <div>
              <label style={{ display: 'block', marginBottom: '8px', fontSize: '13px', textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--color-text-secondary)', fontWeight: 600 }}>
                Password
              </label>
              <input 
                type="password" 
                className="input-field" 
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>
            
            {error && (
              <div style={{ color: 'var(--color-danger)', fontSize: '13px', background: 'var(--color-danger-bg)', padding: '10px 12px', borderRadius: '8px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span className="badge-dot" style={{ background: 'var(--color-danger)' }} />
                {error}
              </div>
            )}
            
            <button type="submit" className="btn-primary" style={{ marginTop: '8px', display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '8px' }}>
              <Key size={18} /> Secure Sign In
            </button>
          </form>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '24px', padding: '24px 0' }}>
            {status === 'success' ? (
              <CheckCircle2 size={48} color="var(--color-success)" className="animate-fade-in" />
            ) : (
              <Loader2 size={48} color="var(--color-accent)" className="animate-spin" style={{ animation: 'spin 1s linear infinite' }} />
            )}
            
            <div style={{ textAlign: 'center' }}>
              <h3 style={{ fontSize: '18px', marginBottom: '8px' }}>
                {status === 'authenticating' && 'Authenticating Identity...'}
                {status === 'checking_permissions' && 'Verifying Access Level...'}
                {status === 'success' && 'Access Granted'}
              </h3>
              <p className="text-muted" style={{ fontSize: '14px' }}>
                {status === 'authenticating' && 'Verifying credentials against Razorpay directory'}
                {status === 'checking_permissions' && 'Checking role-based access controls'}
                {status === 'success' && 'Redirecting to console...'}
              </p>
            </div>

            <div style={{ width: '100%', height: '4px', background: 'rgba(255,255,255,0.1)', borderRadius: '2px', overflow: 'hidden' }}>
              <div style={{
                height: '100%',
                background: 'var(--color-accent)',
                width: status === 'authenticating' ? '33%' : status === 'checking_permissions' ? '66%' : '100%',
                transition: 'width 1.2s ease-in-out'
              }} />
            </div>
          </div>
        )}
        
        <style>{`
          @keyframes spin { 100% { transform: rotate(360deg); } }
        `}</style>
      </div>
    </div>
  );
};
