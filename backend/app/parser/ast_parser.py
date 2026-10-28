import os
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
        Parses Python source code and extracts classes, functions, calls, and imports.
        """
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
            # import math, os
            text = self._get_node_text(node, source_bytes)
            for child in node.children:
                if child.type == "dotted_name":
                    file_info["imports"].append({
                        "module": self._get_node_text(child, source_bytes),
                        "statement": text.strip()
                    })

        elif node.type == "import_from_statement":
            # from x import y
            module_name = ""
            imported_names = []
            for child in node.children:
                if child.type == "dotted_name" or child.type == "relative_import":
                    if not module_name:
                        module_name = self._get_node_text(child, source_bytes)
                elif child.type == "dotted_name" or child.type == "identifier":
                    imported_names.append(self._get_node_text(child, source_bytes))
            file_info["imports"].append({
                "module": module_name,
                "names": imported_names,
                "statement": self._get_node_text(node, source_bytes).strip()
            })

        elif node.type == "class_definition":
            class_name = ""
            body_node = None
            for child in node.children:
                if child.type == "identifier":
                    class_name = self._get_node_text(child, source_bytes)
                elif child.type == "block":
                    body_node = child

            docstring = self._extract_docstring(body_node, source_bytes)
            class_id = f"{file_info['file_path']}::{class_name}"
            
            file_info["classes"].append({
                "id": class_id,
                "name": class_name,
                "file": file_info["file_path"],
                "docstring": docstring,
                "start_line": node.start_point[0] + 1,
                "end_line": node.end_point[0] + 1
            })

            # Traverse class body with parent_class set
            if body_node:
                for child in body_node.children:
                    self._traverse_node(child, source_bytes, file_info, parent_class=class_name, parent_function=None)
            return

        elif node.type == "function_definition":
            func_name = ""
            signature = ""
            body_node = None
            params_node = None

            for child in node.children:
                if child.type == "identifier":
                    func_name = self._get_node_text(child, source_bytes)
                elif child.type == "parameters":
                    params_node = child
                    signature = self._get_node_text(child, source_bytes)
                elif child.type == "block":
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
                # Normalize call name (e.g. self.update_status -> update_status)
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
