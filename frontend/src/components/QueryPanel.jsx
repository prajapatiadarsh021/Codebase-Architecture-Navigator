import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';

const PRESET_QUERIES = [
  {
    symbol: 'authenticate_user',
    query: 'What breaks if I change the signature or return schema of authenticate_user?'
  },
  {
    symbol: 'UserSchema',
    query: 'Analyze downstream cascading impact if fields on UserSchema are altered or removed.'
  },
  {
    symbol: 'process_subscription_charge',
    query: 'What services, controllers, and background workers depend on process_subscription_charge?'
  },
  {
    symbol: 'calculate_monthly_invoices',
    query: 'Identify callers and ledger dependencies for calculate_monthly_invoices.'
  }
];

const QueryPanel = ({
  symbols,
  selectedSymbol,
  onSelectSymbol,
  analysisResult,
  isLoading,
  onRunAnalysis,
  onOpenIngestModal,
  onReloadSample
}) => {
  const [queryText, setQueryText] = useState(
    'What breaks if I change the signature or return schema of authenticate_user?'
  );

  const handlePresetSelect = (preset) => {
    onSelectSymbol(preset.symbol);
    setQueryText(preset.query);
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!selectedSymbol) return;
    onRunAnalysis(selectedSymbol, queryText);
  };

  return (
    <aside className="query-panel">
      <div className="panel-header">
        <div className="panel-title">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <polyline points="4 17 10 11 4 5"></polyline>
            <line x1="12" y1="19" x2="20" y2="19"></line>
          </svg>
          Architecture Query Terminal
        </div>
        <div className="btn-toolbar">
          <button
            type="button"
            className="btn-secondary"
            onClick={onOpenIngestModal}
            title="Ingest local or GitHub repository"
          >
            Ingest Repo
          </button>
          <button
            type="button"
            className="btn-secondary"
            onClick={onReloadSample}
            title="Reload enterprise sample codebase"
          >
            Reset Sample
          </button>
        </div>
      </div>

      <div className="panel-content">
        <form onSubmit={handleSubmit} className="form-group">
          <div className="form-group">
            <label className="form-label" htmlFor="target-symbol-select">
              Target Codebase Symbol
            </label>
            <select
              id="target-symbol-select"
              className="form-select"
              value={selectedSymbol}
              onChange={(e) => onSelectSymbol(e.target.value)}
            >
              <option value="">Select an indexed function or class...</option>
              {symbols.map((s) => (
                <option key={s.id} value={s.name}>
                  [{s.type}] {s.name} ({s.file})
                </option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label className="form-label">
              Common Impact Inquiries
            </label>
            <div className="quick-queries">
              {PRESET_QUERIES.map((pq, idx) => (
                <button
                  key={idx}
                  type="button"
                  className="quick-btn"
                  onClick={() => handlePresetSelect(pq)}
                >
                  {pq.symbol}
                </button>
              ))}
            </div>
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="impact-query-input">
              Downstream Refactoring Question
            </label>
            <textarea
              id="impact-query-input"
              className="form-textarea"
              rows={3}
              value={queryText}
              onChange={(e) => setQueryText(e.target.value)}
              placeholder="Specify the architectural change to evaluate..."
            />
          </div>

          <button
            type="submit"
            className="btn-primary"
            disabled={isLoading || !selectedSymbol}
          >
            {isLoading ? (
              <>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
                </svg>
                Evaluating Dependency Graph...
              </>
            ) : (
              <>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <polygon points="5 3 19 12 5 21 5 3"></polygon>
                </svg>
                Run Agentic Impact Analysis
              </>
            )}
          </button>
        </form>

        {/* Results display */}
        {analysisResult && (
          <div className="results-card">
            <div className="results-header">
              <span className={`badge-risk-banner ${analysisResult.risk_level}`}>
                {analysisResult.risk_level} SEVERITY
              </span>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)' }}>
                Target: {analysisResult.target_symbol}
              </span>
            </div>

            {analysisResult.affected_files && analysisResult.affected_files.length > 0 && (
              <div className="form-group">
                <label className="form-label">Impacted Source Modules</label>
                <div className="affected-list">
                  {analysisResult.affected_files.map((file, idx) => (
                    <div key={idx} className="affected-item">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" strokeWidth="2">
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                        <polyline points="14 2 14 8 20 8"></polyline>
                      </svg>
                      {file}
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="markdown-body">
              <ReactMarkdown>{analysisResult.analysis}</ReactMarkdown>
            </div>
          </div>
        )}
      </div>
    </aside>
  );
};

export default QueryPanel;
