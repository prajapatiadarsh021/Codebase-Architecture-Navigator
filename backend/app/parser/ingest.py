import os
import logging
from typing import Dict, List, Any
from app.parser.ast_parser import CodebaseASTParser
from app.core.database import neo4j_service, qdrant_service

logger = logging.getLogger("ingest_service")
logger.setLevel(logging.INFO)

class CodebaseIngestService:
    def __init__(self):
        self.parser = CodebaseASTParser()

    def ingest_directory(self, root_dir: str, clear_existing: bool = True) -> Dict[str, Any]:
        """
        Recursively scans root_dir, parses ASTs, updates Neo4j graph and Qdrant vector index.
        """
        if clear_existing:
            neo4j_service.clear()
            qdrant_service.clear()

        if not os.path.exists(root_dir):
            raise FileNotFoundError(f"Path does not exist: {root_dir}")

        parsed_files: List[Dict[str, Any]] = []
        
        for dirpath, dirnames, filenames in os.walk(root_dir):
            # Exclude vendor, cache, and hidden directories
            dirnames[:] = [d for d in dirnames if d not in {".git", "__pycache__", "node_modules", ".venv", "venv", ".idea", "dist", "build"}]
            
            for fname in filenames:
                if fname.endswith(".py"):
                    full_path = os.path.join(dirpath, fname)
                    rel_path = os.path.relpath(full_path, root_dir).replace("\\", "/")
                    try:
                        with open(full_path, "rb") as f:
                            content = f.read()
                        parsed = self.parser.parse_source_code(content, rel_path)
                        parsed_files.append(parsed)
                    except Exception as e:
                        logger.warning("Error parsing %s: %s", full_path, str(e))

        # Index nodes into Neo4j and Qdrant
        all_functions_by_name: Dict[str, List[str]] = {}
        all_classes_by_name: Dict[str, str] = {}

        for pf in parsed_files:
            file_path = pf["file_path"]
            file_id = f"file::{file_path}"
            
            # File node
            neo4j_service.upsert_node(file_id, "File", {
                "name": os.path.basename(file_path),
                "file": file_path,
                "path": file_path
            })

            # Classes
            for cls in pf["classes"]:
                all_classes_by_name[cls["name"]] = cls["id"]
                neo4j_service.upsert_node(cls["id"], "Class", {
                    "name": cls["name"],
                    "file": file_path,
                    "docstring": cls["docstring"]
                })
                # File CONTAINS Class
                neo4j_service.add_relationship(file_id, cls["id"], "CONTAINS")
                
                # Qdrant vector index
                qdrant_service.upsert_symbol(
                    symbol_id=cls["id"],
                    name=cls["name"],
                    symbol_type="Class",
                    file_path=file_path,
                    signature=f"class {cls['name']}",
                    docstring=cls["docstring"]
                )

            # Functions
            for fn in pf["functions"]:
                short = fn["short_name"]
                if short not in all_functions_by_name:
                    all_functions_by_name[short] = []
                all_functions_by_name[short].append(fn["id"])

                neo4j_service.upsert_node(fn["id"], "Function", {
                    "name": fn["name"],
                    "file": file_path,
                    "signature": fn["signature"],
                    "docstring": fn["docstring"]
                })

                if fn["parent_class"]:
                    class_id = f"{file_path}::{fn['parent_class']}"
                    neo4j_service.add_relationship(class_id, fn["id"], "CONTAINS")
                else:
                    neo4j_service.add_relationship(file_id, fn["id"], "CONTAINS")

                # Qdrant vector index
                qdrant_service.upsert_symbol(
                    symbol_id=fn["id"],
                    name=fn["name"],
                    symbol_type="Function",
                    file_path=file_path,
                    signature=fn["signature"],
                    docstring=fn["docstring"]
                )

            # File Imports
            for imp in pf["imports"]:
                mod = imp.get("module") or ""
                # Connect import to file if internal file exists
                possible_file_ids = [
                    f"file::{mod}.py",
                    f"file::{mod.replace('.', '/')}.py",
                    f"file::{mod}/__init__.py"
                ]
                for p_id in possible_file_ids:
                    if p_id in neo4j_service._in_memory_nodes:
                        neo4j_service.add_relationship(file_id, p_id, "IMPORTS")

        # Second pass: Connect Function CALLS edges
        for pf in parsed_files:
            for call in pf["calls"]:
                caller_id = call["caller_id"]
                target_name = call["target_name"]
                
                # Match targets
                if target_name in all_functions_by_name:
                    for target_id in all_functions_by_name[target_name]:
                        if target_id != caller_id:
                            neo4j_service.add_relationship(caller_id, target_id, "CALLS", {"line": call["line"]})
                elif target_name in all_classes_by_name:
                    target_cls_id = all_classes_by_name[target_name]
                    neo4j_service.add_relationship(caller_id, target_cls_id, "CALLS", {"line": call["line"]})

        stats = {
            "files_indexed": len(parsed_files),
            "classes_indexed": len(all_classes_by_name),
            "functions_indexed": sum(len(pf["functions"]) for pf in parsed_files),
            "calls_indexed": sum(len(pf["calls"]) for pf in parsed_files),
            "nodes_total": len(neo4j_service._in_memory_nodes),
            "edges_total": len(neo4j_service._in_memory_edges)
        }
        logger.info("Ingestion completed: %s", str(stats))
        return stats

ingest_service = CodebaseIngestService()
