import React from 'react';
import {
  AlertTriangleIcon,
  CpuIcon,
  ShieldIcon,
  ZapIcon,
  CheckCircleIcon,
  RupeeIcon,
  ArrowRightIcon
} from '../common/Icons';

export function WorkflowVisual() {
  const steps = [
    {
      step: '01',
      title: 'Payment Failed',
      badge: 'Webhook',
      badgeColor: 'var(--failed-text)',
      badgeBg: 'var(--failed-bg)',
      icon: AlertTriangleIcon,
      desc: 'Razorpay webhook signature verified & queued'
    },
    {
      step: '02',
      title: 'AI Analysis',
      badge: 'Gemini 1.5',
      badgeColor: 'var(--accent-primary)',
      badgeBg: 'var(--accent-subtle)',
      icon: CpuIcon,
      desc: 'Failure taxonomy & recommendation'
    },
    {
      step: '03',
      title: 'Safety Guard',
      badge: 'Final Authority',
      badgeColor: 'var(--safety-text)',
      badgeBg: 'var(--safety-bg)',
      icon: ShieldIcon,
      desc: 'Deterministic rules override LLM if unsafe'
    },
    {
      step: '04',
      title: 'Recovery Action',
      badge: 'ActionExecutor',
      badgeColor: 'var(--pending-text)',
      badgeBg: 'var(--pending-bg)',
      icon: ZapIcon,
      desc: 'Dispatches Razorpay Test Payment Link'
    },
    {
      step: '05',
      title: 'Payment Captured',
      badge: 'Verification',
      badgeColor: 'var(--captured-text)',
      badgeBg: 'var(--captured-bg)',
      icon: CheckCircleIcon,
      desc: 'Webhook correlates causal attribution'
    },
    {
      step: '06',
      title: 'Recovered Revenue',
      badge: 'Attribution',
      badgeColor: 'var(--recovered-text)',
      badgeBg: 'var(--recovered-bg)',
      icon: RupeeIcon,
      desc: 'Verified causal recovery added to metrics'
    }
  ];

  return (
    <div
      style={{
        backgroundColor: 'var(--bg-card)',
        border: '1px solid var(--border-card)',
        borderRadius: 'var(--radius-lg)',
        padding: '1.25rem 1.5rem',
        marginBottom: '1.5rem',
        boxShadow: 'var(--shadow-sm)'
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem', flexWrap: 'wrap', gap: '0.5rem' }}>
        <div>
          <h3 style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: 'var(--accent-primary)' }} />
            Autonomous Recovery Pipeline
          </h3>
          <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '2px' }}>
            Deterministic safety architecture: Gemini recommends &bull; SafetyGuard enforces &bull; ActionExecutor executes &bull; Webhooks verify causality
          </p>
        </div>
        <span
          style={{
            fontSize: '0.7rem',
            padding: '2px 8px',
            borderRadius: '12px',
            backgroundColor: 'var(--bg-subtle)',
            color: 'var(--text-secondary)',
            fontWeight: 500,
            border: '1px solid var(--border-subtle)'
          }}
        >
          Phase 7 Orchestration
        </span>
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
          gap: '0.75rem',
          position: 'relative'
        }}
      >
        {steps.map((item, idx) => {
          const Icon = item.icon;
          return (
            <div
              key={item.step}
              style={{
                backgroundColor: 'var(--bg-app)',
                border: '1px solid var(--border-subtle)',
                borderRadius: 'var(--radius-md)',
                padding: '0.75rem 0.875rem',
                position: 'relative',
                transition: 'border-color 0.15s ease'
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.4rem' }}>
                <span style={{ fontSize: '0.65rem', fontWeight: 700, color: 'var(--text-light)', letterSpacing: '0.05em' }}>
                  {item.step}
                </span>
                <span
                  style={{
                    fontSize: '0.65rem',
                    fontWeight: 600,
                    padding: '1px 5px',
                    borderRadius: '4px',
                    backgroundColor: item.badgeBg,
                    color: item.badgeColor
                  }}
                >
                  {item.badge}
                </span>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginBottom: '0.25rem' }}>
                <Icon size={14} color={item.badgeColor} />
                <span style={{ fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                  {item.title}
                </span>
              </div>

              <p style={{ fontSize: '0.7rem', color: 'var(--text-muted)', lineHeight: '1.3' }}>
                {item.desc}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}
