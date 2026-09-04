import React, { useState, useEffect, useCallback } from 'react';
import { Sidebar } from './components/layout/Sidebar';
import { TopBar } from './components/layout/TopBar';
import { MetricCards } from './components/dashboard/MetricCards';
import { WorkflowVisual } from './components/dashboard/WorkflowVisual';
import { TransactionTable } from './components/transactions/TransactionTable';
import { TransactionDetailModal } from './components/transactions/TransactionDetailModal';
import { EmptyState } from './components/common/EmptyState';
import { RecoveryEngineView } from './components/views/RecoveryEngineView';
import { AnalyticsView } from './components/views/AnalyticsView';
import { AuditView } from './components/views/AuditView';
import { AlertTriangleIcon, RefreshIcon, ZapIcon } from './components/common/Icons';
import { fetchRecoveryMetrics, fetchHealthStatus, fetchTransactions } from './services/api';

export default function App() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [metrics, setMetrics] = useState(null);
  const [healthData, setHealthData] = useState(null);
  const [transactions, setTransactions] = useState([]);
  const [isDemoData, setIsDemoData] = useState(false);
  const [selectedTransaction, setSelectedTransaction] = useState(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [backendConnected, setBackendConnected] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  // Unified load function
  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);

    // 1. Health check
    let isConnected = false;
    try {
      const health = await fetchHealthStatus();
      setHealthData(health);
      isConnected = health?.status === 'healthy';
      setBackendConnected(isConnected);
    } catch (err) {
      setBackendConnected(false);
    }

    // 2. Metrics query
    try {
      const metricsData = await fetchRecoveryMetrics();
      setMetrics(metricsData);
    } catch (err) {
      console.warn('Metrics endpoint not yet reachable:', err.message);
      // Fallback zeroed metrics object rather than null/undefined
      setMetrics({
        revenue_at_risk: 0,
        recovered_revenue: 0,
        recovery_rate: 0.0,
        total_failed_transactions: 0,
        total_recovered_transactions: 0,
        payment_links_created: 0,
        stopped_transactions: 0,
        eligible_failed_transactions: 0
      });
      if (!isConnected) {
        setError('FastAPI backend connection offline. Start backend on port 8000.');
      }
    }

    // 3. Transactions query
    try {
      const txResult = await fetchTransactions();
      setTransactions(txResult.data || []);
      setIsDemoData(txResult.isDemoData);
    } catch (err) {
      console.warn('Transaction fetch error:', err.message);
      setTransactions([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Check if system has any activity
  const hasActivity =
    (metrics && (metrics.total_failed_transactions > 0 || metrics.revenue_at_risk > 0 || metrics.recovered_revenue > 0)) ||
    (transactions && transactions.length > 0);

  return (
    <div className="app-container">
      {/* Navigation Sidebar */}
      <Sidebar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        mobileOpen={mobileOpen}
        setMobileOpen={setMobileOpen}
        healthData={healthData}
      />

      {/* Main Content Area */}
      <div className="main-content">
        {/* Top bar with Razorpay Test Mode indicator & connectivity status */}
        <TopBar
          activeTab={activeTab}
          onRefresh={loadData}
          loading={loading}
          backendConnected={backendConnected}
          setMobileOpen={setMobileOpen}
        />

        <main className="content-body">
          {/* Error notice banner */}
          {error && (
            <div
              style={{
                backgroundColor: 'var(--failed-bg)',
                border: '1px solid var(--failed-border)',
                borderRadius: 'var(--radius-md)',
                padding: '0.875rem 1.25rem',
                marginBottom: '1.5rem',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                flexWrap: 'wrap',
                gap: '0.75rem'
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                <AlertTriangleIcon size={18} color="var(--failed-text)" />
                <span style={{ fontSize: '0.8125rem', color: 'var(--failed-text)', fontWeight: 500 }}>
                  {error}
                </span>
              </div>
              <button
                onClick={loadData}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.35rem',
                  fontSize: '0.75rem',
                  fontWeight: 600,
                  backgroundColor: 'white',
                  border: '1px solid var(--failed-border)',
                  color: 'var(--failed-text)',
                  padding: '0.3rem 0.65rem',
                  borderRadius: 'var(--radius-sm)',
                  cursor: 'pointer'
                }}
              >
                <RefreshIcon size={12} />
                <span>Retry Connection</span>
              </button>
            </div>
          )}

          {/* VIEW: DASHBOARD */}
          {activeTab === 'dashboard' && (
            <>
              {/* Dashboard Main Header */}
              <div style={{ marginBottom: '1.5rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.75rem' }}>
                  <div>
                    <h1 style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--text-primary)', letterSpacing: '-0.02em' }}>
                      RecoverAI
                    </h1>
                    <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginTop: '2px' }}>
                      Autonomous Payment Recovery &mdash; Monitor failed payments, AI decisions, safety checks, and recovered revenue.
                    </p>
                  </div>

                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.5rem',
                      padding: '0.35rem 0.75rem',
                      backgroundColor: 'var(--bg-card)',
                      border: '1px solid var(--border-subtle)',
                      borderRadius: 'var(--radius-md)',
                      fontSize: '0.75rem'
                    }}
                  >
                    <span style={{ color: 'var(--text-muted)' }}>Target:</span>
                    <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>Razorpay Test Gateway</span>
                  </div>
                </div>
              </div>

              {/* Four Primary Metric Cards + Secondary Bar */}
              <MetricCards metrics={metrics} loading={loading} />

              {/* End-to-End Recovery Flow Visual */}
              <WorkflowVisual />

              {/* Recovery Transactions Table */}
              {!hasActivity && !loading ? (
                <EmptyState onRefresh={loadData} loading={loading} />
              ) : (
                <TransactionTable
                  transactions={transactions}
                  isDemoData={isDemoData}
                  onSelectTransaction={setSelectedTransaction}
                  loading={loading}
                />
              )}
            </>
          )}

          {/* VIEW: TRANSACTIONS */}
          {activeTab === 'transactions' && (
            <div>
              <div style={{ marginBottom: '1.25rem' }}>
                <h1 style={{ fontSize: '1.375rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                  Transactions & Recovery Activity
                </h1>
                <p style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
                  Detailed log of payment failure ingestion, AI evaluation, and causal settlement
                </p>
              </div>

              <TransactionTable
                transactions={transactions}
                isDemoData={isDemoData}
                onSelectTransaction={setSelectedTransaction}
                loading={loading}
              />
            </div>
          )}

          {/* VIEW: RECOVERY ENGINE */}
          {activeTab === 'recovery' && <RecoveryEngineView />}

          {/* VIEW: ANALYTICS */}
          {activeTab === 'analytics' && <AnalyticsView metrics={metrics} />}

          {/* VIEW: AUDIT LOGS */}
          {activeTab === 'audit' && <AuditView />}
        </main>
      </div>

      {/* Slide-over Transaction Detail Modal */}
      {selectedTransaction && (
        <TransactionDetailModal
          transaction={selectedTransaction}
          onClose={() => setSelectedTransaction(null)}
        />
      )}
    </div>
  );
}
