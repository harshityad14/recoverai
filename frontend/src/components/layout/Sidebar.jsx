import React from 'react';
import {
  ShieldIcon,
  ActivityIcon,
  RupeeIcon,
  ZapIcon,
  DatabaseIcon,
  CpuIcon,
  LinkIcon,
  XIcon
} from '../common/Icons';

export function Sidebar({ activeTab, setActiveTab, mobileOpen, setMobileOpen, healthData }) {
  const navItems = [
    { id: 'dashboard', label: 'Dashboard', icon: ActivityIcon },
    { id: 'transactions', label: 'Transactions', icon: RupeeIcon },
    { id: 'recovery', label: 'Recovery Engine', icon: ZapIcon },
    { id: 'analytics', label: 'Analytics', icon: CpuIcon },
    { id: 'audit', label: 'Audit Logs', icon: DatabaseIcon },
  ];

  const handleNavClick = (id) => {
    setActiveTab(id);
    if (setMobileOpen) setMobileOpen(false);
  };

  return (
    <>
      {/* Mobile backdrop */}
      {mobileOpen && (
        <div
          onClick={() => setMobileOpen(false)}
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(15, 23, 42, 0.4)',
            zIndex: 40,
            backdropFilter: 'blur(2px)'
          }}
        />
      )}

      <aside
        style={{
          width: 'var(--sidebar-width)',
          backgroundColor: 'var(--bg-sidebar)',
          borderRight: '1px solid var(--border-subtle)',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
          zIndex: 50,
          transition: 'transform 0.2s ease-in-out',
          position: 'sticky',
          top: 0,
          height: '100vh',
          flexShrink: 0
        }}
        className={mobileOpen ? 'sidebar-mobile-open' : ''}
      >
        <div>
          {/* Logo Header */}
          <div
            style={{
              padding: '1.25rem 1.5rem',
              borderBottom: '1px solid var(--border-subtle)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between'
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              <div
                style={{
                  width: '32px',
                  height: '32px',
                  borderRadius: '6px',
                  backgroundColor: 'var(--accent-subtle)',
                  border: '1px solid var(--accent-border)',
                  color: 'var(--accent-primary)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center'
                }}
              >
                <ShieldIcon size={18} />
              </div>
              <div>
                <span
                  style={{
                    fontSize: '1.05rem',
                    fontWeight: 700,
                    color: 'var(--text-primary)',
                    letterSpacing: '-0.01em'
                  }}
                >
                  RecoverAI
                </span>
                <span
                  style={{
                    display: 'block',
                    fontSize: '0.68rem',
                    color: 'var(--text-muted)',
                    textTransform: 'uppercase',
                    letterSpacing: '0.05em',
                    fontWeight: 600
                  }}
                >
                  Razorpay Agent
                </span>
              </div>
            </div>

            {/* Mobile close button */}
            {mobileOpen && (
              <button
                onClick={() => setMobileOpen(false)}
                style={{
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  color: 'var(--text-muted)',
                  padding: '4px'
                }}
              >
                <XIcon size={20} />
              </button>
            )}
          </div>

          {/* Navigation Links */}
          <nav style={{ padding: '1rem 0.75rem', display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
            <div
              style={{
                fontSize: '0.7rem',
                fontWeight: 600,
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
                color: 'var(--text-light)',
                padding: '0.5rem 0.75rem 0.25rem 0.75rem'
              }}
            >
              Core Platform
            </div>

            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive = activeTab === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => handleNavClick(item.id)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.75rem',
                    width: '100%',
                    padding: '0.55rem 0.75rem',
                    borderRadius: 'var(--radius-md)',
                    border: 'none',
                    backgroundColor: isActive ? 'var(--accent-subtle)' : 'transparent',
                    color: isActive ? 'var(--accent-primary)' : 'var(--text-secondary)',
                    fontWeight: isActive ? 600 : 500,
                    fontSize: '0.875rem',
                    cursor: 'pointer',
                    transition: 'all 0.15s ease',
                    textAlign: 'left'
                  }}
                  onMouseEnter={(e) => {
                    if (!isActive) {
                      e.currentTarget.style.backgroundColor = 'var(--bg-subtle)';
                      e.currentTarget.style.color = 'var(--text-primary)';
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (!isActive) {
                      e.currentTarget.style.backgroundColor = 'transparent';
                      e.currentTarget.style.color = 'var(--text-secondary)';
                    }
                  }}
                >
                  <Icon size={17} color={isActive ? 'var(--accent-primary)' : 'var(--text-muted)'} />
                  <span>{item.label}</span>
                </button>
              );
            })}
          </nav>
        </div>

        {/* Footer Area */}
        <div
          style={{
            padding: '1rem',
            borderTop: '1px solid var(--border-subtle)',
            backgroundColor: 'var(--bg-app)'
          }}
        >
          <div
            style={{
              padding: '0.75rem',
              backgroundColor: 'var(--bg-card)',
              border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-md)'
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.35rem' }}>
              <span style={{ fontSize: '0.7rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                Gateway
              </span>
              <span
                style={{
                  fontSize: '0.65rem',
                  fontWeight: 600,
                  padding: '1px 6px',
                  borderRadius: '12px',
                  backgroundColor: 'var(--pending-bg)',
                  color: 'var(--pending-text)',
                  border: '1px solid var(--pending-border)'
                }}
              >
                Test Mode
              </span>
            </div>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-primary)', fontWeight: 500 }}>
              Razorpay Test Key
            </div>
            <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', marginTop: '2px' }}>
              rzp_test_••••••••
            </div>
          </div>
        </div>
      </aside>
    </>
  );
}
