import os
os.environ["GIT_PYTHON_REFRESH"] = "quiet"

import tempfile
import logging
from contextlib import asynccontextmanager
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

import app.core.shims
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.core.config import settings
from app.core.database import neo4j_service, qdrant_service
from app.ingest import ingest_service
from app.parser.sample_codebase import create_sample_codebase
from app.agents.impact_agent import impact_agent_executor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("app.main")

class IngestRequest(BaseModel):
    repo_path: Optional[str] = None
    use_sample: bool = False

class AnalyzeRequest(BaseModel):
    query: str
    target_symbol: str

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing Multi-Agent Codebase Navigator...")
    if len(neo4j_service._in_memory_nodes) == 0:
        logger.info("Empty graph detected. Generating and indexing sample enterprise architecture.")
        try:
            sample_dir = os.path.join(tempfile.gettempdir(), "navigator_sample_codebase")
            create_sample_codebase(sample_dir)
            ingest_service.ingest_repository(sample_dir, clear_existing=False)
        except Exception as e:
            logger.warning("Could not auto-seed sample codebase during startup: %s", str(e))
    yield
    neo4j_service.close()
    logger.info("Shutdown completed.")

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Interactive architectural map and onboarding assistant with Google Gemini AI.",
    version="1.0.0",
    lifespan=lifespan
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {
        "service": settings.PROJECT_NAME,
        "status": "active",
        "api_docs": "/docs",
        "health": "/api/health"
    }

@app.get("/api/health")
def get_health():
    gemini_key_set = bool(os.getenv("GEMINI_API_KEY", "").strip())
    return {
        "status": "healthy",
        "gemini_ai_configured": gemini_key_set,
        "gemini_model": "gemini-1.5-flash",
        "embeddings_model": "models/text-embedding-004" if gemini_key_set else "deterministic-768-dim",
        "neo4j_connected": neo4j_service.is_connected,
        "neo4j_mode": "remote_instance" if neo4j_service.is_connected else "embedded_graph_store",
        "qdrant_collection": qdrant_service.collection_name,
        "nodes_indexed": len(neo4j_service._in_memory_nodes),
        "edges_indexed": len(neo4j_service._in_memory_edges)
    }

@app.post("/api/ingest")
def ingest_codebase(payload: IngestRequest):
    """
    Ingests codebase from a GitHub URL (via GitPython), a local directory, or initializes sample architecture.
    Extracts AST via Tree-sitter, generates Gemini embeddings, and indexes into Qdrant & Neo4j.
    """
    raw_path = (payload.repo_path or "").strip()

    if payload.use_sample or not raw_path or raw_path.lower() in ("sample", "default"):
        sample_dir = os.path.join(tempfile.gettempdir(), "navigator_sample_codebase")
        create_sample_codebase(sample_dir)
        target_path = sample_dir
    else:
        target_path = raw_path

    try:
        stats = ingest_service.ingest_repository(target_path, clear_existing=True)
        return {
            "status": "success",
            "path": target_path,
            "stats": stats
        }
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except FileNotFoundError as fe:
        raise HTTPException(status_code=400, detail=str(fe))
    except Exception as e:
        logger.error("Ingestion failed: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")

@app.post("/api/load-sample")
def load_sample():
    """
    Seeds the system with the distributed enterprise codebase.
    """
    sample_dir = os.path.join(tempfile.gettempdir(), "navigator_sample_codebase")
    create_sample_codebase(sample_dir)
    stats = ingest_service.ingest_repository(sample_dir, clear_existing=True)
    return {
        "status": "success",
        "message": "Sample codebase loaded and indexed into Neo4j and Qdrant.",
        "stats": stats
    }

@app.get("/api/graph")
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

@app.get("/api/symbols")
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

@app.post("/api/analyze-impact")
def analyze_impact(payload: AnalyzeRequest):
    """
    Executes LangGraph multi-agent retrieval using Gemini 1.5 Flash,
    neo4j_traversal_tool, and qdrant_semantic_tool.
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
