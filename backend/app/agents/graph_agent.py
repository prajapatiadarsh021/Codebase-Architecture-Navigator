import logging
from typing import Dict, Any, List, TypedDict
import app.core.shims
from langgraph.graph import StateGraph, END
from app.core.database import neo4j_service, qdrant_service

logger = logging.getLogger("graph_agent")
logger.setLevel(logging.INFO)

class ImpactAnalysisState(TypedDict):
    query: str
    target_symbol: str
    graph_context: Dict[str, Any]
    semantic_chunks: List[Dict[str, Any]]
    analysis: str
    risk_level: str
    suggested_tests: List[str]
    react_flow_graph: Dict[str, Any]

def neo4j_traversal_tool(state: ImpactAnalysisState) -> Dict[str, Any]:
    """
    Executes graph depth traversal from target_symbol to discover all callers,
    contained methods, and dependent files.
    """
    symbol = state.get("target_symbol", "").strip()
    logger.info("Executing Neo4j traversal tool for symbol: %s", symbol)
    traversal_result = neo4j_service.get_downstream_impact(symbol, max_depth=3)
    return {"graph_context": traversal_result}

def qdrant_semantic_tool(state: ImpactAnalysisState) -> Dict[str, Any]:
    """
    Retrieves semantic symbol documentation, signatures, and context embeddings.
    """
    symbol = state.get("target_symbol", "").strip()
    query = state.get("query", "").strip()
    search_prompt = f"{symbol} {query}".strip()
    logger.info("Executing Qdrant semantic tool for prompt: %s", search_prompt)
    chunks = qdrant_service.search_similar(search_prompt, limit=5)
    return {"semantic_chunks": chunks}

def impact_synthesizer_agent(state: ImpactAnalysisState) -> Dict[str, Any]:
    """
    Synthesizes graph traversal and semantic vector context into an engineering report.
    Complies strictly with anti-vibe-coding rules: no em dashes, pure technical language.
    """
    target = state.get("target_symbol", "Unknown")
    query = state.get("query", "")
    graph = state.get("graph_context", {})
    semantic = state.get("semantic_chunks", [])
    
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    affected_files = graph.get("affected_files", [])
    
    callers = [
        e["source"] for e in edges if e.get("label") == "CALLS"
    ]
    
    # Calculate deterministic risk severity
    node_count = len(nodes)
    if node_count >= 5 or len(affected_files) >= 3:
        risk_level = "CRITICAL"
        risk_badge = "CRITICAL RISK: Multiple cross-module breaking dependencies detected"
    elif node_count >= 3 or len(affected_files) >= 2:
        risk_level = "HIGH"
        risk_badge = "HIGH RISK: Cascades to adjacent service layer"
    elif node_count >= 2:
        risk_level = "MEDIUM"
        risk_badge = "MEDIUM RISK: Isolated to local module callers"
    else:
        risk_level = "LOW"
        risk_badge = "LOW RISK: Leaf node or uncoupled interface"

    # Generate unit test suggestions
    suggested_tests = [
        f"test_{target.split('.')[-1].lower()}_signature_compatibility: Validate parameter contracts and return schema",
        f"test_{target.split('.')[-1].lower()}_null_payload_rejection: Ensure invalid type mutations fail with descriptive exceptions",
        f"test_downstream_regression_on_{len(affected_files)}_modules: Verify callers maintain backwards compatibility"
    ]
    for af in affected_files[:3]:
        mod_name = af.replace(".py", "").replace("/", "_")
        suggested_tests.append(f"test_{mod_name}_integration_pipeline: Verify end-to-end payload routing without schema mismatch")

    # Format React Flow nodes and edges with calculated risk and position
    # Radial or hierarchical grid layout for clean visualization
    react_flow_nodes = []
    react_flow_edges = []
    
    for idx, node in enumerate(nodes):
        depth = node.get("depth", 1)
        x_pos = 100 + (depth * 320)
        y_pos = 80 + (idx * 130)
        
        # Override position if center target
        if depth == 0:
            x_pos = 80
            y_pos = 200

        react_flow_nodes.append({
            "id": node["id"],
            "type": "customEngineeredNode",
            "position": {"x": x_pos, "y": y_pos},
            "data": {
                "label": node["data"].get("label", node["id"]),
                "file": node["data"].get("file", ""),
                "nodeType": node.get("type", "Function"),
                "signature": node["data"].get("signature", ""),
                "risk": node["data"].get("risk", "low"),
                "depth": depth
            }
        })

    for edge in edges:
        react_flow_edges.append({
            "id": edge["id"],
            "source": edge["source"],
            "target": edge["target"],
            "label": edge.get("label", "CALLS"),
            "animated": True if edge.get("label") == "CALLS" else False,
            "style": {"stroke": "#4a5568", "strokeWidth": 2}
        })

    # Construct clean technical engineering report without any em dashes
    caller_list_str = "\n".join([f"- `{c}`" for c in callers[:8]]) if callers else "- No direct inward call references found in indexed AST."
    file_list_str = "\n".join([f"- `{f}`" for f in affected_files]) if affected_files else "- Localized execution scope."
    
    semantic_matches_str = ""
    if semantic:
        semantic_matches_str = "\n".join([
            f"- **{s.get('name')}** (`{s.get('type')}` in `{s.get('file')}`): {s.get('docstring') or s.get('signature') or 'No docstring provided'}"
            for s in semantic[:3]
        ])
    else:
        semantic_matches_str = "- No secondary semantic matches indexed."

    report_markdown = f"""### Architectural Impact Assessment: `{target}`

#### Severity Rating
**Status**: {risk_badge}
**Impact Scope**: {len(nodes)} dependent nodes across {len(affected_files)} source files.

#### User Query Objective
{query}

#### Downstream Dependency Surface
Modifying or refactoring `{target}` directly influences the following caller entry points:
{caller_list_str}

#### Affected Source Files
{file_list_str}

#### Semantic Vector Similarity Context
Top semantic chunks identified in the vector database:
{semantic_matches_str}

#### Recommended Refactoring Protocol
1. **Contract Preservation**: Introduce default parameter fallbacks or an intermediary adapter to prevent breaking existing call sites.
2. **Deprecation Window**: Tag the current `{target}` interface with `@typing.deprecated` before shifting consumers to the revised signature.
3. **Validation Sequence**: Execute integration tests across all {len(affected_files)} dependent files before merging downstream PRs.

#### Suggested Verification Tests
"""
    for test in suggested_tests:
        report_markdown += f"- `{test}`\n"

    return {
        "analysis": report_markdown,
        "risk_level": risk_level,
        "suggested_tests": suggested_tests,
        "react_flow_graph": {
            "nodes": react_flow_nodes,
            "edges": react_flow_edges
        }
    }

def build_impact_agent_workflow():
    workflow = StateGraph(ImpactAnalysisState)
    
    workflow.add_node("neo4j_traversal_tool", neo4j_traversal_tool)
    workflow.add_node("qdrant_semantic_tool", qdrant_semantic_tool)
    workflow.add_node("impact_synthesizer", impact_synthesizer_agent)
    
    workflow.set_entry_point("neo4j_traversal_tool")
    workflow.add_edge("neo4j_traversal_tool", "qdrant_semantic_tool")
    workflow.add_edge("qdrant_semantic_tool", "impact_synthesizer")
    workflow.add_edge("impact_synthesizer", END)
    
    return workflow.compile()

impact_agent_executor = build_impact_agent_workflow()
