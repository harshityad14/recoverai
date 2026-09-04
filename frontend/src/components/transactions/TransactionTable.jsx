import React, { useState } from 'react';
import {
  SearchIcon,
  FilterIcon,
  ChevronRightIcon,
  CheckCircleIcon,
  AlertTriangleIcon,
  ClockIcon,
  BanIcon,
  ShieldIcon,
  InfoIcon
} from '../common/Icons';

export function TransactionTable({ transactions, isDemoData, onSelectTransaction, loading }) {
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState('ALL');

  // Format currency in INR
  const formatCurrency = (paise) => {
    if (typeof paise !== 'number' || isNaN(paise)) return '₹0.00';
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 2,
    }).format(paise / 100);
  };

  // Format relative or compact timestamp
  const formatTime = (isoString) => {
    if (!isoString) return '--';
    try {
      const date = new Date(isoString);
      return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: true });
    } catch {
      return '--';
    }
  };

  // Filter transactions
  const filtered = (transactions || []).filter((tx) => {
    const matchesSearch =
      (tx.payment_id || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
      (tx.transaction_id || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
      (tx.customer_email || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
      (tx.error_code || '').toLowerCase().includes(searchTerm.toLowerCase());

    const matchesStatus = statusFilter === 'ALL' || tx.status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  // Badge renderers
  const renderStatusBadge = (status) => {
    switch (status) {
      case 'RECOVERED':
        return (
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '4px',
              padding: '2px 8px',
              borderRadius: '9999px',
              fontSize: '0.72rem',
              fontWeight: 600,
              backgroundColor: 'var(--recovered-bg)',
              color: 'var(--recovered-text)',
              border: '1px solid var(--recovered-border)'
            }}
          >
            <span style={{ width: '5px', height: '5px', borderRadius: '50%', backgroundColor: 'var(--recovered-text)' }} />
            RECOVERED
          </span>
        );
      case 'CAPTURED':
        return (
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '4px',
              padding: '2px 8px',
              borderRadius: '9999px',
              fontSize: '0.72rem',
              fontWeight: 600,
              backgroundColor: 'var(--captured-bg)',
              color: 'var(--captured-text)',
              border: '1px solid var(--captured-border)'
            }}
            title="Organic payment success; not caused by RecoverAI"
          >
            <span style={{ width: '5px', height: '5px', borderRadius: '50%', backgroundColor: 'var(--captured-text)' }} />
            CAPTURED
          </span>
        );
      case 'RECOVERY_PENDING':
        return (
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '4px',
              padding: '2px 8px',
              borderRadius: '9999px',
              fontSize: '0.72rem',
              fontWeight: 600,
              backgroundColor: 'var(--pending-bg)',
              color: 'var(--pending-text)',
              border: '1px solid var(--pending-border)'
            }}
          >
            <span style={{ width: '5px', height: '5px', borderRadius: '50%', backgroundColor: 'var(--pending-text)' }} />
            PENDING
          </span>
        );
      case 'STOPPED':
        return (
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '4px',
              padding: '2px 8px',
              borderRadius: '9999px',
              fontSize: '0.72rem',
              fontWeight: 600,
              backgroundColor: 'var(--stopped-bg)',
              color: 'var(--stopped-text)',
              border: '1px solid var(--stopped-border)'
            }}
          >
            <span style={{ width: '5px', height: '5px', borderRadius: '50%', backgroundColor: 'var(--stopped-text)' }} />
            STOPPED
          </span>
        );
      case 'FAILED':
      default:
        return (
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '4px',
              padding: '2px 8px',
              borderRadius: '9999px',
              fontSize: '0.72rem',
              fontWeight: 600,
              backgroundColor: 'var(--failed-bg)',
              color: 'var(--failed-text)',
              border: '1px solid var(--failed-border)'
            }}
          >
            <span style={{ width: '5px', height: '5px', borderRadius: '50%', backgroundColor: 'var(--failed-text)' }} />
            FAILED
          </span>
        );
    }
  };

  const renderRecommendationBadge = (rec) => {
    if (!rec || !rec.action) return <span style={{ color: 'var(--text-light)', fontSize: '0.75rem' }}>--</span>;
    return (
      <span
        style={{
          display: 'inline-block',
          padding: '1px 6px',
          borderRadius: '4px',
          fontSize: '0.7rem',
          fontWeight: 600,
          backgroundColor: rec.action === 'PAYMENT_LINK' ? 'var(--accent-subtle)' : 'var(--bg-subtle)',
          color: rec.action === 'PAYMENT_LINK' ? 'var(--accent-primary)' : 'var(--text-secondary)',
          border: '1px solid var(--border-subtle)'
        }}
      >
        {rec.action}
      </span>
    );
  };

  const renderSafetyBadge = (safety) => {
    if (!safety || !safety.decision) return <span style={{ color: 'var(--text-light)', fontSize: '0.75rem' }}>--</span>;
    const isOverride = safety.decision === 'OVERRIDE';
    return (
      <span
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '4px',
          padding: '1px 6px',
          borderRadius: '4px',
          fontSize: '0.7rem',
          fontWeight: 600,
          backgroundColor: isOverride ? 'var(--safety-bg)' : 'var(--recovered-bg)',
          color: isOverride ? 'var(--safety-text)' : 'var(--recovered-text)',
          border: `1px solid ${isOverride ? 'var(--safety-border)' : 'var(--recovered-border)'}`
        }}
        title={safety.reason || safety.rule_id}
      >
        {safety.decision}
      </span>
    );
  };

  return (
    <div
      style={{
        backgroundColor: 'var(--bg-card)',
        border: '1px solid var(--border-card)',
        borderRadius: 'var(--radius-lg)',
        boxShadow: 'var(--shadow-sm)',
        overflow: 'hidden'
      }}
    >
      {/* Demo / Simulated Data Disclaimer Banner */}
      {isDemoData && (
        <div
          style={{
            padding: '0.6rem 1.25rem',
            backgroundColor: '#fffbeb',
            borderBottom: '1px solid #fde68a',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            fontSize: '0.75rem',
            color: '#92400e',
            flexWrap: 'wrap',
            gap: '0.5rem'
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <InfoIcon size={14} color="#b45309" />
            <span>
              <strong>Simulated Demo Scenario Data:</strong> Demonstrating RecoverAI Phase 7 end-to-end recovery scenarios. Live transaction REST endpoint (<code>GET /api/v1/transactions</code>) is awaiting backend interface wiring.
            </span>
          </div>
          <span
            style={{
              fontWeight: 600,
              fontSize: '0.68rem',
              textTransform: 'uppercase',
              backgroundColor: '#fef3c7',
              padding: '1px 6px',
              borderRadius: '4px',
              border: '1px solid #fcd34d'
            }}
          >
            Demo Mode
          </span>
        </div>
      )}

      {/* Table Header Controls */}
      <div
        style={{
          padding: '1rem 1.25rem',
          borderBottom: '1px solid var(--border-subtle)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '0.75rem'
        }}
      >
        <div>
          <h2 style={{ fontSize: '0.9375rem', fontWeight: 600, color: 'var(--text-primary)' }}>
            Recovery Transactions
          </h2>
          <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
            Real-time audit log of failed payments, AI decisions, safety checks, and outcomes
          </p>
        </div>

        {/* Search & Filter Bar */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
          {/* Search box */}
          <div
            style={{
              position: 'relative',
              display: 'flex',
              alignItems: 'center'
            }}
          >
            <span style={{ position: 'absolute', left: '10px', color: 'var(--text-light)', pointerEvents: 'none' }}>
              <SearchIcon size={14} />
            </span>
            <input
              type="text"
              placeholder="Search payment, customer, error..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              style={{
                padding: '0.4rem 0.6rem 0.4rem 2rem',
                fontSize: '0.8125rem',
                border: '1px solid var(--border-subtle)',
                borderRadius: 'var(--radius-md)',
                backgroundColor: 'var(--bg-app)',
                color: 'var(--text-primary)',
                outline: 'none',
                width: '230px',
                transition: 'border-color 0.15s ease'
              }}
              onFocus={(e) => (e.target.style.borderColor = 'var(--accent-primary)')}
              onBlur={(e) => (e.target.style.borderColor = 'var(--border-subtle)')}
            />
          </div>

          {/* Status Filter */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
            {['ALL', 'RECOVERED', 'CAPTURED', 'RECOVERY_PENDING', 'STOPPED'].map((st) => (
              <button
                key={st}
                onClick={() => setStatusFilter(st)}
                style={{
                  fontSize: '0.72rem',
                  fontWeight: 600,
                  padding: '0.35rem 0.6rem',
                  borderRadius: 'var(--radius-sm)',
                  border: '1px solid',
                  borderColor: statusFilter === st ? 'var(--accent-primary)' : 'var(--border-subtle)',
                  backgroundColor: statusFilter === st ? 'var(--accent-subtle)' : 'var(--bg-card)',
                  color: statusFilter === st ? 'var(--accent-primary)' : 'var(--text-muted)',
                  cursor: 'pointer',
                  transition: 'all 0.15s ease'
                }}
              >
                {st === 'ALL' ? 'All' : st.replace('_', ' ')}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Table Container */}
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
          <thead>
            <tr style={{ backgroundColor: 'var(--bg-subtle)', borderBottom: '1px solid var(--border-subtle)' }}>
              <th style={{ padding: '0.65rem 1rem', fontSize: '0.72rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                Payment
              </th>
              <th style={{ padding: '0.65rem 1rem', fontSize: '0.72rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                Amount
              </th>
              <th style={{ padding: '0.65rem 1rem', fontSize: '0.72rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                Failure Reason
              </th>
              <th style={{ padding: '0.65rem 1rem', fontSize: '0.72rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                AI Rec.
              </th>
              <th style={{ padding: '0.65rem 1rem', fontSize: '0.72rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                Confidence
              </th>
              <th style={{ padding: '0.65rem 1rem', fontSize: '0.72rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                Safety
              </th>
              <th style={{ padding: '0.65rem 1rem', fontSize: '0.72rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                Final Action
              </th>
              <th style={{ padding: '0.65rem 1rem', fontSize: '0.72rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                Outcome
              </th>
              <th style={{ padding: '0.65rem 1rem', fontSize: '0.72rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                Time
              </th>
              <th style={{ padding: '0.65rem 0.5rem', width: '40px' }} />
            </tr>
          </thead>
          <tbody>
            {loading ? (
              [1, 2, 3, 4, 5].map((idx) => (
                <tr key={idx} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                  <td colSpan={10} style={{ padding: '1rem' }}>
                    <div className="skeleton" style={{ height: '24px', width: '100%' }} />
                  </td>
                </tr>
              ))
            ) : filtered.length === 0 ? (
              <tr>
                <td colSpan={10} style={{ padding: '3rem 1rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                  <div style={{ display: 'inline-flex', padding: '0.75rem', borderRadius: '50%', backgroundColor: 'var(--bg-subtle)', marginBottom: '0.5rem' }}>
                    <SearchIcon size={20} color="var(--text-light)" />
                  </div>
                  <div style={{ fontSize: '0.875rem', fontWeight: 500, color: 'var(--text-secondary)' }}>
                    No transactions match your search or filter criteria
                  </div>
                  <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
                    Try clearing the filter or searching for another payment ID.
                  </p>
                </td>
              </tr>
            ) : (
              filtered.map((tx) => (
                <tr
                  key={tx.id}
                  onClick={() => onSelectTransaction(tx)}
                  style={{
                    borderBottom: '1px solid var(--border-subtle)',
                    cursor: 'pointer',
                    transition: 'background-color 0.12s ease'
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = 'var(--bg-hover)')}
                  onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
                >
                  {/* Payment */}
                  <td style={{ padding: '0.85rem 1rem' }}>
                    <div style={{ fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                      {tx.payment_id}
                    </div>
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                      {tx.customer_email || tx.customer_id || 'Guest'}
                    </div>
                  </td>

                  {/* Amount */}
                  <td style={{ padding: '0.85rem 1rem' }}>
                    <span className="tabular-nums" style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                      {formatCurrency(tx.amount)}
                    </span>
                  </td>

                  {/* Failure Reason */}
                  <td style={{ padding: '0.85rem 1rem' }}>
                    <span
                      style={{
                        display: 'inline-block',
                        maxWidth: '140px',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                        fontSize: '0.72rem',
                        fontWeight: 500,
                        color: 'var(--failed-text)',
                        backgroundColor: 'var(--failed-bg)',
                        padding: '1px 6px',
                        borderRadius: '4px',
                        border: '1px solid var(--failed-border)'
                      }}
                      title={tx.error_description || tx.error_code}
                    >
                      {tx.error_code || 'FAILURE'}
                    </span>
                  </td>

                  {/* AI Recommendation */}
                  <td style={{ padding: '0.85rem 1rem' }}>
                    {renderRecommendationBadge(tx.ai_recommendation)}
                  </td>

                  {/* Confidence */}
                  <td style={{ padding: '0.85rem 1rem' }}>
                    {tx.ai_recommendation?.confidence ? (
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <div
                          style={{
                            width: '36px',
                            height: '5px',
                            backgroundColor: 'var(--bg-subtle)',
                            borderRadius: '3px',
                            overflow: 'hidden'
                          }}
                        >
                          <div
                            style={{
                              height: '100%',
                              width: `${tx.ai_recommendation.confidence * 100}%`,
                              backgroundColor:
                                tx.ai_recommendation.confidence >= 0.8
                                  ? 'var(--recovered-text)'
                                  : tx.ai_recommendation.confidence >= 0.5
                                  ? 'var(--pending-text)'
                                  : 'var(--failed-text)'
                            }}
                          />
                        </div>
                        <span className="tabular-nums" style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-secondary)' }}>
                          {(tx.ai_recommendation.confidence * 100).toFixed(0)}%
                        </span>
                      </div>
                    ) : (
                      <span style={{ color: 'var(--text-light)', fontSize: '0.75rem' }}>--</span>
                    )}
                  </td>

                  {/* Safety */}
                  <td style={{ padding: '0.85rem 1rem' }}>
                    {renderSafetyBadge(tx.safety_guard)}
                  </td>

                  {/* Final Action */}
                  <td style={{ padding: '0.85rem 1rem' }}>
                    <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                      {tx.safety_guard?.final_action || tx.action_execution?.action || '--'}
                    </span>
                  </td>

                  {/* Outcome */}
                  <td style={{ padding: '0.85rem 1rem' }}>
                    {renderStatusBadge(tx.status)}
                  </td>

                  {/* Time */}
                  <td style={{ padding: '0.85rem 1rem' }}>
                    <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                      {formatTime(tx.created_at)}
                    </span>
                  </td>

                  {/* Chevron action */}
                  <td style={{ padding: '0.85rem 0.5rem', textAlign: 'right', color: 'var(--text-light)' }}>
                    <ChevronRightIcon size={16} />
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
