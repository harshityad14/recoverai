import React from 'react';
import { ShieldIcon, CpuIcon, ZapIcon, CheckCircleIcon, BanIcon, AlertTriangleIcon } from '../common/Icons';

export function RecoveryEngineView() {
  const safetyRules = [
    { id: 'MAX_RETRIES_EXCEEDED', name: 'Max Retries Cap', desc: 'Halts automated recovery if a transaction has already been attempted 3 times.', status: 'Active (Deterministic)' },
    { id: 'AMOUNT_EXCEEDS_LIMIT', name: 'High-Value Escalation', desc: 'Overrules LLM recommendations above ₹100,000 (10,000,000 paise) for human sign-off.', status: 'Active (Deterministic)' },
    { id: 'INSUFFICIENT_CONFIDENCE', name: 'Confidence Floor', desc: 'Requires Gemini confidence score ≥ 0.50 before any automated action can be dispatched.', status: 'Active (Deterministic)' },
    { id: 'UNSUPPORTED_ACTION', name: 'Capability Isolation', desc: 'Rejects direct RETRY or REMINDER actions, enforcing tested PAYMENT_LINK mode only.', status: 'Active (Deterministic)' },
    { id: 'TRANSACTION_ALREADY_SETTLED', name: 'Immutability Guard', desc: 'Prevents delayed or duplicate failure webhooks from overriding CAPTURED or RECOVERED states.', status: 'Active (Deterministic)' }
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      {/* Overview Banner */}
      <div
        style={{
          backgroundColor: 'var(--bg-card)',
          border: '1px solid var(--border-card)',
          borderRadius: 'var(--radius-lg)',
          padding: '1.5rem',
          boxShadow: 'var(--shadow-sm)'
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.5rem' }}>
          <div style={{ padding: '0.5rem', borderRadius: '8px', backgroundColor: 'var(--accent-subtle)', color: 'var(--accent-primary)' }}>
            <CpuIcon size={20} />
          </div>
          <div>
            <h2 style={{ fontSize: '1.125rem', fontWeight: 600, color: 'var(--text-primary)' }}>
              Dual-Layer Autonomous Architecture
            </h2>
            <p style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
              Gemini 1.5 Pro provides intelligent recovery suggestions; deterministic Safety Guard enforces strict business and regulatory bounds.
            </p>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1rem', marginTop: '1.25rem' }}>
          <div style={{ backgroundColor: 'var(--bg-app)', padding: '1rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-subtle)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginBottom: '0.35rem' }}>
              <CpuIcon size={16} color="var(--accent-primary)" />
              <span style={{ fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-primary)' }}>Layer 1: Gemini Decision Engine</span>
            </div>
            <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', lineHeight: '1.4' }}>
              Evaluates error codes, gateway responses, failure categorization (AUTHENTICATION, CARD, INSUFFICIENT_FUNDS, ISSUER_DOWN), and customer history to recommend the optimal recovery vector.
            </p>
          </div>

          <div style={{ backgroundColor: 'var(--bg-app)', padding: '1rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-subtle)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginBottom: '0.35rem' }}>
              <ShieldIcon size={16} color="var(--safety-text)" />
              <span style={{ fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-primary)' }}>Layer 2: Deterministic Safety Guard</span>
            </div>
            <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', lineHeight: '1.4' }}>
              Isolated, zero-network rule engine. The LLM is strictly untrusted input; Safety Guard has ultimate veto power and fails closed on any violation.
            </p>
          </div>
        </div>
      </div>

      {/* Safety Guard Rules Grid */}
      <div
        style={{
          backgroundColor: 'var(--bg-card)',
          border: '1px solid var(--border-card)',
          borderRadius: 'var(--radius-lg)',
          padding: '1.5rem',
          boxShadow: 'var(--shadow-sm)'
        }}
      >
        <h3 style={{ fontSize: '0.9375rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '1rem' }}>
          Active Safety Guard Invariants
        </h3>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          {safetyRules.map((rule) => (
            <div
              key={rule.id}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '0.75rem 1rem',
                backgroundColor: 'var(--bg-app)',
                border: '1px solid var(--border-subtle)',
                borderRadius: 'var(--radius-md)',
                flexWrap: 'wrap',
                gap: '0.5rem'
              }}
            >
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <span style={{ fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                    {rule.name}
                  </span>
                  <code style={{ fontSize: '0.7rem', color: 'var(--text-muted)', backgroundColor: 'var(--bg-card)', padding: '1px 5px', borderRadius: '3px' }}>
                    {rule.id}
                  </code>
                </div>
                <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '2px' }}>
                  {rule.desc}
                </p>
              </div>

              <span
                style={{
                  fontSize: '0.7rem',
                  fontWeight: 600,
                  color: 'var(--recovered-text)',
                  backgroundColor: 'var(--recovered-bg)',
                  padding: '2px 8px',
                  borderRadius: '12px',
                  border: '1px solid var(--recovered-border)'
                }}
              >
                {rule.status}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
