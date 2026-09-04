import React from 'react';
import { RupeeIcon, ActivityIcon, CheckCircleIcon, BanIcon, InfoIcon } from '../common/Icons';

export function AnalyticsView({ metrics }) {
  const formatCurrency = (paise) => {
    if (typeof paise !== 'number' || isNaN(paise)) return '₹0.00';
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 2,
    }).format(paise / 100);
  };

  const recoveryRate = metrics?.recovery_rate ?? 0.0;
  const recoveredRevenue = metrics?.recovered_revenue ?? 0;
  const revenueAtRisk = metrics?.revenue_at_risk ?? 0;
  const totalFailed = metrics?.total_failed_transactions ?? 0;
  const eligibleFailed = metrics?.eligible_failed_transactions ?? 0;
  const totalRecovered = metrics?.total_recovered_transactions ?? 0;

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
        <h2 style={{ fontSize: '1.125rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.25rem' }}>
          Recovery Performance Analytics
        </h2>
        <p style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', marginBottom: '1.25rem' }}>
          Deterministic, database-derived KPIs aggregated across Razorpay transaction states.
        </p>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem' }}>
          <div style={{ padding: '1rem', backgroundColor: 'var(--bg-app)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-subtle)' }}>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase' }}>
              Formula Definition
            </span>
            <div style={{ fontSize: '0.8125rem', color: 'var(--text-primary)', marginTop: '0.5rem', fontFamily: 'monospace' }}>
              recovery_rate = total_recovered / eligible_failed
            </div>
            <p style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', marginTop: '0.25rem' }}>
              Protected against zero-division (defaults to 0.0% when eligible_failed is 0).
            </p>
          </div>

          <div style={{ padding: '1rem', backgroundColor: 'var(--bg-app)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-subtle)' }}>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase' }}>
              Eligible Transactions
            </span>
            <div className="tabular-nums" style={{ fontSize: '1.375rem', fontWeight: 700, color: 'var(--text-primary)', marginTop: '0.25rem' }}>
              {eligibleFailed}
            </div>
            <p style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', marginTop: '0.25rem' }}>
              Out of {totalFailed} total failures evaluated
            </p>
          </div>

          <div style={{ padding: '1rem', backgroundColor: 'var(--bg-app)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-subtle)' }}>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase' }}>
              Conversion Yield
            </span>
            <div className="tabular-nums" style={{ fontSize: '1.375rem', fontWeight: 700, color: 'var(--recovered-text)', marginTop: '0.25rem' }}>
              {(recoveryRate * 100).toFixed(1)}%
            </div>
            <p style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', marginTop: '0.25rem' }}>
              {totalRecovered} successful recoveries achieved
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
