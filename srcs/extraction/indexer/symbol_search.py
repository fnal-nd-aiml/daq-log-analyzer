"""
File: symbol_search.py
Purpose: Symbol search mixin for CodeIndex.
Category: Utility
Author: artdaq team
Depends: None
Exports: SymbolSearchMixin
Complexity: Low | Lines: 62
"""

import json
import sqlite3
from pathlib import Path
from ..extractor import ClassInfo, FunctionInfo
from .config import CodeIndexConfig

class SymbolSearchMixin:
    config: CodeIndexConfig

    def find_function(self, name: str, file_filter: str | None=None) -> list[FunctionInfo]:
        with sqlite3.connect(self.config.index_path) as conn:
            conn.row_factory = sqlite3.Row
            if file_filter:
                cursor = conn.execute('''
                    SELECT f.*, files.path FROM functions f
                    JOIN files ON f.file_id = files.id
                    WHERE f.name LIKE ? AND files.path LIKE ?
                    ''', (name, f'%{file_filter}%'))
            else:
                cursor = conn.execute('''
                    SELECT f.*, files.path FROM functions f
                    JOIN files ON f.file_id = files.id
                    WHERE f.name LIKE ?
                    ''', (name,))
            results = []
            for row in cursor.fetchall():
                results.append(FunctionInfo(name=row['name'], file_path=Path(row['path']), start_line=row['start_line'], end_line=row['end_line'], signature=row['signature'] or '', return_type=row['return_type'] or '', parameters=json.loads(row['parameters_json'] or '[]'), class_name=row['class_name'], modifiers=json.loads(row['modifiers_json'] or '[]'), docstring=row['docstring']))
            return results

    def find_class(self, name: str) -> list[ClassInfo]:
        with sqlite3.connect(self.config.index_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute('''
                SELECT c.*, files.path FROM classes c
                JOIN files ON c.file_id = files.id
                WHERE c.name LIKE ?
                ''', (name,))
            results = []
            for row in cursor.fetchall():
                results.append(ClassInfo(name=row['name'], file_path=Path(row['path']), start_line=row['start_line'], end_line=row['end_line'], signature=row['signature'] or '', base_classes=json.loads(row['base_classes_json'] or '[]'), methods=json.loads(row['methods_json'] or '[]')))
            return results

    def search_symbols(self, query: str, symbol_type: str | None=None) -> list[dict]:
        with sqlite3.connect(self.config.index_path) as conn:
            conn.row_factory = sqlite3.Row
            if symbol_type:
                cursor = conn.execute('''
                    SELECT s.*, files.path FROM symbols s
                    JOIN files ON s.file_id = files.id
                    WHERE s.name LIKE ? AND s.symbol_type = ?
                    ORDER BY s.name
                    LIMIT 100
                    ''', (query, symbol_type))
            else:
                cursor = conn.execute('''
                    SELECT s.*, files.path FROM symbols s
                    JOIN files ON s.file_id = files.id
                    WHERE s.name LIKE ?
                    ORDER BY s.name
                    LIMIT 100
                    ''', (query,))
            return [{'name': row['name'], 'type': row['symbol_type'], 'file': row['path'], 'line': row['line'], 'context': row['context']} for row in cursor.fetchall()]