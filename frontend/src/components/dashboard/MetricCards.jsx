import React from 'react';
import {
  RupeeIcon,
  CheckCircleIcon,
  ActivityIcon,
  AlertTriangleIcon,
  LinkIcon,
  ClockIcon,
  BanIcon,
  ShieldIcon
} from '../common/Icons';

export function MetricCards({ metrics, loading }) {
  // Format paise into INR currency display
  const formatCurrency = (paise) => {
    if (typeof paise !== 'number' || isNaN(paise)) return '₹0.00';
    const rupees = paise / 100;
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 2,
    }).format(rupees);
  };

  // Format recovery rate percentage
  const formatRate = (rate) => {
    if (typeof rate !== 'number' || isNaN(rate)) return '0.0%';
    return `${(rate * 100).toFixed(1)}%`;
  };

  // Format integers
  const formatCount = (count) => {
    if (typeof count !== 'number' || isNaN(count)) return '0';
    return new Intl.NumberFormat('en-IN').format(count);
  };

  const revenueAtRisk = metrics?.revenue_at_risk ?? 0;
  const recoveredRevenue = metrics?.recovered_revenue ?? 0;
  const recoveryRate = metrics?.recovery_rate ?? 0.0;
  const totalFailed = metrics?.total_failed_transactions ?? 0;

  const totalRecovered = metrics?.total_recovered_transactions ?? 0;
  const paymentLinksCreated = metrics?.payment_links_created ?? 0;
  const stoppedTransactions = metrics?.stopped_transactions ?? 0;
  const eligibleFailed = metrics?.eligible_failed_transactions ?? 0;
  // Compute pending: payment links created minus recovered or count of pending
  const pendingCount = Math.max(0, paymentLinksCreated - totalRecovered);

  return (
    <div style={{ marginBottom: '1.75rem' }}>
      {/* Primary Metrics Grid (4 Cards) */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
          gap: '1rem',
          marginBottom: '1rem'
        }}
      >
        {/* 1. Revenue at Risk */}
        <div
          style={{
            backgroundColor: 'var(--bg-card)',
            border: '1px solid var(--border-card)',
            borderRadius: 'var(--radius-lg)',
            padding: '1.25rem',
            boxShadow: 'var(--shadow-sm)',
            position: 'relative'
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
            <span style={{ fontSize: '0.8125rem', fontWeight: 500, color: 'var(--text-muted)' }}>
              Revenue at Risk
            </span>
            <div
              style={{
                width: '28px',
                height: '28px',
                borderRadius: '6px',
                backgroundColor: 'var(--failed-bg)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'var(--failed-text)'
              }}
            >
              <AlertTriangleIcon size={15} />
            </div>
          </div>
          {loading ? (
            <div className="skeleton" style={{ height: '32px', width: '120px', margin: '0.25rem 0' }} />
          ) : (
            <div className="tabular-nums" style={{ fontSize: '1.625rem', fontWeight: 700, color: 'var(--text-primary)', letterSpacing: '-0.02em' }}>
              {formatCurrency(revenueAtRisk)}
            </div>
          )}
          <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
            Unrecovered failed payments
          </p>
        </div>

        {/* 2. Recovered Revenue */}
        <div
          style={{
            backgroundColor: 'var(--bg-card)',
            border: '1px solid var(--border-card)',
            borderRadius: 'var(--radius-lg)',
            padding: '1.25rem',
            boxShadow: 'var(--shadow-sm)',
            position: 'relative'
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
            <span style={{ fontSize: '0.8125rem', fontWeight: 500, color: 'var(--text-muted)' }}>
              Recovered Revenue
            </span>
            <div
              style={{
                width: '28px',
                height: '28px',
                borderRadius: '6px',
                backgroundColor: 'var(--recovered-bg)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'var(--recovered-text)'
              }}
            >
              <RupeeIcon size={15} />
            </div>
          </div>
          {loading ? (
            <div className="skeleton" style={{ height: '32px', width: '120px', margin: '0.25rem 0' }} />
          ) : (
            <div className="tabular-nums" style={{ fontSize: '1.625rem', fontWeight: 700, color: 'var(--recovered-text)', letterSpacing: '-0.02em' }}>
              {formatCurrency(recoveredRevenue)}
            </div>
          )}
          <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
            Verified causally recovered via RecoverAI
          </p>
        </div>

        {/* 3. Recovery Rate */}
        <div
          style={{
            backgroundColor: 'var(--bg-card)',
            border: '1px solid var(--border-card)',
            borderRadius: 'var(--radius-lg)',
            padding: '1.25rem',
            boxShadow: 'var(--shadow-sm)',
            position: 'relative'
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
            <span style={{ fontSize: '0.8125rem', fontWeight: 500, color: 'var(--text-muted)' }}>
              Recovery Rate
            </span>
            <div
              style={{
                width: '28px',
                height: '28px',
                borderRadius: '6px',
                backgroundColor: 'var(--accent-subtle)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'var(--accent-primary)'
              }}
            >
              <ActivityIcon size={15} />
            </div>
          </div>
          {loading ? (
            <div className="skeleton" style={{ height: '32px', width: '100px', margin: '0.25rem 0' }} />
          ) : (
            <div className="tabular-nums" style={{ fontSize: '1.625rem', fontWeight: 700, color: 'var(--text-primary)', letterSpacing: '-0.02em' }}>
              {formatRate(recoveryRate)}
            </div>
          )}
          <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
            total_recovered / eligible_failed
          </p>
        </div>

        {/* 4. Failed Transactions */}
        <div
          style={{
            backgroundColor: 'var(--bg-card)',
            border: '1px solid var(--border-card)',
            borderRadius: 'var(--radius-lg)',
            padding: '1.25rem',
            boxShadow: 'var(--shadow-sm)',
            position: 'relative'
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
            <span style={{ fontSize: '0.8125rem', fontWeight: 500, color: 'var(--text-muted)' }}>
              Failed Transactions
            </span>
            <div
              style={{
                width: '28px',
                height: '28px',
                borderRadius: '6px',
                backgroundColor: 'var(--bg-subtle)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'var(--text-secondary)'
              }}
            >
              <BanIcon size={15} />
            </div>
          </div>
          {loading ? (
            <div className="skeleton" style={{ height: '32px', width: '80px', margin: '0.25rem 0' }} />
          ) : (
            <div className="tabular-nums" style={{ fontSize: '1.625rem', fontWeight: 700, color: 'var(--text-primary)', letterSpacing: '-0.02em' }}>
              {formatCount(totalFailed)}
            </div>
          )}
          <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
            Total failed payment events
          </p>
        </div>
      </div>

      {/* Secondary Metrics Bar */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
          gap: '0.75rem'
        }}
      >
        {/* Recovered Transactions */}
        <div
          style={{
            backgroundColor: 'var(--bg-card)',
            border: '1px solid var(--border-card)',
            borderRadius: 'var(--radius-md)',
            padding: '0.875rem 1rem',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between'
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            <CheckCircleIcon size={16} color="var(--recovered-text)" />
            <span style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)' }}>Recovered</span>
          </div>
          {loading ? (
            <div className="skeleton" style={{ height: '20px', width: '40px' }} />
          ) : (
            <span className="tabular-nums" style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-primary)' }}>
              {formatCount(totalRecovered)}
            </span>
          )}
        </div>

        {/* Payment Links Created */}
        <div
          style={{
            backgroundColor: 'var(--bg-card)',
            border: '1px solid var(--border-card)',
            borderRadius: 'var(--radius-md)',
            padding: '0.875rem 1rem',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between'
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            <LinkIcon size={16} color="var(--accent-primary)" />
            <span style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)' }}>Payment Links</span>
          </div>
          {loading ? (
            <div className="skeleton" style={{ height: '20px', width: '40px' }} />
          ) : (
            <span className="tabular-nums" style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-primary)' }}>
              {formatCount(paymentLinksCreated)}
            </span>
          )}
        </div>

        {/* Recovery Pending */}
        <div
          style={{
            backgroundColor: 'var(--bg-card)',
            border: '1px solid var(--border-card)',
            borderRadius: 'var(--radius-md)',
            padding: '0.875rem 1rem',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between'
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            <ClockIcon size={16} color="var(--pending-text)" />
            <span style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)' }}>Recovery Pending</span>
          </div>
          {loading ? (
            <div className="skeleton" style={{ height: '20px', width: '40px' }} />
          ) : (
            <span className="tabular-nums" style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-primary)' }}>
              {formatCount(pendingCount)}
            </span>
          )}
        </div>

        {/* Stopped Transactions */}
        <div
          style={{
            backgroundColor: 'var(--bg-card)',
            border: '1px solid var(--border-card)',
            borderRadius: 'var(--radius-md)',
            padding: '0.875rem 1rem',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between'
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            <ShieldIcon size={16} color="var(--stopped-text)" />
            <span style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)' }}>Stopped by Safety</span>
          </div>
          {loading ? (
            <div className="skeleton" style={{ height: '20px', width: '40px' }} />
          ) : (
            <span className="tabular-nums" style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-primary)' }}>
              {formatCount(stoppedTransactions)}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
