import React from 'react';

const PrivacyPolicy = () => {
  return (
    <div className="legal-page-container">
      <article className="legal-article">
        <h1 className="legal-title">Privacy Policy</h1>
        <div className="legal-meta">
          Effective Date: October 2026 | Document Classification: Public Engineering Policy
        </div>

        <section className="legal-section">
          <h2 className="legal-section-title">1. Codebase Parsing and Data Ingestion</h2>
          <p className="legal-text">
            The Multi-Agent Codebase Onboarding & Architecture Navigator processes Abstract Syntax Trees
            (ASTs) of client codebases. AST extraction processes function definitions, signatures, imports,
            and call references.
          </p>
          <p className="legal-text">
            Source code repositories ingested via local paths or remote Git identifiers are processed locally
            within designated containerized workers. Raw source code files are parsed strictly for structural
            relationship extraction and are never transmitted to unauthorized third parties.
          </p>
        </section>

        <section className="legal-section">
          <h2 className="legal-section-title">2. Graph Database and Vector Storage</h2>
          <p className="legal-text">
            Structural metadata is persisted across two internal data stores:
          </p>
          <ul className="legal-list">
            <li>
              <strong>Neo4j Graph Database:</strong> Stores directed relationship nodes including File,
              Class, and Function declarations, linked via CALLS, CONTAINS, and IMPORTS edges.
            </li>
            <li>
              <strong>Qdrant Vector Database:</strong> Stores numeric embeddings generated from docstrings
              and function signatures to facilitate semantic code retrieval.
            </li>
          </ul>
        </section>

        <section className="legal-section">
          <h2 className="legal-section-title">3. Telemetry and Analytics</h2>
          <p className="legal-text">
            This platform operates in high-integrity engineering mode. We do not track user cursors,
            session recordings, or browser fingerprints. System logs are restricted to API execution
            timings, Cypher query error diagnostics, and vector upsert status reports.
          </p>
        </section>

        <section className="legal-section">
          <h2 className="legal-section-title">4. Data Retention and Deletion</h2>
          <p className="legal-text">
            Users retain complete control over ingested code metadata. Triggering the codebase reset
            action immediately purges Neo4j graph nodes and drops the corresponding Qdrant vector collections.
          </p>
        </section>
      </article>
    </div>
  );
};

export default PrivacyPolicy;
