import math
import hashlib
import logging
from typing import Dict, List, Any, Optional
import neo4j
from neo4j import GraphDatabase
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from app.core.config import settings

logger = logging.getLogger("db_manager")
logger.setLevel(logging.INFO)

# Deterministic 768-dim semantic embedding vector generator matching Gemini text-embedding-004
def compute_embedding(text: str, dim: int = 768) -> List[float]:
    """
    Computes a deterministic normalized semantic representation for a text chunk.
    Ensures stable cosine similarity calculation when GEMINI_API_KEY is not configured.
    """
    cleaned = text.lower().strip()
    words = [w for w in cleaned.replace("(", " ").replace(")", " ").replace(":", " ").split() if len(w) > 1]
    vector = [0.0] * dim
    
    if not words:
        return [1.0 / math.sqrt(dim)] * dim
        
    for word in words:
        h = int(hashlib.sha256(word.encode("utf-8")).hexdigest(), 16)
        idx = h % dim
        sign = 1.0 if ((h >> 8) % 2 == 0) else -1.0
        weight = 1.0 + (len(word) / 10.0)
        vector[idx] += sign * weight

    # Normalize vector to unit length (L2 norm)
    norm = math.sqrt(sum(x * x for x in vector))
    if norm > 0:
        vector = [x / norm for x in vector]
    else:
        vector = [1.0 / math.sqrt(dim)] * dim
    return vector


class Neo4jGraphService:
    def __init__(self):
        self.driver: Optional[neo4j.Driver] = None
        self.is_connected = False
        
        # Resilient in-memory graph fallback
        self._in_memory_nodes: Dict[str, Dict[str, Any]] = {}
        self._in_memory_edges: List[Dict[str, Any]] = []
        
        self.init_driver()

    def init_driver(self):
        try:
            self.driver = GraphDatabase.driver(
                settings.NEO4J_URI,
                auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
            )
            self.driver.verify_connectivity()
            self.is_connected = True
            logger.info("Connected to Neo4j instance at %s", settings.NEO4J_URI)
            self._ensure_constraints()
        except Exception as e:
            self.is_connected = False
            logger.warning("Neo4j not reachable (%s). Initializing in-memory fallback store.", str(e))

    def _ensure_constraints(self):
        if not self.is_connected or not self.driver:
            return
        try:
            with self.driver.session() as session:
                session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (f:File) REQUIRE f.id IS UNIQUE")
                session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (c:Class) REQUIRE c.id IS UNIQUE")
                session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (fn:Function) REQUIRE fn.id IS UNIQUE")
        except Exception as e:
            logger.error("Failed to set Neo4j constraints: %s", str(e))

    def close(self):
        if self.driver:
            self.driver.close()

    def clear(self):
        self._in_memory_nodes.clear()
        self._in_memory_edges.clear()
        if self.is_connected and self.driver:
            try:
                with self.driver.session() as session:
                    session.run("MATCH (n) DETACH DELETE n")
            except Exception as e:
                logger.error("Error clearing Neo4j: %s", str(e))

    def upsert_node(self, node_id: str, label: str, properties: Dict[str, Any]):
        props = dict(properties)
        props["id"] = node_id
        props["label"] = label
        
        # In-memory update
        self._in_memory_nodes[node_id] = props
        
        if self.is_connected and self.driver:
            try:
                query = f"""
                MERGE (n:{label} {{id: $id}})
                SET n += $props
                """
                with self.driver.session() as session:
                    session.run(query, id=node_id, props=props)
            except Exception as e:
                logger.error("Neo4j upsert_node error: %s", str(e))

    def add_relationship(self, from_id: str, to_id: str, rel_type: str, properties: Optional[Dict[str, Any]] = None):
        props = properties or {}
        edge = {
            "source": from_id,
            "target": to_id,
            "type": rel_type,
            "properties": props
        }
        
        # Check if edge already exists in-memory
        if not any(e["source"] == from_id and e["target"] == to_id and e["type"] == rel_type for e in self._in_memory_edges):
            self._in_memory_edges.append(edge)
            
        if self.is_connected and self.driver:
            try:
                query = f"""
                MATCH (a {{id: $from_id}}), (b {{id: $to_id}})
                MERGE (a)-[r:{rel_type}]->(b)
                SET r += $props
                """
                with self.driver.session() as session:
                    session.run(query, from_id=from_id, to_id=to_id, props=props)
            except Exception as e:
                logger.error("Neo4j add_relationship error: %s", str(e))

    def get_full_graph(self) -> Dict[str, Any]:
        """
        Returns all nodes and edges formatted for React Flow.
        """
        if self.is_connected and self.driver:
            try:
                nodes_dict = {}
                edges_list = []
                with self.driver.session() as session:
                    res_nodes = session.run("MATCH (n) RETURN n.id AS id, labels(n)[0] AS type, properties(n) AS props")
                    for r in res_nodes:
                        nid = r["id"]
                        props = dict(r["props"])
                        nodes_dict[nid] = {
                            "id": nid,
                            "type": r["type"],
                            "data": {
                                "label": props.get("name", nid),
                                "type": r["type"],
                                "file": props.get("file", ""),
                                "signature": props.get("signature", ""),
                                "risk": props.get("risk", "low")
                            }
                        }
                    res_edges = session.run("MATCH (a)-[r]->(b) RETURN a.id AS source, b.id AS target, type(r) AS type, properties(r) AS props")
                    for r in res_edges:
                        edges_list.append({
                            "id": f"{r['source']}->{r['target']}:{r['type']}",
                            "source": r["source"],
                            "target": r["target"],
                            "label": r["type"],
                            "type": "smoothstep"
                        })
                return {"nodes": list(nodes_dict.values()), "edges": edges_list}
            except Exception as e:
                logger.error("Error reading Neo4j full graph: %s. Falling back to in-memory.", str(e))
                
        # In-memory graph representation
        formatted_nodes = []
        for nid, node_data in self._in_memory_nodes.items():
            formatted_nodes.append({
                "id": nid,
                "type": node_data.get("label", "Function"),
                "data": {
                    "label": node_data.get("name", nid),
                    "type": node_data.get("label", "Function"),
                    "file": node_data.get("file", ""),
                    "signature": node_data.get("signature", ""),
                    "risk": node_data.get("risk", "low")
                }
            })
            
        formatted_edges = []
        for i, edge in enumerate(self._in_memory_edges):
            formatted_edges.append({
                "id": f"{edge['source']}->{edge['target']}:{edge['type']}:{i}",
                "source": edge["source"],
                "target": edge["target"],
                "label": edge["type"],
                "type": "smoothstep"
            })
            
        return {"nodes": formatted_nodes, "edges": formatted_edges}

    def get_downstream_impact(self, target_symbol: str, max_depth: int = 3) -> Dict[str, Any]:
        """
        Traverses callers and dependents of the target symbol.
        """
        # Search target node
        matched_target_id = None
        for nid, node in self._in_memory_nodes.items():
            if node.get("name") == target_symbol or nid == target_symbol or nid.endswith(f":{target_symbol}"):
                matched_target_id = nid
                break
                
        if not matched_target_id:
            # Fallback search
            for nid in self._in_memory_nodes.keys():
                if target_symbol.lower() in nid.lower():
                    matched_target_id = nid
                    break
                    
        if not matched_target_id:
            return {"target": target_symbol, "nodes": [], "edges": [], "affected_files": []}
            
        # BFS traversal for callers (incoming CALLS/IMPORTS/CONTAINS relationships)
        visited_nodes = {matched_target_id: 0}
        frontier = [matched_target_id]
        collected_edges = []
        
        current_depth = 0
        while frontier and current_depth < max_depth:
            next_frontier = []
            for current in frontier:
                # Upstream callers: nodes that CALL current, or IMPORT current
                for edge in self._in_memory_edges:
                    src = edge["source"]
                    tgt = edge["target"]
                    if tgt == current:
                        collected_edges.append(edge)
                        if src not in visited_nodes:
                            visited_nodes[src] = current_depth + 1
                            next_frontier.append(src)
                    elif src == current:
                        collected_edges.append(edge)
                        if tgt not in visited_nodes:
                            visited_nodes[tgt] = current_depth + 1
                            next_frontier.append(tgt)
            frontier = next_frontier
            current_depth += 1

        # Format impact nodes and calculate risk score
        affected_files = set()
        impact_nodes = []
        for nid, depth in visited_nodes.items():
            node_props = self._in_memory_nodes.get(nid, {})
            fpath = node_props.get("file", "")
            if fpath:
                affected_files.add(fpath)
            
            risk = "critical" if depth == 0 else ("high" if depth == 1 else ("medium" if depth == 2 else "low"))
            impact_nodes.append({
                "id": nid,
                "type": node_props.get("label", "Function"),
                "depth": depth,
                "data": {
                    "label": node_props.get("name", nid),
                    "type": node_props.get("label", "Function"),
                    "file": fpath,
                    "signature": node_props.get("signature", ""),
                    "risk": risk
                }
            })

        formatted_edges = [
            {
                "id": f"{e['source']}->{e['target']}:{e['type']}",
                "source": e["source"],
                "target": e["target"],
                "label": e["type"]
            }
            for e in collected_edges
        ]

        return {
            "target": matched_target_id,
            "nodes": impact_nodes,
            "edges": formatted_edges,
            "affected_files": sorted(list(affected_files))
        }


class QdrantVectorService:
    def __init__(self):
        self.collection_name = settings.QDRANT_COLLECTION
        self.dim = 768
        
        # If QDRANT_URL is :memory: or not set, use local in-memory
        if not settings.QDRANT_URL or settings.QDRANT_URL == ":memory:":
            self.client = QdrantClient(":memory:")
            logger.info("Initialized Qdrant client in :memory: mode.")
        else:
            self.client = QdrantClient(
                url=settings.QDRANT_URL,
                api_key=settings.QDRANT_API_KEY if settings.QDRANT_API_KEY else None
            )
            logger.info("Connected to Qdrant at %s", settings.QDRANT_URL)
            
        self._ensure_collection()
        self._point_counter = 1

    def _ensure_collection(self):
        try:
            collections = self.client.get_collections().collections
            exists = any(c.name == self.collection_name for c in collections)
            if not exists:
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=qmodels.VectorParams(
                        size=self.dim,
                        distance=qmodels.Distance.COSINE
                    )
                )
                logger.info("Created Qdrant collection: %s (dim=%d)", self.collection_name, self.dim)
        except Exception as e:
            logger.error("Error ensuring Qdrant collection: %s", str(e))

    def clear(self):
        try:
            self.client.delete_collection(collection_name=self.collection_name)
            self._ensure_collection()
            self._point_counter = 1
        except Exception as e:
            logger.error("Error clearing Qdrant collection: %s", str(e))

    def upsert_symbol(
        self,
        symbol_id: str,
        name: str,
        symbol_type: str,
        file_path: str,
        signature: str,
        docstring: str,
        code_snippet: str = "",
        custom_vector: Optional[List[float]] = None,
        custom_summary: Optional[str] = None
    ):
        if custom_vector and len(custom_vector) == self.dim:
            vector = custom_vector
        else:
            content_for_embedding = f"{name} {symbol_type} {signature} {docstring} {code_snippet}"
            vector = compute_embedding(content_for_embedding, dim=self.dim)
        
        point_id = self._point_counter
        self._point_counter += 1
        
        summary = custom_summary or f"{symbol_type} '{name}' in {file_path}: {docstring or signature}"
        
        payload = {
            "symbol_id": symbol_id,
            "name": name,
            "type": symbol_type,
            "file": file_path,
            "signature": signature,
            "docstring": docstring,
            "code_chunk": code_snippet,
            "summary": summary
        }
        
        try:
            self.client.upsert(
                collection_name=self.collection_name,
                points=[
                    qmodels.PointStruct(
                        id=point_id,
                        vector=vector,
                        payload=payload
                    )
                ]
            )
        except Exception as e:
            logger.error("Failed to upsert point to Qdrant: %s", str(e))

    def search_similar(self, query: str, limit: int = 5, query_vector: Optional[List[float]] = None) -> List[Dict[str, Any]]:
        vec = query_vector if (query_vector and len(query_vector) == self.dim) else compute_embedding(query, dim=self.dim)
        try:
            if hasattr(self.client, "query_points"):
                response = self.client.query_points(
                    collection_name=self.collection_name,
                    query=vec,
                    limit=limit
                )
                hits = response.points
            else:
                hits = self.client.search(
                    collection_name=self.collection_name,
                    query_vector=vec,
                    limit=limit
                )
                
            output = []
            for hit in hits:
                payload = hit.payload or {}
                output.append({
                    "score": round(float(hit.score if hasattr(hit, "score") else 0.0), 4),
                    "name": payload.get("name", ""),
                    "type": payload.get("type", ""),
                    "file": payload.get("file", ""),
                    "signature": payload.get("signature", ""),
                    "docstring": payload.get("docstring", ""),
                    "summary": payload.get("summary", "")
                })
            return output
        except Exception as e:
            logger.error("Error searching in Qdrant: %s", str(e))
            return []


# Global singletons
neo4j_service = Neo4jGraphService()
qdrant_service = QdrantVectorService()
