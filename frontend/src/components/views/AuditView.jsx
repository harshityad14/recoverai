import React from 'react';
import { DatabaseIcon, ShieldIcon, CheckCircleIcon, ZapIcon } from '../common/Icons';

export function AuditView() {
  const auditGuarantees = [
    { title: 'HMAC-SHA256 Webhook Verification', desc: 'Every incoming event is verified using Razorpay Webhook Secret. Invalid signatures are rejected immediately with HTTP 400.' },
    { title: 'Redis Set Idempotency', desc: 'Unique event IDs (X-Razorpay-Event-Id) are checked against Redis cache. Duplicate webhooks are acknowledged safely without re-processing.' },
    { title: 'Deterministic Safety Veto', desc: 'No LLM output directly triggers payment APIs. All actions pass through the isolated SafetyGuard service before reaching ActionExecutor.' },
    { title: 'Causal Attribution Verification', desc: 'payment.captured events must match payment_link_id or notes.transaction_id to qualify as RECOVERED; organic payments receive CAPTURED.' },
    { title: 'Secret Redaction in Audit Logs', desc: 'API keys, credentials, and merchant secrets are strictly excluded from database models, logs, and HTTP payloads.' }
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
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
          <div style={{ padding: '0.5rem', borderRadius: '8px', backgroundColor: 'var(--bg-subtle)', color: 'var(--text-secondary)' }}>
            <DatabaseIcon size={20} />
          </div>
          <div>
            <h2 style={{ fontSize: '1.125rem', fontWeight: 600, color: 'var(--text-primary)' }}>
              Audit Trail & Security Guarantees
            </h2>
            <p style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
              Enterprise compliance and safety boundaries verified through 169 automated tests.
            </p>
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', marginTop: '1.25rem' }}>
          {auditGuarantees.map((item, idx) => (
            <div
              key={idx}
              style={{
                display: 'flex',
                alignItems: 'flex-start',
                gap: '0.75rem',
                padding: '0.875rem 1rem',
                backgroundColor: 'var(--bg-app)',
                borderRadius: 'var(--radius-md)',
                border: '1px solid var(--border-subtle)'
              }}
            >
              <div style={{ marginTop: '2px' }}>
                <CheckCircleIcon size={16} color="var(--recovered-text)" />
              </div>
              <div>
                <div style={{ fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                  {item.title}
                </div>
                <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '2px', lineHeight: '1.4' }}>
                  {item.desc}
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
