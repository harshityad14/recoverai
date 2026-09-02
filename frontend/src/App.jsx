import React, { useState, useEffect } from 'react';

export default function App() {
  const [healthData, setHealthData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchHealth = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch('/health');
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      const data = await response.json();
      setHealthData(data);
    } catch (err) {
      setError(err.message || 'Failed to connect to RecoverAI backend');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchHealth();
  }, []);

  return (
    <div style={{ maxWidth: '1000px', margin: '0 auto', padding: '2rem 1.5rem' }}>
      {/* Header */}
      <header style={{ borderBottom: '1px solid #1e293b', paddingBottom: '1.5rem', marginBottom: '2rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1rem' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              <span style={{ fontSize: '2rem' }}>🛡️</span>
              <h1 style={{ fontSize: '2rem', fontWeight: '700', color: '#38bdf8' }}>RecoverAI</h1>
              <span style={{
                fontSize: '0.75rem',
                backgroundColor: '#1e3a8a',
                color: '#93c5fd',
                padding: '0.2rem 0.6rem',
                borderRadius: '9999px',
                fontWeight: '600'
              }}>
                Phase 1 Active
              </span>
            </div>
            <p style={{ color: '#94a3b8', marginTop: '0.5rem' }}>
              AI-Powered Payment Recovery Agent &bull; Razorpay AI Buildathon
            </p>
          </div>
          <button
            onClick={fetchHealth}
            disabled={loading}
            style={{
              backgroundColor: '#0284c7',
              color: 'white',
              border: 'none',
              padding: '0.6rem 1.2rem',
              borderRadius: '0.375rem',
              fontWeight: '500',
              cursor: loading ? 'not-allowed' : 'pointer',
              opacity: loading ? 0.7 : 1,
              transition: 'background 0.2s',
            }}
          >
            {loading ? 'Checking...' : 'Refresh Status'}
          </button>
        </div>
      </header>

      {/* System Status Cards */}
      <section style={{ marginBottom: '2.5rem' }}>
        <h2 style={{ fontSize: '1.25rem', marginBottom: '1rem', color: '#f8fafc' }}>System Status & Diagnostics</h2>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1rem' }}>
          
          {/* Backend Card */}
          <div style={{
            backgroundColor: '#131c2e',
            border: '1px solid #1e293b',
            borderRadius: '0.5rem',
            padding: '1.25rem'
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
              <span style={{ fontWeight: '600', color: '#cbd5e1' }}>FastAPI Backend</span>
              <span style={{
                fontSize: '0.75rem',
                padding: '0.2rem 0.5rem',
                borderRadius: '0.25rem',
                backgroundColor: healthData?.status === 'healthy' ? '#065f46' : '#7f1d1d',
                color: healthData?.status === 'healthy' ? '#6ee7b7' : '#fca5a5'
              }}>
                {loading ? 'Checking...' : (healthData?.status || 'Offline')}
              </span>
            </div>
            <p style={{ fontSize: '0.875rem', color: '#94a3b8' }}>
              Service: <strong>{healthData?.service || 'RecoverAI'}</strong>
            </p>
            <p style={{ fontSize: '0.875rem', color: '#94a3b8', marginTop: '0.25rem' }}>
              Environment: <strong>{healthData?.environment || 'development'}</strong>
            </p>
          </div>

          {/* Database Card */}
          <div style={{
            backgroundColor: '#131c2e',
            border: '1px solid #1e293b',
            borderRadius: '0.5rem',
            padding: '1.25rem'
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
              <span style={{ fontWeight: '600', color: '#cbd5e1' }}>PostgreSQL (SQLAlchemy)</span>
              <span style={{
                fontSize: '0.75rem',
                padding: '0.2rem 0.5rem',
                borderRadius: '0.25rem',
                backgroundColor: healthData?.components?.database === 'connected' ? '#065f46' : '#854d0e',
                color: healthData?.components?.database === 'connected' ? '#6ee7b7' : '#fde047'
              }}>
                {loading ? 'Checking...' : (healthData?.components?.database || 'Configured')}
              </span>
            </div>
            <p style={{ fontSize: '0.875rem', color: '#94a3b8' }}>
              Driver: <strong>SQLAlchemy + psycopg2</strong>
            </p>
            <p style={{ fontSize: '0.875rem', color: '#94a3b8', marginTop: '0.25rem' }}>
              Status: <strong>{healthData?.components?.database || 'Configured (Phase 1 Base)'}</strong>
            </p>
          </div>

          {/* Redis Card */}
          <div style={{
            backgroundColor: '#131c2e',
            border: '1px solid #1e293b',
            borderRadius: '0.5rem',
            padding: '1.25rem'
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
              <span style={{ fontWeight: '600', color: '#cbd5e1' }}>Redis Queue & Cache</span>
              <span style={{
                fontSize: '0.75rem',
                padding: '0.2rem 0.5rem',
                borderRadius: '0.25rem',
                backgroundColor: healthData?.components?.redis === 'connected' ? '#065f46' : '#854d0e',
                color: healthData?.components?.redis === 'connected' ? '#6ee7b7' : '#fde047'
              }}>
                {loading ? 'Checking...' : (healthData?.components?.redis || 'Configured')}
              </span>
            </div>
            <p style={{ fontSize: '0.875rem', color: '#94a3b8' }}>
              Connection: <strong>Redis Client Pool</strong>
            </p>
            <p style={{ fontSize: '0.875rem', color: '#94a3b8', marginTop: '0.25rem' }}>
              Status: <strong>{healthData?.components?.redis || 'Configured (Phase 1 Base)'}</strong>
            </p>
          </div>
        </div>

        {error && (
          <div style={{
            marginTop: '1rem',
            padding: '0.75rem 1rem',
            backgroundColor: '#450a0a',
            border: '1px solid #b91c1c',
            borderRadius: '0.375rem',
            color: '#fecaca',
            fontSize: '0.875rem'
          }}>
            ⚠️ {error} &mdash; Backend might be starting or running on a different port.
          </div>
        )}
      </section>

      {/* Raw Health Payload */}
      {healthData && (
        <section style={{ marginBottom: '2.5rem' }}>
          <h2 style={{ fontSize: '1.25rem', marginBottom: '0.75rem', color: '#f8fafc' }}>
            Live Health Response (<code>GET /health</code>)
          </h2>
          <pre style={{
            backgroundColor: '#030712',
            padding: '1rem',
            borderRadius: '0.5rem',
            border: '1px solid #1f2937',
            overflowX: 'auto',
            fontSize: '0.875rem',
            color: '#34d399'
          }}>
            {JSON.stringify(healthData, null, 2)}
          </pre>
        </section>
      )}

      {/* Roadmap & Architecture Overview */}
      <section style={{
        backgroundColor: '#0f172a',
        border: '1px solid #1e293b',
        borderRadius: '0.5rem',
        padding: '1.5rem'
      }}>
        <h2 style={{ fontSize: '1.25rem', marginBottom: '0.75rem', color: '#f8fafc' }}>Buildathon Pipeline Roadmap</h2>
        <ul style={{ listStylePosition: 'inside', color: '#94a3b8', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
          <li><span style={{ color: '#38bdf8', fontWeight: '600' }}>[Phase 1] Scaffolding:</span> FastAPI, PostgreSQL config, Redis connection, React scaffolding, testing framework.</li>
          <li><span style={{ color: '#64748b' }}>[Phase 2] Webhooks:</span> Razorpay signature verification & event ingestion into Redis queue.</li>
          <li><span style={{ color: '#64748b' }}>[Phase 3] Intelligence:</span> Failure taxonomy analysis + LLM Decision Engine with deterministic safety checks.</li>
          <li><span style={{ color: '#64748b' }}>[Phase 4] Execution & Tracking:</span> Action dispatch, Razorpay API interactions, audit logging, and recovery dashboard.</li>
        </ul>
      </section>
    </div>
  );
}
