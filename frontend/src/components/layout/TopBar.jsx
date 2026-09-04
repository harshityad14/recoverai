import React from 'react';
import { RefreshIcon, ZapIcon, MenuIcon } from '../common/Icons';

export function TopBar({ activeTab, onRefresh, loading, backendConnected, setMobileOpen }) {
  const getPageTitle = () => {
    switch (activeTab) {
      case 'transactions':
        return 'Transactions & Recovery Log';
      case 'recovery':
        return 'Autonomous Recovery Engine';
      case 'analytics':
        return 'Recovery Analytics & KPIs';
      case 'audit':
        return 'Decision Audit Trail';
      case 'dashboard':
      default:
        return 'Payment Recovery Dashboard';
    }
  };

  return (
    <header
      style={{
        height: 'var(--topbar-height)',
        backgroundColor: 'var(--bg-card)',
        borderBottom: '1px solid var(--border-subtle)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 1.5rem',
        position: 'sticky',
        top: 0,
        zIndex: 30
      }}
    >
      {/* Left: Mobile hamburger & breadcrumbs */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
        <button
          onClick={() => setMobileOpen(true)}
          style={{
            display: 'none',
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            color: 'var(--text-secondary)',
            padding: '4px'
          }}
          className="mobile-menu-trigger"
        >
          <MenuIcon size={20} />
        </button>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <span style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
            RecoverAI
          </span>
          <span style={{ color: 'var(--text-light)', fontSize: '0.75rem' }}>/</span>
          <span style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-primary)' }}>
            {getPageTitle()}
          </span>
        </div>
      </div>

      {/* Right: Test Mode Badge, Connection Status, Refresh Button, Profile */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.875rem' }}>
        {/* Razorpay Test Mode Indicator */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.4rem',
            padding: '0.25rem 0.65rem',
            backgroundColor: 'var(--pending-bg)',
            border: '1px solid var(--pending-border)',
            borderRadius: '9999px',
            fontSize: '0.75rem',
            fontWeight: 600,
            color: 'var(--pending-text)'
          }}
          title="Running in Razorpay Test Mode. All transactions and payment links use sandbox mock credentials."
        >
          <ZapIcon size={13} color="var(--pending-text)" />
          <span>TEST MODE</span>
        </div>

        {/* Backend Connectivity Status */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.4rem',
            fontSize: '0.75rem',
            color: backendConnected ? 'var(--text-secondary)' : 'var(--failed-text)',
            padding: '0.25rem 0.5rem',
            borderRadius: 'var(--radius-sm)',
            backgroundColor: 'var(--bg-subtle)'
          }}
          title={backendConnected ? 'Connected to FastAPI backend on port 8000' : 'Cannot connect to backend server'}
        >
          <span
            style={{
              width: '7px',
              height: '7px',
              borderRadius: '50%',
              backgroundColor: backendConnected ? '#10b981' : '#ef4444',
              display: 'inline-block'
            }}
          />
          <span style={{ fontWeight: 500 }}>
            {backendConnected ? 'Live API' : 'Offline'}
          </span>
        </div>

        {/* Refresh button */}
        <button
          onClick={onRefresh}
          disabled={loading}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.4rem',
            backgroundColor: 'var(--bg-card)',
            border: '1px solid var(--border-subtle)',
            color: 'var(--text-secondary)',
            padding: '0.4rem 0.75rem',
            borderRadius: 'var(--radius-md)',
            fontSize: '0.8125rem',
            fontWeight: 500,
            cursor: loading ? 'not-allowed' : 'pointer',
            transition: 'all 0.15s ease',
            opacity: loading ? 0.7 : 1
          }}
          onMouseEnter={(e) => {
            if (!loading) {
              e.currentTarget.style.borderColor = 'var(--border-hover)';
              e.currentTarget.style.backgroundColor = 'var(--bg-subtle)';
            }
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.borderColor = 'var(--border-subtle)';
            e.currentTarget.style.backgroundColor = 'var(--bg-card)';
          }}
        >
          <span style={{ display: 'inline-flex', animation: loading ? 'spin 1s linear infinite' : 'none' }}>
            <RefreshIcon size={14} />
          </span>
          <span className="hide-on-mobile">{loading ? 'Syncing...' : 'Refresh'}</span>
        </button>
      </div>
    </header>
  );
}
