import os
import json
import logging
from typing import Dict, Any, List, Optional, TypedDict

from dotenv import load_dotenv
import app.core.shims
from langgraph.graph import StateGraph, END

from app.core.database import neo4j_service, qdrant_service

load_dotenv()
logger = logging.getLogger("impact_agent")
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

# Phase 2: Agent Tools Creation

def qdrant_semantic_tool(state: ImpactAnalysisState) -> Dict[str, Any]:
    """
    Performs semantic search over indexed code vectors in Qdrant to find relevant
    functions, contracts, and context when a developer asks natural language questions.
    """
    symbol = state.get("target_symbol", "").strip()
    query = state.get("query", "").strip()
    search_prompt = f"{symbol} {query}".strip()
    
    logger.info("Executing qdrant_semantic_tool for query: '%s'", search_prompt)
    
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    query_vector = None
    if gemini_key:
        try:
            from langchain_google_genai import GoogleGenerativeAIEmbeddings
            embeddings = GoogleGenerativeAIEmbeddings(
                model="models/text-embedding-004",
                google_api_key=gemini_key
            )
            query_vector = embeddings.embed_query(search_prompt)
        except Exception as e:
            logger.warning("Gemini query embedding failed: %s. Using fallback vector.", str(e))
            query_vector = None
            
    chunks = qdrant_service.search_similar(search_prompt, limit=5, query_vector=query_vector)
    return {"semantic_chunks": chunks}

def neo4j_traversal_tool(state: ImpactAnalysisState) -> Dict[str, Any]:
    """
    Executes Cypher depth queries on the Neo4j dependency graph to trace upstream
    callers, downstream dependents, and call hierarchies.
    """
    symbol = state.get("target_symbol", "").strip()
    logger.info("Executing neo4j_traversal_tool for target: '%s'", symbol)
    traversal_result = neo4j_service.get_downstream_impact(symbol, max_depth=3)
    return {"graph_context": traversal_result}

# Phase 3: Multi-Agent Reasoning (LangGraph + Gemini)

def gemini_reasoning_node(state: ImpactAnalysisState) -> Dict[str, Any]:
    """
    Uses ChatGoogleGenerativeAI (gemini-1.5-flash) to reason about breaking changes,
    assign technical risk levels, and generate pytest-compatible unit tests.
    """
    target = state.get("target_symbol", "Unknown")
    query = state.get("query", "")
    graph = state.get("graph_context", {})
    semantic = state.get("semantic_chunks", [])
    
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    affected_files = graph.get("affected_files", [])
    
    callers = [e["source"] for e in edges if e.get("label") == "CALLS"]
    
    # Calculate baseline risk level
    node_count = len(nodes)
    if node_count >= 5 or len(affected_files) >= 3:
        baseline_risk = "CRITICAL"
    elif node_count >= 3 or len(affected_files) >= 2:
        baseline_risk = "HIGH"
    elif node_count >= 2:
        baseline_risk = "MEDIUM"
    else:
        baseline_risk = "LOW"

    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    llm_analysis = None
    llm_risk = baseline_risk
    suggested_tests = []

    if gemini_key:
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            llm = ChatGoogleGenerativeAI(
                model="gemini-1.5-flash",
                temperature=0,
                google_api_key=gemini_key
            )
            
            prompt = f"""You are a Principal Software Architect conducting an automated static call-graph impact analysis.
Analyze the impact of modifying `{target}` based on the user question and the retrieved graph and vector data.

CRITICAL RULES:
- Never use em dashes (use colons, parentheses, or separate sentences).
- Use precise technical engineering terminology.
- No vague marketing buzzwords or AI-slop copy.

CONTEXT DATA:
User Query: {query}
Target Symbol: {target}
Direct Callers: {callers}
Impacted Nodes Count: {node_count}
Impacted Source Files: {affected_files}
Semantic Code Context Chunks: {json.dumps(semantic, default=str)}

OUTPUT FORMAT REQUIREMENTS:
Provide your response in structured markdown with the following sections:
1. Executive Risk Rating: State the risk level (CRITICAL, HIGH, MEDIUM, or LOW) and a 1-sentence technical justification.
2. Downstream Breaking Surface: Bulleted list explaining which caller functions, endpoints, or services break if `{target}` is modified.
3. Affected Modules: List the files with exact filepaths.
4. Refactoring Protocol: 3 concrete, sequential engineering instructions (e.g. backward-compatibility shims, parameter deprecation, migration window).
5. Pytest Verification Suite: Provide 3 concrete, executable pytest test function signatures with docstrings verifying backward compatibility and error handling.
"""
            response = llm.invoke(prompt)
            llm_analysis = response.content if hasattr(response, "content") else str(response)
            
            # Extract risk rating from LLM response if explicitly mentioned
            upper_content = llm_analysis.upper()
            if "CRITICAL" in upper_content:
                llm_risk = "CRITICAL"
            elif "HIGH" in upper_content:
                llm_risk = "HIGH"
            elif "MEDIUM" in upper_content:
                llm_risk = "MEDIUM"
            elif "LOW" in upper_content:
                llm_risk = "LOW"
                
            # Extract suggested test names
            lines = llm_analysis.splitlines()
            for line in lines:
                if "def test_" in line:
                    clean_test = line.replace("def ", "").replace(":", "").strip()
                    suggested_tests.append(clean_test)
                    
            logger.info("Successfully completed Gemini 1.5 Flash architectural impact reasoning.")
        except Exception as e:
            logger.warning("Gemini LLM reasoning call failed: %s. Using algorithmic synthesis.", str(e))
            llm_analysis = None

    # Fallback algorithmic synthesis if Gemini API key not present or call failed
    if not llm_analysis:
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

        target_short = target.split(".")[-1].lower()
        suggested_tests = [
            f"test_{target_short}_signature_backwards_compatibility",
            f"test_{target_short}_null_payload_rejection",
            f"test_{target_short}_downstream_caller_regression"
        ]

        llm_analysis = f"""### Architectural Impact Assessment: `{target}`

#### Executive Risk Rating
**Status**: {baseline_risk} SEVERITY: Impact scope spans {node_count} dependent nodes across {len(affected_files)} source files.

#### User Query Objective
{query}

#### Downstream Breaking Surface
Modifying or altering `{target}` directly cascades to the following caller entry points:
{caller_list_str}

#### Affected Source Files
{file_list_str}

#### Semantic Vector Similarity Context (Qdrant)
{semantic_matches_str}

#### Refactoring Protocol
1. **Contract Preservation**: Maintain backward-compatible parameter defaults or introduce an adapter layer.
2. **Deprecation Phase**: Mark the existing `{target}` interface with `@typing.deprecated` before consumers migrate.
3. **Automated Verification**: Run integration tests across all {len(affected_files)} dependent files before merging downstream PRs.

#### Pytest Verification Suite
```python
def test_{target_short}_signature_backwards_compatibility():
    \"\"\"Validate that {target} maintains backward-compatible return schema.\"\"\"
    pass

def test_{target_short}_null_payload_rejection():
    \"\"\"Validate that {target} gracefully rejects invalid inputs with ValueError.\"\"\"
    pass

def test_{target_short}_downstream_caller_regression():
    \"\"\"Verify integration across callers without signature mismatch.\"\"\"
    pass
```
"""

    return {
        "analysis": llm_analysis,
        "risk_level": llm_risk,
        "suggested_tests": suggested_tests
    }

def react_flow_formatter_node(state: ImpactAnalysisState) -> Dict[str, Any]:
    """
    Formats the impacted dependency subgraph into nodes and edges specifically for React Flow.
    """
    graph = state.get("graph_context", {})
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    overall_risk = state.get("risk_level", "low").lower()

    react_flow_nodes = []
    react_flow_edges = []

    # Layout by traversal depth
    depth_groups: Dict[int, List[Dict[str, Any]]] = {}
    for node in nodes:
        d = node.get("depth", 1)
        if d not in depth_groups:
            depth_groups[d] = []
        depth_groups[d].append(node)

    for depth, group_nodes in depth_groups.items():
        x_base = 80 if depth == 0 else (120 + depth * 340)
        for row_idx, node in enumerate(group_nodes):
            y_pos = 80 + (row_idx * 140)
            
            node_risk = "critical" if depth == 0 else ("high" if depth == 1 else ("medium" if depth == 2 else "low"))
            if overall_risk == "low":
                node_risk = "low"

            react_flow_nodes.append({
                "id": node["id"],
                "type": "customEngineeredNode",
                "position": {"x": x_base, "y": y_pos},
                "data": {
                    "label": node["data"].get("label", node["id"]),
                    "file": node["data"].get("file", ""),
                    "nodeType": node.get("type", "Function"),
                    "signature": node["data"].get("signature", ""),
                    "risk": node_risk,
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

    return {
        "react_flow_graph": {
            "nodes": react_flow_nodes,
            "edges": react_flow_edges
        }
    }

def build_impact_agent():
    workflow = StateGraph(ImpactAnalysisState)

    workflow.add_node("neo4j_traversal_tool", neo4j_traversal_tool)
    workflow.add_node("qdrant_semantic_tool", qdrant_semantic_tool)
    workflow.add_node("gemini_reasoning_node", gemini_reasoning_node)
    workflow.add_node("react_flow_formatter_node", react_flow_formatter_node)

    workflow.set_entry_point("neo4j_traversal_tool")
    workflow.add_edge("neo4j_traversal_tool", "qdrant_semantic_tool")
    workflow.add_edge("qdrant_semantic_tool", "gemini_reasoning_node")
    workflow.add_edge("gemini_reasoning_node", "react_flow_formatter_node")
    workflow.add_edge("react_flow_formatter_node", END)

    return workflow.compile()

impact_agent_executor = build_impact_agent()
