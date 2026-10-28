import React, { useMemo } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  Panel,
  BackgroundVariant,
  useReactFlow,
  ReactFlowProvider
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import CustomNode from './CustomNode';

const CanvasInner = ({
  nodes,
  edges,
  onNodesChange,
  onEdgesChange,
  onNodeClick,
  viewMode,
  onResetView
}) => {
  const { fitView } = useReactFlow();

  const nodeTypes = useMemo(() => ({
    customEngineeredNode: CustomNode,
    Function: CustomNode,
    Class: CustomNode,
    File: CustomNode
  }), []);

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      onNodeClick={onNodeClick}
      nodeTypes={nodeTypes}
      fitView
      minZoom={0.15}
      maxZoom={2.5}
      defaultEdgeOptions={{
        type: 'smoothstep',
        style: { stroke: '#4a5568', strokeWidth: 1.5 }
      }}
    >
      <Background
        variant={BackgroundVariant.Dots}
        gap={24}
        size={1.5}
        color="#1e2638"
      />
      <Controls showInteractive={false} />
      
      <Panel position="top-left" style={{ margin: 12 }}>
        <div className="canvas-stats-badge">
          <div className="canvas-badge-item">
            <span className="badge-dim">Nodes:</span>
            <span className="badge-val">{nodes.length}</span>
          </div>
          <div className="canvas-badge-item">
            <span className="badge-dim">Dependencies:</span>
            <span className="badge-val">{edges.length}</span>
          </div>
          <div className="canvas-badge-item">
            <span className="badge-dim">Mode:</span>
            <span className="badge-val" style={{ color: viewMode === 'impact' ? '#ef4444' : '#10b981' }}>
              {viewMode === 'impact' ? 'FOCUSED IMPACT' : 'FULL ARCHITECTURE'}
            </span>
          </div>
          <button
            type="button"
            className="btn-canvas-action"
            onClick={() => fitView({ duration: 400, padding: 0.2 })}
            title="Fit graph to canvas view"
          >
            Fit View
          </button>
          {viewMode === 'impact' && (
            <button
              type="button"
              className="btn-canvas-action"
              onClick={onResetView}
              title="Return to full codebase architecture"
            >
              Full Graph
            </button>
          )}
        </div>
      </Panel>

      <MiniMap
        nodeColor={(n) => {
          if (n.data?.risk === 'critical') return '#ef4444';
          if (n.data?.risk === 'high') return '#f97316';
          if (n.data?.risk === 'medium') return '#f59e0b';
          if (n.data?.nodeType === 'Class') return '#f59e0b';
          if (n.data?.nodeType === 'File') return '#10b981';
          return '#3b82f6';
        }}
        maskColor="rgba(9, 13, 20, 0.85)"
        style={{
          backgroundColor: '#0f141c',
          border: '1px solid #2d3748',
          borderRadius: 4
        }}
      />
    </ReactFlow>
  );
};

const FlowCanvas = (props) => {
  return (
    <div className="canvas-viewport">
      <ReactFlowProvider>
        <CanvasInner {...props} />
      </ReactFlowProvider>
    </div>
  );
};

export default FlowCanvas;
