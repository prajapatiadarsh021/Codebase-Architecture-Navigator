import React, { memo } from 'react';
import { Handle, Position } from '@xyflow/react';

const CustomNode = ({ data }) => {
  const {
    label = 'symbol',
    file = '',
    nodeType = 'Function',
    signature = '',
    risk = 'low'
  } = data;

  const riskClass = `risk-${risk.toLowerCase()}`;

  return (
    <div className={`node-card ${riskClass}`}>
      <Handle
        type="target"
        position={Position.Left}
        style={{
          background: '#4a5568',
          width: 8,
          height: 8,
          borderRadius: 2,
          border: '1px solid #1e2638'
        }}
      />

      <div className="node-header">
        <span className={`node-badge-type ${nodeType}`}>
          {nodeType}
        </span>
        <span className={`node-badge-risk ${risk.toLowerCase()}`}>
          {risk.toUpperCase()}
        </span>
      </div>

      <div className="node-body">
        <div className="node-title" title={label}>
          {label}
        </div>
        {file && (
          <div className="node-file" title={file}>
            <span>path:</span> {file}
          </div>
        )}
        {signature && (
          <div className="node-signature" title={signature}>
            {signature}
          </div>
        )}
      </div>

      <Handle
        type="source"
        position={Position.Right}
        style={{
          background: '#4a5568',
          width: 8,
          height: 8,
          borderRadius: 2,
          border: '1px solid #1e2638'
        }}
      />
    </div>
  );
};

export default memo(CustomNode);
