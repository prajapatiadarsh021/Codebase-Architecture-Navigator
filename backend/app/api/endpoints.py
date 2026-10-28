import os
import re
import shutil
import tempfile
import logging
import subprocess
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.database import neo4j_service, qdrant_service
from app.parser.ingest import ingest_service
from app.parser.sample_codebase import create_sample_codebase
from app.agents.graph_agent import impact_agent_executor

logger = logging.getLogger("api_endpoints")
router = APIRouter()

class IngestRequest(BaseModel):
    repo_path: Optional[str] = None
    use_sample: bool = False

class AnalyzeRequest(BaseModel):
    query: str
    target_symbol: str

def is_git_url(path: str) -> bool:
    cleaned = path.strip().lower()
    return (
        cleaned.startswith("http://")
        or cleaned.startswith("https://")
        or cleaned.startswith("git@")
        or cleaned.endswith(".git")
        or "github.com/" in cleaned
        or "gitlab.com/" in cleaned
        or "bitbucket.org/" in cleaned
    )

def clone_git_repository(git_url: str) -> str:
    url = git_url.strip()
    if not url.startswith("http://") and not url.startswith("https://") and not url.startswith("git@"):
        url = "https://" + url

    repo_name_match = re.search(r"([^/]+?)(?:\.git)?$", url)
    repo_name = repo_name_match.group(1) if repo_name_match else "cloned_repo"
    clean_name = re.sub(r"[^a-zA-Z0-9_-]", "_", repo_name)
    target_dir = os.path.join(tempfile.gettempdir(), f"navigator_repo_{clean_name}")

    if os.path.exists(target_dir):
        try:
            def handle_remove_readonly(func, path, exc):
                import stat
                try:
                    os.chmod(path, stat.S_IWRITE)
                    func(path)
                except Exception:
                    pass
            shutil.rmtree(target_dir, onerror=handle_remove_readonly)
        except Exception as e:
            logger.warning("Could not clear previous clone folder %s: %s", target_dir, str(e))

    logger.info("Executing git clone: %s -> %s", url, target_dir)
    res = subprocess.run(
        ["git", "clone", "--depth", "1", url, target_dir],
        capture_output=True,
        text=True,
        timeout=180
    )

    if res.returncode != 0:
        err_msg = res.stderr.strip() or res.stdout.strip() or "Unknown git error occurred"
        logger.error("Git clone failed: %s", err_msg)
        raise ValueError(f"Git clone failed: {err_msg}")

    return target_dir

@router.get("/health")
def get_health():
    return {
        "status": "healthy",
        "neo4j_connected": neo4j_service.is_connected,
        "neo4j_mode": "remote_instance" if neo4j_service.is_connected else "embedded_graph_store",
        "qdrant_collection": qdrant_service.collection_name,
        "nodes_indexed": len(neo4j_service._in_memory_nodes),
        "edges_indexed": len(neo4j_service._in_memory_edges)
    }

@router.post("/ingest")
def ingest_codebase(payload: IngestRequest):
    """
    Ingests codebase from a GitHub URL, a local filesystem directory, or initializes sample architecture.
    """
    raw_path = (payload.repo_path or "").strip()
    
    if payload.use_sample or not raw_path or raw_path.lower() in ("sample", "default"):
        sample_dir = os.path.join(tempfile.gettempdir(), "navigator_sample_codebase")
        create_sample_codebase(sample_dir)
        target_path = sample_dir
        source_type = "sample"
    elif is_git_url(raw_path):
        try:
            target_path = clone_git_repository(raw_path)
            source_type = "git"
        except ValueError as ve:
            raise HTTPException(status_code=400, detail=str(ve))
        except Exception as ex:
            logger.error("Git clone exception: %s", str(ex))
            raise HTTPException(status_code=500, detail=f"Failed to clone repository: {str(ex)}")
    else:
        target_path = raw_path
        source_type = "local"
        if not os.path.exists(target_path):
            raise HTTPException(
                status_code=400,
                detail=f"Target path does not exist on server: {target_path}. Provide a valid public GitHub URL or existing local folder."
            )

    try:
        stats = ingest_service.ingest_directory(target_path, clear_existing=True)
        return {
            "status": "success",
            "source_type": source_type,
            "path": target_path,
            "stats": stats
        }
    except Exception as e:
        logger.error("Ingestion failed: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")

@router.post("/load-sample")
def load_sample():
    """
    Convenience endpoint to seed the system with the distributed enterprise codebase.
    """
    sample_dir = os.path.join(tempfile.gettempdir(), "navigator_sample_codebase")
    create_sample_codebase(sample_dir)
    stats = ingest_service.ingest_directory(sample_dir, clear_existing=True)
    return {
        "status": "success",
        "message": "Sample codebase loaded and indexed into Neo4j and Qdrant.",
        "stats": stats
    }

@router.get("/graph")
def get_graph():
    """
    Returns full node-link graph formatted for React Flow with balanced multi-column layout.
    """
    full_graph = neo4j_service.get_full_graph()
    nodes = full_graph.get("nodes", [])
    edges = full_graph.get("edges", [])
    
    file_nodes = [n for n in nodes if n["type"] == "File"]
    class_nodes = [n for n in nodes if n["type"] == "Class"]
    function_nodes = [n for n in nodes if n["type"] not in ("File", "Class")]
    
    formatted_nodes = []
    
    # Column 0: File nodes (x: 60)
    for idx, n in enumerate(file_nodes):
        formatted_nodes.append({
            "id": n["id"],
            "type": "customEngineeredNode",
            "position": {"x": 60, "y": 60 + (idx * 135)},
            "data": {
                "label": n["data"].get("label", n["id"]),
                "file": n["data"].get("file", ""),
                "nodeType": "File",
                "signature": n["data"].get("signature", ""),
                "risk": n["data"].get("risk", "low")
            }
        })
        
    # Column 1: Class nodes (x: 400)
    for idx, n in enumerate(class_nodes):
        formatted_nodes.append({
            "id": n["id"],
            "type": "customEngineeredNode",
            "position": {"x": 400, "y": 60 + (idx * 145)},
            "data": {
                "label": n["data"].get("label", n["id"]),
                "file": n["data"].get("file", ""),
                "nodeType": "Class",
                "signature": n["data"].get("signature", ""),
                "risk": n["data"].get("risk", "low")
            }
        })

    # Columns 2+: Function nodes wrapped across columns starting at x: 740
    fn_cols = 2 if len(function_nodes) > 12 else 1
    for idx, n in enumerate(function_nodes):
        c = idx % fn_cols
        r = idx // fn_cols
        formatted_nodes.append({
            "id": n["id"],
            "type": "customEngineeredNode",
            "position": {"x": 740 + (c * 330), "y": 60 + (r * 135)},
            "data": {
                "label": n["data"].get("label", n["id"]),
                "file": n["data"].get("file", ""),
                "nodeType": n.get("type", "Function"),
                "signature": n["data"].get("signature", ""),
                "risk": n["data"].get("risk", "low")
            }
        })
        
    return {
        "nodes": formatted_nodes,
        "edges": edges,
        "total_nodes": len(nodes),
        "total_edges": len(edges)
    }

@router.get("/symbols")
def get_symbols():
    """
    Returns indexed symbols for quick selection and autocomplete.
    """
    symbols = []
    for nid, node in neo4j_service._in_memory_nodes.items():
        if node.get("label") in ("Function", "Class"):
            symbols.append({
                "id": nid,
                "name": node.get("name", nid),
                "type": node.get("label"),
                "file": node.get("file", ""),
                "signature": node.get("signature", "")
            })
    symbols.sort(key=lambda s: s["name"])
    return {"symbols": symbols}

@router.post("/analyze-impact")
def analyze_impact(payload: AnalyzeRequest):
    """
    Executes LangGraph agentic retrieval across Neo4j graph and Qdrant vector index.
    Returns impact assessment markdown and React Flow subgraph.
    """
    target = payload.target_symbol.strip()
    query = payload.query.strip()
    
    if not target:
        raise HTTPException(status_code=400, detail="target_symbol parameter is required.")
        
    try:
        initial_state = {
            "query": query,
            "target_symbol": target,
            "graph_context": {},
            "semantic_chunks": [],
            "analysis": "",
            "risk_level": "LOW",
            "suggested_tests": [],
            "react_flow_graph": {"nodes": [], "edges": []}
        }
        
        result_state = impact_agent_executor.invoke(initial_state)
        
        return {
            "target_symbol": target,
            "query": query,
            "risk_level": result_state.get("risk_level", "LOW"),
            "analysis": result_state.get("analysis", ""),
            "suggested_tests": result_state.get("suggested_tests", []),
            "graph": result_state.get("react_flow_graph", {"nodes": [], "edges": []}),
            "affected_files": result_state.get("graph_context", {}).get("affected_files", [])
        }
    except Exception as e:
        logger.error("Analysis execution error: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")
