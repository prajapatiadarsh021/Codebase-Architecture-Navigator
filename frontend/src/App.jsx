import React, { useState, useEffect, useCallback } from 'react';
import { applyNodeChanges, applyEdgeChanges } from '@xyflow/react';
import FlowCanvas from './components/FlowCanvas';
import QueryPanel from './components/QueryPanel';
import PrivacyPolicy from './components/PrivacyPolicy';
import Terms from './components/Terms';

const API_BASE = '/api';

const App = () => {
  const [currentRoute, setCurrentRoute] = useState('canvas'); // 'canvas' | 'privacy' | 'terms'
  const [nodes, setNodes] = useState([]);
  const [edges, setEdges] = useState([]);
  const [fullGraphCache, setFullGraphCache] = useState({ nodes: [], edges: [] });
  const [symbols, setSymbols] = useState([]);
  const [selectedSymbol, setSelectedSymbol] = useState('');
  const [analysisResult, setAnalysisResult] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [systemHealth, setSystemHealth] = useState(null);
  
  // Ingest modal & status
  const [isIngestModalOpen, setIsIngestModalOpen] = useState(false);
  const [ingestPathInput, setIngestPathInput] = useState('');
  const [isIngesting, setIsIngesting] = useState(false);
  const [ingestError, setIngestError] = useState('');
  const [ingestSuccessMessage, setIngestSuccessMessage] = useState('');

  // View mode: 'full' | 'impact'
  const [graphViewMode, setGraphViewMode] = useState('full');

  const onNodesChange = useCallback(
    (changes) => setNodes((nds) => applyNodeChanges(changes, nds)),
    []
  );

  const onEdgesChange = useCallback(
    (changes) => setEdges((eds) => applyEdgeChanges(changes, eds)),
    []
  );

  // Fetch initial graph and symbols
  const loadGraphData = useCallback(async () => {
    try {
      const [graphRes, symbolsRes, healthRes] = await Promise.all([
        fetch(`${API_BASE}/graph`),
        fetch(`${API_BASE}/symbols`),
        fetch(`${API_BASE}/health`)
      ]);

      if (graphRes.ok) {
        try {
          const graphData = await graphRes.json();
          setNodes(graphData.nodes || []);
          setEdges(graphData.edges || []);
          setFullGraphCache(graphData);
        } catch (e) {
          console.warn('Failed parsing graph data:', e);
        }
      }

      if (symbolsRes.ok) {
        try {
          const symbolsData = await symbolsRes.json();
          const symList = symbolsData.symbols || [];
          setSymbols(symList);
          if (symList.length > 0) {
            // If current symbol not in new list, pick first
            setSelectedSymbol((prev) => {
              const exists = symList.some((s) => s.name === prev);
              return exists ? prev : symList[0].name;
            });
          }
        } catch (e) {
          console.warn('Failed parsing symbols data:', e);
        }
      }

      if (healthRes.ok) {
        try {
          const healthData = await healthRes.json();
          setSystemHealth(healthData);
        } catch (e) {
          console.warn('Failed parsing health status data:', e);
        }
      }
    } catch (err) {
      console.error('Error loading initial architecture data:', err);
    }
  }, []);

  useEffect(() => {
    loadGraphData();
  }, [loadGraphData]);

  // Handle node click on canvas
  const handleNodeClick = (_, node) => {
    const symbolLabel = node.data?.label;
    if (symbolLabel) {
      setSelectedSymbol(symbolLabel);
    }
  };

  // Run impact analysis
  const handleRunAnalysis = async (symbol, query) => {
    setIsLoading(true);
    try {
      const res = await fetch(`${API_BASE}/analyze-impact`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          target_symbol: symbol,
          query: query
        })
      });

      let data = {};
      try {
        const text = await res.text();
        data = text ? JSON.parse(text) : {};
      } catch {
        data = {};
      }

      if (!res.ok) {
        throw new Error(data.detail || `Impact analysis failed (${res.status}: ${res.statusText || 'Check backend connection'})`);
      }

      setAnalysisResult(data);

      if (data.graph && data.graph.nodes && data.graph.nodes.length > 0) {
        setNodes(data.graph.nodes);
        setEdges(data.graph.edges || []);
        setGraphViewMode('impact');
      }
    } catch (err) {
      console.error('Analysis error:', err);
      alert(`Impact analysis failed: ${err.message}`);
    } finally {
      setIsLoading(false);
    }
  };

  // Reset to full codebase graph
  const handleResetToFullGraph = () => {
    if (fullGraphCache.nodes?.length > 0) {
      setNodes(fullGraphCache.nodes);
      setEdges(fullGraphCache.edges);
      setGraphViewMode('full');
    } else {
      loadGraphData();
    }
  };

  // Reload enterprise sample
  const handleReloadSample = async () => {
    setIsLoading(true);
    try {
      const res = await fetch(`${API_BASE}/load-sample`, { method: 'POST' });
      if (res.ok) {
        await loadGraphData();
        setAnalysisResult(null);
        setGraphViewMode('full');
        setIngestSuccessMessage('Enterprise sample codebase restored and re-indexed.');
        setTimeout(() => setIngestSuccessMessage(''), 6000);
      }
    } catch (err) {
      console.error('Failed to reload sample codebase:', err);
    } finally {
      setIsLoading(false);
    }
  };

  // Repository ingestion (GitHub or Local)
  const handleIngestSubmit = async (e) => {
    if (e) e.preventDefault();
    setIsIngesting(true);
    setIngestError('');
    try {
      const res = await fetch(`${API_BASE}/ingest`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          repo_path: ingestPathInput.trim(),
          use_sample: false
        })
      });

      let data = {};
      try {
        const text = await res.text();
        data = text ? JSON.parse(text) : {};
      } catch {
        data = {};
      }

      if (!res.ok) {
        throw new Error(
          data.detail || `Ingestion failed (${res.status}: ${res.statusText || 'Backend server may be offline'})`
        );
      }

      await loadGraphData();
      setIsIngestModalOpen(false);
      setIngestPathInput('');
      setAnalysisResult(null);
      setGraphViewMode('full');
      
      const stats = data.stats || {};
      setIngestSuccessMessage(
        `Successfully ingested repository: ${stats.files_indexed || 0} files, ${stats.classes_indexed || 0} classes, ${stats.functions_indexed || 0} functions, ${stats.edges_total || 0} dependencies mapped.`
      );
      setTimeout(() => setIngestSuccessMessage(''), 8000);
    } catch (err) {
      setIngestError(err.message || 'An unexpected error occurred during ingestion.');
    } finally {
      setIsIngesting(false);
    }
  };

  return (
    <div style={{ width: '100%', height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Top Application Header */}
      <header className="app-header">
        <div className="brand-section">
          <div className="brand-icon-wrapper">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="5" r="3"></circle>
              <line x1="12" y1="8" x2="12" y2="12"></line>
              <circle cx="6" cy="19" r="3"></circle>
              <circle cx="18" cy="19" r="3"></circle>
              <line x1="12" y1="12" x2="6" y2="16"></line>
              <line x1="12" y1="12" x2="18" y2="16"></line>
            </svg>
          </div>
          <span className="brand-title">Codebase Architecture Navigator</span>
          <span className="brand-version">v1.0-prod</span>
        </div>

        <nav className="header-nav">
          <button
            type="button"
            className={`nav-item ${currentRoute === 'canvas' ? 'active' : ''}`}
            onClick={() => setCurrentRoute('canvas')}
          >
            Architecture Canvas
          </button>
          <button
            type="button"
            className={`nav-item ${currentRoute === 'privacy' ? 'active' : ''}`}
            onClick={() => setCurrentRoute('privacy')}
          >
            Privacy Policy
          </button>
          <button
            type="button"
            className={`nav-item ${currentRoute === 'terms' ? 'active' : ''}`}
            onClick={() => setCurrentRoute('terms')}
          >
            Terms of Service
          </button>
        </nav>

        <div className="header-status-group">
          {systemHealth && (
            <div className="status-indicator">
              <span className={`status-dot ${systemHealth.status === 'healthy' ? '' : 'offline'}`}></span>
              <span>Store: {systemHealth.neo4j_mode}</span>
            </div>
          )}
          {graphViewMode === 'impact' && (
            <button
              type="button"
              className="btn-secondary"
              onClick={handleResetToFullGraph}
              style={{ padding: '4px 10px', fontSize: 11 }}
            >
              Show Full Graph
            </button>
          )}
        </div>
      </header>

      {/* Success Notification Banner */}
      {ingestSuccessMessage && (
        <div className="success-banner">
          <div className="success-banner-content">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#10b981" strokeWidth="2">
              <polyline points="20 6 9 17 4 12"></polyline>
            </svg>
            <span>{ingestSuccessMessage}</span>
          </div>
          <button
            type="button"
            className="btn-banner-close"
            onClick={() => setIngestSuccessMessage('')}
          >
            ✕
          </button>
        </div>
      )}

      {/* Main Content Area */}
      <main className="app-container">
        {currentRoute === 'canvas' && (
          <div className="workspace-layout">
            <FlowCanvas
              nodes={nodes}
              edges={edges}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onNodeClick={handleNodeClick}
              viewMode={graphViewMode}
              onResetView={handleResetToFullGraph}
            />
            <QueryPanel
              symbols={symbols}
              selectedSymbol={selectedSymbol}
              onSelectSymbol={setSelectedSymbol}
              analysisResult={analysisResult}
              isLoading={isLoading}
              onRunAnalysis={handleRunAnalysis}
              onOpenIngestModal={() => {
                setIngestError('');
                setIsIngestModalOpen(true);
              }}
              onReloadSample={handleReloadSample}
            />
          </div>
        )}

        {currentRoute === 'privacy' && <PrivacyPolicy />}
        {currentRoute === 'terms' && <Terms />}
      </main>

      {/* Repository Ingestion Modal (Supports GitHub URLs & Local Directories) */}
      {isIngestModalOpen && (
        <div className="ingest-modal-backdrop" onClick={() => !isIngesting && setIsIngestModalOpen(false)}>
          <div className="ingest-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div className="modal-title">Ingest Codebase Repository</div>
              <button
                type="button"
                className="nav-item"
                style={{ padding: '2px 8px' }}
                onClick={() => !isIngesting && setIsIngestModalOpen(false)}
                disabled={isIngesting}
              >
                ✕
              </button>
            </div>
            <form onSubmit={handleIngestSubmit}>
              <div className="modal-body">
                <p style={{ color: 'var(--text-secondary)', fontSize: 12, lineHeight: 1.6 }}>
                  Paste a public GitHub repository URL or specify a local directory path.
                  The engine will clone the code, parse Abstract Syntax Trees (AST) using Tree-sitter,
                  map function and class relationships, and index semantic embeddings into Qdrant.
                </p>

                <div className="form-group">
                  <label className="form-label" htmlFor="repo-path-input">
                    GitHub URL or Filesystem Path
                  </label>
                  <input
                    id="repo-path-input"
                    type="text"
                    className="form-input"
                    placeholder="https://github.com/username/repo.git or C:/projects/my-service"
                    value={ingestPathInput}
                    onChange={(e) => setIngestPathInput(e.target.value)}
                    disabled={isIngesting}
                    required
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">Quick Repo Presets</label>
                  <div className="quick-queries">
                    <button
                      type="button"
                      className="quick-btn"
                      onClick={() => setIngestPathInput('https://github.com/prajapatiadarsh021/diabetes-predection.git')}
                      disabled={isIngesting}
                    >
                      diabetes-predection (GitHub)
                    </button>
                    <button
                      type="button"
                      className="quick-btn"
                      onClick={() => setIngestPathInput('sample')}
                      disabled={isIngesting}
                    >
                      Enterprise Sample Architecture
                    </button>
                  </div>
                </div>

                {isIngesting && (
                  <div className="ingest-progress-box">
                    <div className="spinner-bar"></div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--accent-blue)' }}>
                      {ingestPathInput.includes('http') || ingestPathInput.includes('.git')
                        ? 'Cloning repository from GitHub and parsing Abstract Syntax Trees...'
                        : 'Scanning directory, extracting ASTs, and indexing into vector database...'}
                    </div>
                  </div>
                )}

                {ingestError && (
                  <div className="ingest-error-box">
                    <strong>Error:</strong> {ingestError}
                  </div>
                )}
              </div>

              <div className="modal-footer">
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => setIsIngestModalOpen(false)}
                  disabled={isIngesting}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn-primary"
                  disabled={isIngesting || !ingestPathInput.trim()}
                >
                  {isIngesting ? 'Processing Ingestion...' : 'Clone and Ingest Repository'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default App;
