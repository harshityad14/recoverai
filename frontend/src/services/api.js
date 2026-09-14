/**
 * RecoverAI API Service Module
 * Handles API communication with FastAPI backend:
 * - GET /api/v1/metrics/recovery (with /metrics/recovery fallback)
 * - GET /health (backend operational diagnostics)
 * - GET /api/v1/transactions (attempt live query, graceful demo scenario fallback)
 */

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/+$/, '');

function getApiUrl(path) {
  if (!API_BASE_URL) {
    return path;
  }
  const cleanPath = path.startsWith('/') ? path : `/${path}`;
  return `${API_BASE_URL}${cleanPath}`;
}

export async function fetchRecoveryMetrics() {
  // Try /api/v1/metrics/recovery first, fallback to /metrics/recovery
  try {
    const res = await fetch(getApiUrl('/api/v1/metrics/recovery'));
    if (res.ok) {
      return await res.json();
    }
  } catch (err) {
    // try direct /metrics/recovery
  }

  try {
    const res2 = await fetch(getApiUrl('/metrics/recovery'));
    if (res2.ok) {
      return await res2.json();
    }
    throw new Error(`Failed to fetch metrics: HTTP ${res2.status}`);
  } catch (err) {
    throw new Error(`Backend metrics unavailable: ${err.message}`);
  }
}

export async function fetchHealthStatus() {
  try {
    const res = await fetch(getApiUrl('/health'));
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }
    return await res.json();
  } catch (err) {
    throw new Error(`Backend health check failed: ${err.message}`);
  }
}

export async function fetchTransactions() {
  // Attempt live transactions endpoint
  try {
    const res = await fetch(getApiUrl('/api/v1/transactions'));
    if (res.ok) {
      const data = await res.json();
      return {
        data: data.items || data,
        isDemoData: false,
        source: 'live'
      };
    }
  } catch (err) {
    // live transactions endpoint is not implemented in backend
  }

  // Graceful fallback to structured demo scenarios matching Phase 7 recovery pipeline
  return {
    data: getDemoScenarios(),
    isDemoData: true,
    source: 'simulated_scenarios'
  };
}

/**
 * Structured Scenario Dataset for Demo & Testing
 * Exactly reproduces the 4 core Phase 7 test scenarios.
 * NOTE: Clearly labelled as simulated data in UI.
 */
function getDemoScenarios() {
  return [
    {
      id: 1,
      transaction_id: 'txn_rec_91a82e1c',
      payment_id: 'pay_RPtest91a82e1c',
      order_id: 'order_ORD8839201',
      customer_id: 'cust_priya_sharma_98',
      customer_email: 'priya.s@example.com',
      amount: 450000, // paise (₹4,500.00)
      currency: 'INR',
      status: 'RECOVERED',
      error_code: 'BAD_REQUEST_ERROR',
      error_description: 'Payment failed due to 3D Secure authentication timeout at issuer bank',
      payment_link_id: 'plink_rec_77492a',
      payment_link_url: 'https://rzp.io/i/rec_77492a',
      created_at: new Date(Date.now() - 14 * 60 * 1000).toISOString(),
      updated_at: new Date(Date.now() - 4 * 60 * 1000).toISOString(),
      // AI & Safety Pipeline Audit Trail
      ai_recommendation: {
        action: 'PAYMENT_LINK',
        confidence: 0.94,
        rationale: 'Isolated 3DS OTP timeout on authentic customer card. Customer history shows 100% past recovery upon link delivery. High recovery probability.',
        model: 'gemini-1.5-pro'
      },
      safety_guard: {
        decision: 'APPROVE',
        rule_id: 'APPROVED',
        final_action: 'PAYMENT_LINK',
        reason: 'Safe recovery action. Amount within ₹100,000 threshold and retry attempt 1/3.'
      },
      action_execution: {
        action: 'PAYMENT_LINK',
        result: 'SUCCESS',
        reference_id: 'plink_rec_77492a',
        executed_at: new Date(Date.now() - 12 * 60 * 1000).toISOString()
      },
      outcome: {
        status: 'RECOVERED',
        causally_verified: true,
        recovered_amount: 450000,
        recovered_at: new Date(Date.now() - 4 * 60 * 1000).toISOString(),
        attribution_note: 'Verified causal recovery. Webhook payment.captured matched payment_link_id plink_rec_77492a.'
      }
    },
    {
      id: 2,
      transaction_id: 'txn_org_44c11b09',
      payment_id: 'pay_RPtest44c11b09',
      order_id: 'order_ORD5519822',
      customer_id: 'cust_rohit_verma_12',
      customer_email: 'rohit.v@example.com',
      amount: 220000, // paise (₹2,200.00)
      currency: 'INR',
      status: 'CAPTURED',
      error_code: 'CARD_ERROR',
      error_description: 'Card declined: Insufficient funds in checking account',
      payment_link_id: 'plink_org_99210b',
      payment_link_url: 'https://rzp.io/i/org_99210b',
      created_at: new Date(Date.now() - 45 * 60 * 1000).toISOString(),
      updated_at: new Date(Date.now() - 10 * 60 * 1000).toISOString(),
      ai_recommendation: {
        action: 'PAYMENT_LINK',
        confidence: 0.81,
        rationale: 'Temporary balance deficiency. Alternate payment link allows UPI or netbanking fallback.',
        model: 'gemini-1.5-pro'
      },
      safety_guard: {
        decision: 'APPROVE',
        rule_id: 'APPROVED',
        final_action: 'PAYMENT_LINK',
        reason: 'Standard payment link dispatch approved.'
      },
      action_execution: {
        action: 'PAYMENT_LINK',
        result: 'SUCCESS',
        reference_id: 'plink_org_99210b',
        executed_at: new Date(Date.now() - 43 * 60 * 1000).toISOString()
      },
      outcome: {
        status: 'CAPTURED',
        causally_verified: false,
        recovered_amount: 0,
        recovered_at: null,
        attribution_note: 'Organic capture: Customer returned to main merchant website directly with a different card. RecoverAI explicitly disclaims attribution credit.'
      }
    },
    {
      id: 3,
      transaction_id: 'txn_pnd_82d55e41',
      payment_id: 'pay_RPtest82d55e41',
      order_id: 'order_ORD7728103',
      customer_id: 'cust_ananya_das_44',
      customer_email: 'ananya.d@example.com',
      amount: 315000, // paise (₹3,150.00)
      currency: 'INR',
      status: 'RECOVERY_PENDING',
      error_code: 'BAD_REQUEST_ERROR',
      error_description: 'Customer abandoned payment flow during OTP entry',
      payment_link_id: 'plink_pnd_11029c',
      payment_link_url: 'https://rzp.io/i/pnd_11029c',
      created_at: new Date(Date.now() - 8 * 60 * 1000).toISOString(),
      updated_at: new Date(Date.now() - 7 * 60 * 1000).toISOString(),
      ai_recommendation: {
        action: 'PAYMENT_LINK',
        confidence: 0.92,
        rationale: 'Immediate cart abandonment. SMS recovery link generated with 15-minute expiry.',
        model: 'gemini-1.5-pro'
      },
      safety_guard: {
        decision: 'APPROVE',
        rule_id: 'APPROVED',
        final_action: 'PAYMENT_LINK',
        reason: 'Payment link dispatch approved within safety limits.'
      },
      action_execution: {
        action: 'PAYMENT_LINK',
        result: 'SUCCESS',
        reference_id: 'plink_pnd_11029c',
        executed_at: new Date(Date.now() - 7 * 60 * 1000).toISOString()
      },
      outcome: {
        status: 'RECOVERY_PENDING',
        causally_verified: false,
        recovered_amount: 0,
        recovered_at: null,
        attribution_note: 'Payment link active in Razorpay Test Mode. Awaiting customer authorization.'
      }
    },
    {
      id: 4,
      transaction_id: 'txn_ovr_33f99a88',
      payment_id: 'pay_RPtest33f99a88',
      order_id: 'order_ORD9928104',
      customer_id: 'cust_vikram_enterprise',
      customer_email: 'finance@vikram-ent.in',
      amount: 15000000, // paise (₹150,000.00)
      currency: 'INR',
      status: 'STOPPED',
      error_code: 'GATEWAY_ERROR',
      error_description: 'High-value transaction flagged for mandatory manual review',
      payment_link_id: null,
      payment_link_url: null,
      created_at: new Date(Date.now() - 65 * 60 * 1000).toISOString(),
      updated_at: new Date(Date.now() - 64 * 60 * 1000).toISOString(),
      ai_recommendation: {
        action: 'PAYMENT_LINK',
        confidence: 0.86,
        rationale: 'Enterprise tier client requested automated retry link for high-value invoice.',
        model: 'gemini-1.5-pro'
      },
      safety_guard: {
        decision: 'OVERRIDE',
        rule_id: 'AMOUNT_EXCEEDS_LIMIT',
        final_action: 'STOP',
        reason: 'Transaction amount (₹150,000.00) exceeds maximum automated recovery limit of ₹100,000.00. Safety Guard stopped automated execution.'
      },
      action_execution: {
        action: 'STOP',
        result: 'SKIPPED',
        reference_id: null,
        executed_at: new Date(Date.now() - 64 * 60 * 1000).toISOString()
      },
      outcome: {
        status: 'STOPPED',
        causally_verified: false,
        recovered_amount: 0,
        recovered_at: null,
        attribution_note: 'Recovery halted by deterministic Safety Guard. Escalated to manual account executive.'
      }
    },
    {
      id: 5,
      transaction_id: 'txn_stp_12a77b55',
      payment_id: 'pay_RPtest12a77b55',
      order_id: 'order_ORD1100223',
      customer_id: 'cust_unknown_card_66',
      customer_email: 'user66@example.com',
      amount: 850000, // paise (₹8,500.00)
      currency: 'INR',
      status: 'STOPPED',
      error_code: 'GATEWAY_ERROR',
      error_description: 'Card issuer network down across all payment gateways',
      payment_link_id: null,
      payment_link_url: null,
      created_at: new Date(Date.now() - 110 * 60 * 1000).toISOString(),
      updated_at: new Date(Date.now() - 109 * 60 * 1000).toISOString(),
      ai_recommendation: {
        action: 'STOP',
        confidence: 0.42,
        rationale: 'Widespread issuer downtime reported. Retrying immediately has low probability of success.',
        model: 'gemini-1.5-pro'
      },
      safety_guard: {
        decision: 'APPROVE',
        rule_id: 'APPROVED',
        final_action: 'STOP',
        reason: 'AI recommended STOP due to low confidence and network outage. Approved.'
      },
      action_execution: {
        action: 'STOP',
        result: 'SKIPPED',
        reference_id: null,
        executed_at: new Date(Date.now() - 109 * 60 * 1000).toISOString()
      },
      outcome: {
        status: 'STOPPED',
        causally_verified: false,
        recovered_amount: 0,
        recovered_at: null,
        attribution_note: 'No recovery action triggered. Prevents customer annoyance during bank downtime.'
      }
    }
  ];
}
