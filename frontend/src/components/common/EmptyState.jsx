import React from 'react';
import { ShieldIcon, ZapIcon, RefreshIcon } from './Icons';

export function EmptyState({ onRefresh, loading }) {
  return (
    <div
      style={{
        backgroundColor: 'var(--bg-card)',
        border: '1px solid var(--border-card)',
        borderRadius: 'var(--radius-lg)',
        padding: '4rem 2rem',
        textAlign: 'center',
        maxWidth: '640px',
        margin: '2rem auto',
        boxShadow: 'var(--shadow-sm)'
      }}
    >
      <div
        style={{
          width: '56px',
          height: '56px',
          borderRadius: '50%',
          backgroundColor: 'var(--accent-subtle)',
          color: 'var(--accent-primary)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          margin: '0 auto 1.25rem auto'
        }}
      >
        <ShieldIcon size={28} />
      </div>

      <h3 style={{ fontSize: '1.25rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.5rem' }}>
        No recovery activity yet
      </h3>

      <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)', lineHeight: '1.6', marginBottom: '1.5rem' }}>
        Trigger a Razorpay Test Mode payment failure to see RecoverAI analyze, evaluate with Safety Guard, and autonomously dispatch a recovery payment link.
      </p>

      <div
        style={{
          backgroundColor: 'var(--bg-app)',
          border: '1px solid var(--border-subtle)',
          borderRadius: 'var(--radius-md)',
          padding: '1rem',
          textAlign: 'left',
          fontSize: '0.8125rem',
          color: 'var(--text-secondary)',
          marginBottom: '1.5rem',
          lineHeight: '1.5'
        }}
      >
        <div style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.35rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
          <ZapIcon size={14} color="var(--accent-primary)" />
          How to Test RecoverAI:
        </div>
        <ol style={{ paddingLeft: '1.25rem', display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
          <li>Simulate a failed payment in Razorpay Checkout test mode (e.g. Failure OTP).</li>
          <li>Razorpay webhook sends <code>payment.failed</code> to <code>/webhooks/razorpay</code>.</li>
          <li>RecoverAI verifies signature, evaluates safety invariants, and creates a recovery payment link.</li>
          <li>Upon customer payment, <code>payment.captured</code> webhook marks state as <code>RECOVERED</code>.</li>
        </ol>
      </div>

      <button
        onClick={onRefresh}
        disabled={loading}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '0.5rem',
          backgroundColor: 'var(--accent-primary)',
          color: 'white',
          border: 'none',
          padding: '0.55rem 1.25rem',
          borderRadius: 'var(--radius-md)',
          fontSize: '0.875rem',
          fontWeight: 500,
          cursor: loading ? 'not-allowed' : 'pointer',
          opacity: loading ? 0.7 : 1,
          transition: 'background-color 0.15s ease'
        }}
        onMouseEnter={(e) => {
          if (!loading) e.currentTarget.style.backgroundColor = 'var(--accent-hover)';
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.backgroundColor = 'var(--accent-primary)';
        }}
      >
        <RefreshIcon size={15} />
        <span>{loading ? 'Checking for Events...' : 'Check Recovery Status'}</span>
      </button>
    </div>
  );
}
