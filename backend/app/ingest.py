import os
os.environ["GIT_PYTHON_REFRESH"] = "quiet"

import io
import re
import shutil
import tempfile
import logging
import zipfile
import urllib.request
from typing import Dict, List, Any, Optional

try:
    import git
except Exception:
    git = None

from dotenv import load_dotenv

from app.core.config import settings
from app.core.database import neo4j_service, qdrant_service
from app.parser.ast_parser import CodebaseASTParser

# Ensure .env is loaded
load_dotenv()

logger = logging.getLogger("ingest")
logger.setLevel(logging.INFO)

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

def download_github_zip(git_url: str) -> Optional[str]:
    """
    Downloads and extracts a public GitHub repository without requiring git binary.
    Works in serverless environments like Vercel.
    """
    match = re.search(r"github\.com[/:]([\w.-]+)/([\w.-]+?)(?:\.git)?(?:/|$)", git_url)
    if not match:
        return None
    owner, repo = match.group(1), match.group(2)
    clean_name = re.sub(r"[^a-zA-Z0-9_-]", "_", f"{owner}_{repo}")
    target_dir = os.path.join(tempfile.gettempdir(), f"navigator_zip_{clean_name}")

    if os.path.exists(target_dir):
        try:
            shutil.rmtree(target_dir, ignore_errors=True)
        except Exception:
            pass

    os.makedirs(target_dir, exist_ok=True)
    zip_urls = [
        f"https://api.github.com/repos/{owner}/{repo}/zipball",
        f"https://github.com/{owner}/{repo}/archive/refs/heads/main.zip",
        f"https://github.com/{owner}/{repo}/archive/refs/heads/master.zip"
    ]

    for z_url in zip_urls:
        try:
            logger.info("Downloading GitHub zip: %s", z_url)
            req = urllib.request.Request(
                z_url,
                headers={"User-Agent": "Codebase-Architecture-Navigator", "Accept": "application/vnd.github.v3+json"}
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                if resp.status == 200:
                    zip_bytes = resp.read()
                    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                        zf.extractall(target_dir)

                    items = os.listdir(target_dir)
                    if len(items) == 1 and os.path.isdir(os.path.join(target_dir, items[0])):
                        extracted_root = os.path.join(target_dir, items[0])
                    else:
                        extracted_root = target_dir
                    logger.info("Successfully extracted GitHub repo to %s", extracted_root)
                    return extracted_root
        except Exception as e:
            logger.warning("GitHub zip download failed for %s: %s", z_url, str(e))

    return None

def clone_with_git(git_url: str) -> str:
    """
    Fallback to GitPython clone if git binary is present.
    """
    url = git_url.strip()
    if not url.startswith("http://") and not url.startswith("https://") and not url.startswith("git@"):
        url = "https://" + url

    repo_name_match = re.search(r"([^/]+?)(?:\.git)?$", url)
    repo_name = repo_name_match.group(1) if repo_name_match else "cloned_repo"
    clean_name = re.sub(r"[^a-zA-Z0-9_-]", "_", repo_name)
    target_dir = os.path.join(tempfile.gettempdir(), f"navigator_repo_{clean_name}")

    if os.path.exists(target_dir):
        def handle_remove_readonly(func, path, exc):
            import stat
            try:
                os.chmod(path, stat.S_IWRITE)
                func(path)
            except Exception:
                pass
        try:
            shutil.rmtree(target_dir, onerror=handle_remove_readonly)
        except Exception:
            import time
            target_dir = os.path.join(tempfile.gettempdir(), f"navigator_repo_{clean_name}_{int(time.time())}")

    try:
        if git is None:
            raise RuntimeError("Git binary or GitPython is not available on this server environment.")
        logger.info("GitPython: Cloning repository from %s into %s", url, target_dir)
        git.Repo.clone_from(url, target_dir, depth=1)
        return target_dir
    except Exception as e:
        logger.error("Git clone failed: %s", str(e))
        raise ValueError(f"Git clone failed: {str(e)}")

def fetch_or_clone_repository(git_url: str) -> str:
    """
    Fetches a repository using pure HTTP zipball download for GitHub (zero git dependencies),
    or falls back to git clone if available.
    """
    if "github.com" in git_url.lower():
        extracted = download_github_zip(git_url)
        if extracted:
            return extracted

    return clone_with_git(git_url)

class CodebaseIngestService:
    def __init__(self):
        self.parser = CodebaseASTParser()
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "").strip()
        self._embeddings_client = None
        self._init_gemini_embeddings()

    def _init_gemini_embeddings(self):
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if self.gemini_api_key:
            try:
                from langchain_google_genai import GoogleGenerativeAIEmbeddings
                self._embeddings_client = GoogleGenerativeAIEmbeddings(
                    model="models/text-embedding-004",
                    google_api_key=self.gemini_api_key
                )
                logger.info("Initialized Google Gemini text-embedding-004 embeddings client.")
            except Exception as e:
                logger.warning("Could not initialize Gemini embeddings client: %s. Using fallback.", str(e))
                self._embeddings_client = None
        else:
            logger.info("GEMINI_API_KEY not configured. Using deterministic 768-dim fallback embeddings.")
            self._embeddings_client = None

    def ingest_repository(self, target_input: str, clear_existing: bool = True) -> Dict[str, Any]:
        """
        Ingests codebase from a GitHub URL or local directory.
        1. Downloads or clones repository.
        2. Parses Python, JavaScript, and TypeScript files into AST.
        3. Populates Neo4j graph nodes and directed relationships.
        4. Generates Gemini text-embedding-004 embeddings and indexes into Qdrant.
        """
        raw_target = target_input.strip()
        if is_git_url(raw_target):
            work_dir = fetch_or_clone_repository(raw_target)
        else:
            work_dir = raw_target

        if not os.path.exists(work_dir):
            raise FileNotFoundError(f"Target directory does not exist: {work_dir}")

        if clear_existing:
            neo4j_service.clear()
            qdrant_service.clear()

        # Re-check API key in case it was added to .env
        self._init_gemini_embeddings()

        parsed_files: List[Dict[str, Any]] = []
        supported_exts = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}
        ignored_dirs = {
            ".git", "__pycache__", "node_modules", ".venv", "venv", ".idea", 
            "dist", "build", ".next", ".vscode", "coverage", "android", "gradle"
        }

        for dirpath, dirnames, filenames in os.walk(work_dir):
            dirnames[:] = [d for d in dirnames if d.lower() not in ignored_dirs]

            for fname in filenames:
                _, ext = os.path.splitext(fname)
                if ext.lower() in supported_exts:
                    full_path = os.path.join(dirpath, fname)
                    rel_path = os.path.relpath(full_path, work_dir).replace("\\", "/")
                    try:
                        with open(full_path, "rb") as f:
                            content = f.read()
                        parsed = self.parser.parse_source_code(content, rel_path)
                        parsed_files.append(parsed)
                    except Exception as e:
                        logger.warning("Error parsing %s: %s", full_path, str(e))

        if not parsed_files:
            raise ValueError(
                f"No supported code files found in repository. "
                "Supported formats: Python (.py), JavaScript (.js, .jsx), TypeScript (.ts, .tsx)."
            )

        all_functions_by_name: Dict[str, List[str]] = {}
        all_classes_by_name: Dict[str, str] = {}
        symbols_to_embed: List[Dict[str, Any]] = []

        # Pass 1: Build Neo4j nodes and collect symbols for embedding
        for pf in parsed_files:
            file_path = pf["file_path"]
            file_id = f"file::{file_path}"

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
                neo4j_service.add_relationship(file_id, cls["id"], "CONTAINS")

                symbols_to_embed.append({
                    "symbol_id": cls["id"],
                    "name": cls["name"],
                    "type": "Class",
                    "file": file_path,
                    "signature": f"class {cls['name']}",
                    "docstring": cls["docstring"],
                    "code_chunk": f"class {cls['name']}:\n    \"\"\"{cls['docstring']}\"\"\"",
                    "summary_text": f"Class {cls['name']} in {file_path}. {cls['docstring'] or 'Class declaration.'}"
                })

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

                symbols_to_embed.append({
                    "symbol_id": fn["id"],
                    "name": fn["name"],
                    "type": "Function",
                    "file": file_path,
                    "signature": fn["signature"],
                    "docstring": fn["docstring"],
                    "code_chunk": f"def {fn['signature']}:\n    \"\"\"{fn['docstring']}\"\"\"",
                    "summary_text": f"Function {fn['name']} in {file_path}. Signature: {fn['signature']}. {fn['docstring'] or 'Callable definition.'}"
                })

            # Module Imports
            for imp in pf["imports"]:
                mod = imp.get("module") or ""
                clean_mod = mod.lstrip("./").lstrip("@/").replace("\\", "/")
                possible_file_ids = [
                    f"file::{mod}",
                    f"file::{mod}.py",
                    f"file::{clean_mod}",
                    f"file::{clean_mod}.ts",
                    f"file::{clean_mod}.tsx",
                    f"file::{clean_mod}.js",
                    f"file::{clean_mod}.jsx",
                    f"file::{clean_mod}/index.ts",
                    f"file::{clean_mod}/index.tsx",
                    f"file::{clean_mod}/index.js",
                    f"file::{mod.replace('.', '/')}.py",
                    f"file::{mod}/__init__.py"
                ]
                for p_id in possible_file_ids:
                    if p_id in neo4j_service._in_memory_nodes:
                        neo4j_service.add_relationship(file_id, p_id, "IMPORTS")
                        break

        # Pass 2: Connect CALLS relationships
        for pf in parsed_files:
            for call in pf["calls"]:
                caller_id = call["caller_id"]
                target_name = call["target_name"]

                if target_name in all_functions_by_name:
                    for target_id in all_functions_by_name[target_name]:
                        if target_id != caller_id:
                            neo4j_service.add_relationship(caller_id, target_id, "CALLS", {"line": call["line"]})
                elif target_name in all_classes_by_name:
                    target_cls_id = all_classes_by_name[target_name]
                    neo4j_service.add_relationship(caller_id, target_cls_id, "CALLS", {"line": call["line"]})

        # Pass 3: Compute embeddings (Google Gemini text-embedding-004 or fallback) and upsert into Qdrant
        logger.info("Computing vector embeddings for %d codebase symbols...", len(symbols_to_embed))
        vectors: List[Optional[List[float]]] = [None] * len(symbols_to_embed)

        if self._embeddings_client and symbols_to_embed:
            try:
                texts = [s["summary_text"] for s in symbols_to_embed]
                # Embed in batches of 32 to respect API rate limits
                batch_size = 32
                computed_vectors = []
                for i in range(0, len(texts), batch_size):
                    batch = texts[i:i + batch_size]
                    batch_vecs = self._embeddings_client.embed_documents(batch)
                    computed_vectors.extend(batch_vecs)
                vectors = computed_vectors
                logger.info("Successfully generated %d Gemini neural embeddings.", len(vectors))
            except Exception as e:
                logger.warning("Gemini API embedding generation failed: %s. Using fallback vectorizer.", str(e))
                vectors = [None] * len(symbols_to_embed)

        for idx, sym in enumerate(symbols_to_embed):
            custom_vec = vectors[idx] if idx < len(vectors) else None
            qdrant_service.upsert_symbol(
                symbol_id=sym["symbol_id"],
                name=sym["name"],
                symbol_type=sym["type"],
                file_path=sym["file"],
                signature=sym["signature"],
                docstring=sym["docstring"],
                code_snippet=sym["code_chunk"],
                custom_vector=custom_vec,
                custom_summary=sym["summary_text"]
            )

        stats = {
            "files_indexed": len(parsed_files),
            "classes_indexed": len(all_classes_by_name),
            "functions_indexed": sum(len(pf["functions"]) for pf in parsed_files),
            "calls_indexed": sum(len(pf["calls"]) for pf in parsed_files),
            "nodes_total": len(neo4j_service._in_memory_nodes),
            "edges_total": len(neo4j_service._in_memory_edges),
            "embeddings_model": "models/text-embedding-004" if (self._embeddings_client and vectors and vectors[0] is not None) else "deterministic-768-dim"
        }
        logger.info("Ingestion completed successfully: %s", str(stats))
        return stats

ingest_service = CodebaseIngestService()
