import React from 'react';
import {
  XIcon,
  CheckCircleIcon,
  AlertTriangleIcon,
  ShieldIcon,
  CpuIcon,
  ZapIcon,
  RupeeIcon,
  ExternalLinkIcon,
  InfoIcon,
  ClockIcon
} from '../common/Icons';

export function TransactionDetailModal({ transaction, onClose }) {
  if (!transaction) return null;

  const formatCurrency = (paise) => {
    if (typeof paise !== 'number' || isNaN(paise)) return '₹0.00';
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 2,
    }).format(paise / 100);
  };

  const formatDate = (isoString) => {
    if (!isoString) return '--';
    try {
      return new Date(isoString).toLocaleString('en-IN', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: true
      });
    } catch {
      return isoString;
    }
  };

  const isRecovered = transaction.status === 'RECOVERED';
  const isCaptured = transaction.status === 'CAPTURED';
  const isPending = transaction.status === 'RECOVERY_PENDING';
  const isStopped = transaction.status === 'STOPPED';

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(15, 23, 42, 0.4)',
        backdropFilter: 'blur(2px)',
        display: 'flex',
        justifyContent: 'flex-end',
        zIndex: 60,
        animation: 'fadeIn 0.15s ease'
      }}
      onClick={onClose}
    >
      <div
        style={{
          width: '100%',
          maxWidth: '580px',
          backgroundColor: 'var(--bg-card)',
          height: '100vh',
          boxShadow: 'var(--shadow-drawer)',
          display: 'flex',
          flexDirection: 'column',
          overflowY: 'auto'
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Drawer Header */}
        <div
          style={{
            padding: '1.25rem 1.5rem',
            borderBottom: '1px solid var(--border-subtle)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            position: 'sticky',
            top: 0,
            backgroundColor: 'var(--bg-card)',
            zIndex: 10
          }}
        >
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <h2 style={{ fontSize: '1.125rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                Transaction Audit Detail
              </h2>
              <span
                style={{
                  fontSize: '0.7rem',
                  fontWeight: 600,
                  padding: '1px 8px',
                  borderRadius: '12px',
                  backgroundColor: isRecovered ? 'var(--recovered-bg)' : isCaptured ? 'var(--captured-bg)' : isPending ? 'var(--pending-bg)' : isStopped ? 'var(--stopped-bg)' : 'var(--failed-bg)',
                  color: isRecovered ? 'var(--recovered-text)' : isCaptured ? 'var(--captured-text)' : isPending ? 'var(--pending-text)' : isStopped ? 'var(--stopped-text)' : 'var(--failed-text)',
                  border: '1px solid'
                }}
              >
                {transaction.status}
              </span>
            </div>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '2px' }}>
              ID: <code>{transaction.transaction_id || transaction.payment_id}</code>
            </div>
          </div>

          <button
            onClick={onClose}
            style={{
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              color: 'var(--text-muted)',
              padding: '6px',
              borderRadius: 'var(--radius-sm)'
            }}
            onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = 'var(--bg-subtle)')}
            onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
          >
            <XIcon size={20} />
          </button>
        </div>

        {/* Drawer Body */}
        <div style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          
          {/* Causality Callout Banner: RECOVERED vs CAPTURED distinction */}
          {isRecovered && (
            <div
              style={{
                backgroundColor: 'var(--recovered-bg)',
                border: '1px solid var(--recovered-border)',
                borderRadius: 'var(--radius-md)',
                padding: '0.875rem 1rem',
                display: 'flex',
                alignItems: 'flex-start',
                gap: '0.75rem'
              }}
            >
              <CheckCircleIcon size={18} color="var(--recovered-text)" />
              <div>
                <div style={{ fontSize: '0.8125rem', fontWeight: 600, color: 'var(--recovered-text)' }}>
                  Causally Attributed Recovery (RECOVERED)
                </div>
                <p style={{ fontSize: '0.75rem', color: '#166534', marginTop: '2px', lineHeight: '1.4' }}>
                  This payment succeeded via the Razorpay payment link dispatched by RecoverAI (<code>{transaction.payment_link_id || 'plink_verified'}</code>). The recovery is provably and causally attributed to RecoverAI.
                </p>
              </div>
            </div>
          )}

          {isCaptured && (
            <div
              style={{
                backgroundColor: 'var(--captured-bg)',
                border: '1px solid var(--captured-border)',
                borderRadius: 'var(--radius-md)',
                padding: '0.875rem 1rem',
                display: 'flex',
                alignItems: 'flex-start',
                gap: '0.75rem'
              }}
            >
              <InfoIcon size={18} color="var(--captured-text)" />
              <div>
                <div style={{ fontSize: '0.8125rem', fontWeight: 600, color: 'var(--captured-text)' }}>
                  Organic Capture (CAPTURED &mdash; Disclaimed Attribution)
                </div>
                <p style={{ fontSize: '0.75rem', color: '#1e40af', marginTop: '2px', lineHeight: '1.4' }}>
                  The customer completed this payment through an organic channel outside RecoverAI (e.g. direct website checkout with alternative card). RecoverAI strictly refuses to take attribution credit for organic payments.
                </p>
              </div>
            </div>
          )}

          {/* Core Transaction Metadata Cards */}
          <div
            style={{
              backgroundColor: 'var(--bg-app)',
              border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-md)',
              padding: '1rem',
              display: 'grid',
              gridTemplateColumns: '1fr 1fr',
              gap: '0.75rem'
            }}
          >
            <div>
              <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>
                Amount
              </span>
              <div className="tabular-nums" style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                {formatCurrency(transaction.amount)}
              </div>
            </div>
            <div>
              <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>
                Customer
              </span>
              <div style={{ fontSize: '0.8125rem', fontWeight: 500, color: 'var(--text-primary)', wordBreak: 'break-all' }}>
                {transaction.customer_email || transaction.customer_id || 'Guest Customer'}
              </div>
            </div>
            <div>
              <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>
                Razorpay Payment ID
              </span>
              <div style={{ fontSize: '0.75rem', fontFamily: 'monospace', color: 'var(--text-secondary)' }}>
                {transaction.payment_id}
              </div>
            </div>
            <div>
              <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>
                Order ID
              </span>
              <div style={{ fontSize: '0.75rem', fontFamily: 'monospace', color: 'var(--text-secondary)' }}>
                {transaction.order_id || '--'}
              </div>
            </div>
          </div>

          {/* Failure Summary */}
          <div
            style={{
              backgroundColor: 'var(--bg-card)',
              border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-md)',
              padding: '1rem'
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginBottom: '0.35rem' }}>
              <AlertTriangleIcon size={14} color="var(--failed-text)" />
              <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--failed-text)', textTransform: 'uppercase' }}>
                Original Failure
              </span>
            </div>
            <div style={{ fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-primary)' }}>
              {transaction.error_code}
            </div>
            <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '2px' }}>
              {transaction.error_description || 'No description provided by gateway.'}
            </p>
          </div>

          {/* Visual Recovery Timeline (01 to 06) */}
          <div>
            <h3 style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.75rem' }}>
              Audit Trail & Execution Timeline
            </h3>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', position: 'relative', paddingLeft: '1.25rem' }}>
              {/* Vertical timeline connector */}
              <div
                style={{
                  position: 'absolute',
                  left: '6px',
                  top: '12px',
                  bottom: '12px',
                  width: '2px',
                  backgroundColor: 'var(--border-subtle)'
                }}
              />

              {/* 01 Payment Failed */}
              <div style={{ position: 'relative' }}>
                <div
                  style={{
                    position: 'absolute',
                    left: '-1.25rem',
                    top: '2px',
                    width: '14px',
                    height: '14px',
                    borderRadius: '50%',
                    backgroundColor: 'var(--failed-bg)',
                    border: '2px solid var(--failed-text)',
                    boxSizing: 'border-box'
                  }}
                />
                <div style={{ fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                  01 Payment Failed
                </div>
                <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                  {formatDate(transaction.created_at)}
                </div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '2px' }}>
                  Razorpay webhook <code>payment.failed</code> ingested into Redis queue.
                </div>
              </div>

              {/* 02 Failure Analyzed */}
              <div style={{ position: 'relative' }}>
                <div
                  style={{
                    position: 'absolute',
                    left: '-1.25rem',
                    top: '2px',
                    width: '14px',
                    height: '14px',
                    borderRadius: '50%',
                    backgroundColor: 'var(--bg-subtle)',
                    border: '2px solid var(--text-muted)',
                    boxSizing: 'border-box'
                  }}
                />
                <div style={{ fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                  02 Failure Analyzed
                </div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '2px' }}>
                  Failure taxonomy classified as eligible for automated evaluation.
                </div>
              </div>

              {/* 03 Gemini Recommendation */}
              <div style={{ position: 'relative' }}>
                <div
                  style={{
                    position: 'absolute',
                    left: '-1.25rem',
                    top: '2px',
                    width: '14px',
                    height: '14px',
                    borderRadius: '50%',
                    backgroundColor: 'var(--accent-subtle)',
                    border: '2px solid var(--accent-primary)',
                    boxSizing: 'border-box'
                  }}
                />
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <span style={{ fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                    03 Gemini Recommendation
                  </span>
                  <span
                    style={{
                      fontSize: '0.65rem',
                      fontWeight: 600,
                      backgroundColor: 'var(--accent-subtle)',
                      color: 'var(--accent-primary)',
                      padding: '1px 5px',
                      borderRadius: '3px'
                    }}
                  >
                    Recommendation Only
                  </span>
                </div>
                {transaction.ai_recommendation ? (
                  <div style={{ marginTop: '0.25rem' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.75rem' }}>
                      <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                        Action: {transaction.ai_recommendation.action}
                      </span>
                      <span style={{ color: 'var(--text-muted)' }}>&bull;</span>
                      <span style={{ color: 'var(--text-secondary)' }}>
                        Confidence: {(transaction.ai_recommendation.confidence * 100).toFixed(0)}%
                      </span>
                    </div>
                    <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '3px', fontStyle: 'italic', backgroundColor: 'var(--bg-app)', padding: '0.5rem', borderRadius: '4px', border: '1px solid var(--border-subtle)' }}>
                      "{transaction.ai_recommendation.rationale}"
                    </p>
                  </div>
                ) : (
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                    Bypassed (ineligible failure).
                  </div>
                )}
              </div>

              {/* 04 Safety Guard Decision */}
              <div style={{ position: 'relative' }}>
                <div
                  style={{
                    position: 'absolute',
                    left: '-1.25rem',
                    top: '2px',
                    width: '14px',
                    height: '14px',
                    borderRadius: '50%',
                    backgroundColor: 'var(--safety-bg)',
                    border: '2px solid var(--safety-text)',
                    boxSizing: 'border-box'
                  }}
                />
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <span style={{ fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                    04 Safety Guard Decision
                  </span>
                  <span
                    style={{
                      fontSize: '0.65rem',
                      fontWeight: 600,
                      backgroundColor: 'var(--safety-bg)',
                      color: 'var(--safety-text)',
                      padding: '1px 5px',
                      borderRadius: '3px'
                    }}
                  >
                    Final Authority
                  </span>
                </div>
                {transaction.safety_guard ? (
                  <div style={{ marginTop: '0.25rem', fontSize: '0.75rem' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                      <span style={{ fontWeight: 600, color: transaction.safety_guard.decision === 'OVERRIDE' ? 'var(--safety-text)' : 'var(--recovered-text)' }}>
                        Decision: {transaction.safety_guard.decision}
                      </span>
                      <span style={{ color: 'var(--text-muted)' }}>&bull;</span>
                      <span style={{ color: 'var(--text-secondary)' }}>
                        Rule: <code>{transaction.safety_guard.rule_id}</code>
                      </span>
                    </div>
                    <div style={{ marginTop: '2px', color: 'var(--text-secondary)' }}>
                      Final Action: <strong>{transaction.safety_guard.final_action}</strong>
                    </div>
                    {transaction.safety_guard.reason && (
                      <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '2px' }}>
                        {transaction.safety_guard.reason}
                      </div>
                    )}
                  </div>
                ) : (
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                    Evaluated against deterministic invariants.
                  </div>
                )}
              </div>

              {/* 05 Recovery Action */}
              <div style={{ position: 'relative' }}>
                <div
                  style={{
                    position: 'absolute',
                    left: '-1.25rem',
                    top: '2px',
                    width: '14px',
                    height: '14px',
                    borderRadius: '50%',
                    backgroundColor: 'var(--pending-bg)',
                    border: '2px solid var(--pending-text)',
                    boxSizing: 'border-box'
                  }}
                />
                <div style={{ fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                  05 Recovery Action Execution
                </div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '2px' }}>
                  Execution: <strong>{transaction.action_execution?.result || (transaction.status === 'STOPPED' ? 'SKIPPED' : 'SUCCESS')}</strong>
                </div>
                {transaction.payment_link_id && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginTop: '3px' }}>
                    <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Reference:</span>
                    <code style={{ fontSize: '0.72rem', color: 'var(--accent-primary)', backgroundColor: 'var(--accent-subtle)', padding: '1px 5px', borderRadius: '3px' }}>
                      {transaction.payment_link_id}
                    </code>
                  </div>
                )}
              </div>

              {/* 06 Payment Outcome */}
              <div style={{ position: 'relative' }}>
                <div
                  style={{
                    position: 'absolute',
                    left: '-1.25rem',
                    top: '2px',
                    width: '14px',
                    height: '14px',
                    borderRadius: '50%',
                    backgroundColor: isRecovered ? 'var(--recovered-bg)' : isCaptured ? 'var(--captured-bg)' : isPending ? 'var(--pending-bg)' : isStopped ? 'var(--stopped-bg)' : 'var(--failed-bg)',
                    border: `2px solid ${isRecovered ? 'var(--recovered-text)' : isCaptured ? 'var(--captured-text)' : isPending ? 'var(--pending-text)' : isStopped ? 'var(--stopped-text)' : 'var(--failed-text)'}`,
                    boxSizing: 'border-box'
                  }}
                />
                <div style={{ fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                  06 Payment Outcome &bull; {transaction.status}
                </div>
                <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                  {formatDate(transaction.outcome?.recovered_at || transaction.updated_at)}
                </div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '2px' }}>
                  {transaction.outcome?.attribution_note || `Final state reached: ${transaction.status}.`}
                </div>
              </div>
            </div>
          </div>

        </div>

        {/* Drawer Footer */}
        <div
          style={{
            padding: '1rem 1.5rem',
            borderTop: '1px solid var(--border-subtle)',
            backgroundColor: 'var(--bg-app)',
            marginTop: 'auto',
            display: 'flex',
            justifyContent: 'flex-end'
          }}
        >
          <button
            onClick={onClose}
            style={{
              padding: '0.45rem 1rem',
              backgroundColor: 'var(--bg-card)',
              border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-md)',
              fontSize: '0.8125rem',
              fontWeight: 500,
              cursor: 'pointer',
              color: 'var(--text-primary)'
            }}
          >
            Close Detail
          </button>
        </div>
      </div>
    </div>
  );
}
