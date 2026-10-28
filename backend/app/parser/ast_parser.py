import os
import re
from typing import List, Dict, Any, Optional
import tree_sitter
from tree_sitter import Language, Parser
import tree_sitter_python

class CodebaseASTParser:
    def __init__(self):
        self.language = Language(tree_sitter_python.language())
        self.parser = Parser(self.language)

    def parse_source_code(self, source_bytes: bytes, file_path: str) -> Dict[str, Any]:
        """
        Parses source code based on file extension.
        - Python (.py) via Tree-sitter
        - JavaScript / TypeScript (.js, .jsx, .ts, .tsx, .mjs, .cjs) via AST/regex extractor
        """
        _, ext = os.path.splitext(file_path.lower())
        if ext in (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"):
            return self._parse_javascript_source(source_bytes, file_path)

        tree = self.parser.parse(source_bytes)
        root_node = tree.root_node
        
        file_info = {
            "file_path": file_path,
            "classes": [],
            "functions": [],
            "imports": [],
            "calls": []
        }
        
        self._traverse_node(root_node, source_bytes, file_info, parent_class=None, parent_function=None)
        return file_info

    def _parse_javascript_source(self, source_bytes: bytes, file_path: str) -> Dict[str, Any]:
        """
        Lightweight AST & regex extractor for JS, JSX, TS, and TSX files.
        Extracts classes, named functions, React arrow components, imports, and calls.
        """
        text = source_bytes.decode("utf-8", errors="replace")
        
        file_info = {
            "file_path": file_path,
            "classes": [],
            "functions": [],
            "imports": [],
            "calls": []
        }

        # 1. Classes / Interfaces
        class_regex = re.compile(r'(?:export\s+(?:default\s+)?)?(?:class|interface)\s+([a-zA-Z0-9_$]+)', re.MULTILINE)
        for match in class_regex.finditer(text):
            cls_name = match.group(1)
            line_num = text[:match.start()].count("\n") + 1
            cls_id = f"{file_path}::{cls_name}"
            file_info["classes"].append({
                "id": cls_id,
                "name": cls_name,
                "file": file_path,
                "docstring": f"Class definition for {cls_name}",
                "start_line": line_num,
                "end_line": line_num
            })

        # 2. Named Functions & React Components
        fn_regex = re.compile(
            r'(?:export\s+(?:default\s+)?)?(?:async\s+)?function\s*([a-zA-Z0-9_$]+)\s*\(([^)]*)\)',
            re.MULTILINE
        )
        for match in fn_regex.finditer(text):
            fn_name = match.group(1)
            params = match.group(2).strip()
            line_num = text[:match.start()].count("\n") + 1
            func_id = f"{file_path}::{fn_name}"
            file_info["functions"].append({
                "id": func_id,
                "name": fn_name,
                "short_name": fn_name,
                "parent_class": None,
                "file": file_path,
                "signature": f"{fn_name}({params})",
                "docstring": f"Function {fn_name}",
                "start_line": line_num,
                "end_line": line_num
            })

        # 3. Arrow & Variable Functions (e.g. const HotelCard = (...) => ...)
        arrow_regex = re.compile(
            r'(?:export\s+)?(?:const|let|var)\s+([a-zA-Z0-9_$]+)\s*=\s*(?:async\s*)?(?:\(([^)]*)\)|([a-zA-Z0-9_$]+))\s*(?::\s*[^=]+)?\s*=>',
            re.MULTILINE
        )
        for match in arrow_regex.finditer(text):
            fn_name = match.group(1)
            params = (match.group(2) or match.group(3) or "").strip()
            line_num = text[:match.start()].count("\n") + 1
            func_id = f"{file_path}::{fn_name}"
            if not any(f["id"] == func_id for f in file_info["functions"]):
                file_info["functions"].append({
                    "id": func_id,
                    "name": fn_name,
                    "short_name": fn_name,
                    "parent_class": None,
                    "file": file_path,
                    "signature": f"{fn_name}({params})",
                    "docstring": f"Component or Handler {fn_name}",
                    "start_line": line_num,
                    "end_line": line_num
                })

        # 4. Imports
        imp_regex = re.compile(
            r'import\s+(?:(?:[\w*\s{},$]+)\s+from\s+)?[\'"]([^\'"]+)[\'"]',
            re.MULTILINE
        )
        for match in imp_regex.finditer(text):
            mod_path = match.group(1)
            line_num = text[:match.start()].count("\n") + 1
            file_info["imports"].append({
                "module": mod_path,
                "line": line_num
            })

        # 5. Calls
        call_regex = re.compile(r'\b([a-zA-Z0-9_$]{2,})\s*\(', re.MULTILINE)
        reserved_words = {"if", "for", "while", "switch", "catch", "return", "function", "import", "export", "typeof", "sizeof", "new", "throw", "require", "console"}
        for match in call_regex.finditer(text):
            target = match.group(1)
            if target in reserved_words:
                continue
            line_num = text[:match.start()].count("\n") + 1
            caller_id = f"{file_path}::file_scope"
            for fn in file_info["functions"]:
                if fn["start_line"] <= line_num:
                    caller_id = fn["id"]

            file_info["calls"].append({
                "caller_id": caller_id,
                "target_name": target,
                "full_call": target,
                "line": line_num
            })

        return file_info

    def _get_node_text(self, node: tree_sitter.Node, source_bytes: bytes) -> str:
        return source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

    def _extract_docstring(self, body_node: Optional[tree_sitter.Node], source_bytes: bytes) -> str:
        if not body_node:
            return ""
        for child in body_node.children:
            if child.type == "expression_statement":
                for sub in child.children:
                    if sub.type == "string":
                        raw = self._get_node_text(sub, source_bytes)
                        return raw.strip("\"' \n\t")
            elif child.type not in ("comment", "\n"):
                break
        return ""

    def _traverse_node(
        self,
        node: tree_sitter.Node,
        source_bytes: bytes,
        file_info: Dict[str, Any],
        parent_class: Optional[str] = None,
        parent_function: Optional[str] = None
    ):
        if node.type == "import_statement":
            for child in node.children:
                if child.type == "dotted_name":
                    file_info["imports"].append({
                        "module": self._get_node_text(child, source_bytes),
                        "line": node.start_point[0] + 1
                    })
            return

        if node.type == "import_from_statement":
            mod_name = None
            for child in node.children:
                if child.type == "dotted_name":
                    mod_name = self._get_node_text(child, source_bytes)
                    break
                elif child.type == "relative_import":
                    mod_name = self._get_node_text(child, source_bytes)
                    break
            if mod_name:
                file_info["imports"].append({
                    "module": mod_name,
                    "line": node.start_point[0] + 1
                })
            return

        if node.type == "class_definition":
            name_node = node.child_by_field_name("name")
            class_name = self._get_node_text(name_node, source_bytes) if name_node else "AnonymousClass"
            class_id = f"{file_info['file_path']}::{class_name}"
            
            body_node = node.child_by_field_name("body")
            docstring = self._extract_docstring(body_node, source_bytes)

            file_info["classes"].append({
                "id": class_id,
                "name": class_name,
                "file": file_info["file_path"],
                "docstring": docstring,
                "start_line": node.start_point[0] + 1,
                "end_line": node.end_point[0] + 1
            })

            if body_node:
                for child in body_node.children:
                    self._traverse_node(child, source_bytes, file_info, parent_class=class_name, parent_function=None)
            return

        if node.type == "function_definition":
            name_node = node.child_by_field_name("name")
            func_name = self._get_node_text(name_node, source_bytes) if name_node else "anonymous"
            params_node = node.child_by_field_name("parameters")
            signature = self._get_node_text(params_node, source_bytes) if params_node else "()"
            
            body_node = node.child_by_field_name("body")
            if not body_node:
                for child in node.children:
                    if child.type == "block":
                        body_node = child

            docstring = self._extract_docstring(body_node, source_bytes)
            
            qualified_name = f"{parent_class}.{func_name}" if parent_class else func_name
            func_id = f"{file_info['file_path']}::{qualified_name}"
            
            file_info["functions"].append({
                "id": func_id,
                "name": qualified_name,
                "short_name": func_name,
                "parent_class": parent_class,
                "file": file_info["file_path"],
                "signature": f"{func_name}{signature}",
                "docstring": docstring,
                "start_line": node.start_point[0] + 1,
                "end_line": node.end_point[0] + 1
            })

            # Search calls inside function body
            if body_node:
                self._extract_calls(body_node, source_bytes, func_id, file_info)
            return

        for child in node.children:
            self._traverse_node(child, source_bytes, file_info, parent_class, parent_function)

    def _extract_calls(self, node: tree_sitter.Node, source_bytes: bytes, caller_id: str, file_info: Dict[str, Any]):
        if node.type == "call":
            func_child = node.child_by_field_name("function") or (node.children[0] if node.children else None)
            if func_child:
                call_name = self._get_node_text(func_child, source_bytes)
                clean_target = call_name.split(".")[-1]
                file_info["calls"].append({
                    "caller_id": caller_id,
                    "target_name": clean_target,
                    "full_call": call_name,
                    "line": node.start_point[0] + 1
                })
        for child in node.children:
            self._extract_calls(child, source_bytes, caller_id, file_info)

    def parse_file(self, file_path: str) -> Dict[str, Any]:
        with open(file_path, "rb") as f:
            content = f.read()
        return self.parse_source_code(content, file_path)
