'use client';

import { useState } from 'react';

export default function DiagnosticsPage() {
  const [ticker, setTicker] = useState('AAPL');
  const [diagnostics, setDiagnostics] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const runDiagnostics = async () => {
    setLoading(true);
    setError('');
    setDiagnostics(null);

    try {
      const response = await fetch(
        `https://hedge-fund-ai-production-4d4d.up.railway.app/api/v1/diagnostics/${ticker}`
      );
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      setDiagnostics(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 to-slate-800 p-8">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-4xl font-bold text-white mb-2">🔍 API Diagnostics</h1>
          <p className="text-slate-400">
            Complete transparency: See EXACTLY what each API returns. No hiding. Real data only.
          </p>
        </div>

        {/* Input */}
        <div className="flex gap-4 mb-8">
          <input
            type="text"
            value={ticker}
            onChange={(e) => setTicker(e.target.value.toUpperCase())}
            placeholder="Enter ticker (e.g., AAPL)"
            className="px-4 py-3 rounded-lg bg-slate-700 text-white placeholder-slate-400 flex-1"
            onKeyPress={(e) => e.key === 'Enter' && runDiagnostics()}
          />
          <button
            onClick={runDiagnostics}
            disabled={loading}
            className="px-8 py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-semibold disabled:opacity-50 transition"
          >
            {loading ? 'Testing...' : 'Run Diagnostic'}
          </button>
        </div>

        {/* Error */}
        {error && (
          <div className="bg-red-900 text-red-100 p-4 rounded-lg mb-8">
            ❌ Error: {error}
          </div>
        )}

        {/* Results */}
        {diagnostics && (
          <div className="space-y-6">
            {/* Timestamp */}
            <div className="bg-slate-700 p-4 rounded-lg text-sm text-slate-300">
              📅 {diagnostics.timestamp} • Ticker: {diagnostics.ticker}
            </div>

            {/* Verdict (PROMINENT) */}
            <div className="bg-slate-700 p-6 rounded-lg border-2 border-blue-500">
              <div className="text-2xl font-bold text-white">
                {diagnostics.verdict}
              </div>
              <p className="text-slate-300 text-sm mt-2">
                This is the ROOT CAUSE. Everything else flows from this.
              </p>
            </div>

            {/* Environment Status */}
            <div className="bg-slate-700 p-6 rounded-lg">
              <h2 className="text-xl font-bold text-white mb-4">🔐 Environment Keys</h2>
              <div className="grid grid-cols-2 gap-4">
                {Object.entries(diagnostics.environment).map(([key, value]) => (
                  <div key={key} className="flex items-center gap-2">
                    <span className={value ? '✅' : '❌'}></span>
                    <span className="text-slate-300">
                      {key.replace('_key_configured', '').toUpperCase()}: <strong>{value ? 'SET' : 'MISSING'}</strong>
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {/* LLM Status */}
            <div className="bg-slate-700 p-6 rounded-lg">
              <h2 className="text-xl font-bold text-white mb-4">🤖 LLM Status</h2>
              <div className="grid grid-cols-2 gap-4">
                <div className="text-slate-300">
                  <strong>Gemini:</strong> <span className="ml-2">{diagnostics.llm_status.gemini}</span>
                </div>
                <div className="text-slate-300">
                  <strong>OpenAI:</strong> <span className="ml-2">{diagnostics.llm_status.openai}</span>
                </div>
              </div>
              <p className="text-slate-400 text-sm mt-3 italic">{diagnostics.llm_status.note}</p>
            </div>

            {/* API Results */}
            <div className="space-y-4">
              <h2 className="text-xl font-bold text-white">📡 API Responses</h2>
              {Object.entries(diagnostics.apis).map(([api_name, api_data]) => (
                <div key={api_name} className="bg-slate-700 p-4 rounded-lg">
                  <div className="flex items-center justify-between mb-3">
                    <span className="font-semibold text-white">
                      {api_name.toUpperCase().replace(/_/g, ' ')}
                    </span>
                    <span className="text-sm font-bold">
                      {api_data.status || 'N/A'}
                    </span>
                  </div>

                  {/* Show all data keys */}
                  <div className="bg-slate-800 p-3 rounded text-sm font-mono text-slate-300 overflow-auto max-h-64">
                    <pre>{JSON.stringify(api_data, null, 2)}</pre>
                  </div>
                </div>
              ))}
            </div>

            {/* Interpretation Guide */}
            <div className="bg-slate-700 p-6 rounded-lg border border-slate-600">
              <h2 className="text-lg font-bold text-white mb-3">📋 How to Read Results</h2>
              <ul className="space-y-2 text-slate-300 text-sm">
                <li><strong>✅ SUCCESS</strong> = API working, data received</li>
                <li><strong>❌ HTTP 403</strong> = API key invalid or endpoint deprecated</li>
                <li><strong>⚠️ NO SECTOR</strong> = API works but sector field empty</li>
                <li><strong>🔴 EXCEPTION</strong> = Connection/timeout error</li>
                <li><strong>Verdict 🟢</strong> = All good, problem elsewhere</li>
                <li><strong>Verdict 🟡</strong> = Some APIs down but still functional</li>
                <li><strong>Verdict 🔴</strong> = Critical issues, check environment</li>
              </ul>
            </div>
          </div>
        )}

        {/* No Results Yet */}
        {!diagnostics && !loading && !error && (
          <div className="bg-slate-700 p-12 rounded-lg text-center text-slate-400">
            <p className="text-lg">Enter a ticker and click "Run Diagnostic" to see real API status</p>
            <p className="text-sm mt-2">Try: AAPL, AMZN, MSFT, etc.</p>
          </div>
        )}
      </div>
    </div>
  );
}
