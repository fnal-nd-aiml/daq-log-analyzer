"""
File: call_graph.py
Purpose: Call graph analysis mixin for CodeIndex.
Category: Utility
Author: artdaq team
Depends: None
Exports: CallGraphMixin
Complexity: Medium | Lines: 113
"""

import logging
import sqlite3
from .config import CodeIndexConfig
logger = logging.getLogger(__name__)

class CallGraphMixin:
    config: CodeIndexConfig

    def _extract_simple_name(self, qualified_name: str) -> str:
        if '::' in qualified_name:
            return qualified_name.split('::')[-1]
        return qualified_name

    def resolve_call_references(self) -> int:
        resolved = 0
        with sqlite3.connect(self.config.index_path) as conn:
            cursor = conn.execute('SELECT id, name FROM functions ORDER BY LENGTH(name) DESC')
            name_to_ids: dict[str, list[int]] = {}
            for row in cursor.fetchall():
                func_id, name = row
                simple_name = self._extract_simple_name(name)
                if simple_name not in name_to_ids:
                    name_to_ids[simple_name] = []
                name_to_ids[simple_name].append(func_id)
                if name != simple_name:
                    if name not in name_to_ids:
                        name_to_ids[name] = []
                    name_to_ids[name].append(func_id)
            cursor = conn.execute('''
                SELECT id, callee_name FROM function_calls
                WHERE callee_function_id IS NULL
                ''')
            calls_to_resolve = cursor.fetchall()
            for call_id, callee_name in calls_to_resolve:
                if callee_name in name_to_ids:
                    func_ids = name_to_ids[callee_name]
                    conn.execute('UPDATE function_calls SET callee_function_id = ? WHERE id = ?', (func_ids[0], call_id))
                    resolved += 1
                    continue
                simple_name = self._extract_simple_name(callee_name)
                if simple_name in name_to_ids:
                    func_ids = name_to_ids[simple_name]
                    conn.execute('UPDATE function_calls SET callee_function_id = ? WHERE id = ?', (func_ids[0], call_id))
                    resolved += 1
            conn.commit()
        logger.info(f'Resolved {resolved} call references')
        return resolved

    def get_callers(self, function_name: str) -> list[dict]:
        simple_name = self._extract_simple_name(function_name)
        with sqlite3.connect(self.config.index_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute('''
                SELECT id FROM functions
                WHERE name = ? OR name = ? OR name LIKE ?
                ''', (function_name, simple_name, f'%::{simple_name}'))
            target_func_ids = [row[0] for row in cursor.fetchall()]
            if target_func_ids:
                placeholders = ','.join(('?' for _ in target_func_ids))
                cursor = conn.execute(f'\n                    SELECT DISTINCT\n                        f.name as caller_name,\n                        f.signature as caller_signature,\n                        f.start_line as caller_line,\n                        files.path as caller_file,\n                        fc.call_line,\n                        fc.call_type\n                    FROM function_calls fc\n                    JOIN functions f ON fc.caller_function_id = f.id\n                    JOIN files ON f.file_id = files.id\n                    WHERE fc.callee_name = ?\n                       OR fc.callee_name = ?\n                       OR fc.callee_function_id IN ({placeholders})\n                    ORDER BY files.path, fc.call_line\n                    ', (function_name, simple_name, *target_func_ids))
            else:
                cursor = conn.execute('''
                    SELECT DISTINCT
                        f.name as caller_name,
                        f.signature as caller_signature,
                        f.start_line as caller_line,
                        files.path as caller_file,
                        fc.call_line,
                        fc.call_type
                    FROM function_calls fc
                    JOIN functions f ON fc.caller_function_id = f.id
                    JOIN files ON f.file_id = files.id
                    WHERE fc.callee_name = ? OR fc.callee_name = ?
                    ORDER BY files.path, fc.call_line
                    ''', (function_name, simple_name))
            return [{'caller_name': row['caller_name'], 'caller_signature': row['caller_signature'], 'caller_line': row['caller_line'], 'caller_file': row['caller_file'], 'call_line': row['call_line'], 'call_type': row['call_type']} for row in cursor.fetchall()]

    def get_callees(self, function_name: str) -> list[dict]:
        simple_name = self._extract_simple_name(function_name)
        with sqlite3.connect(self.config.index_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute('''
                SELECT DISTINCT
                    fc.callee_name,
                    fc.call_line,
                    fc.call_type,
                    files.path as caller_file,
                    callee_func.name as resolved_callee_name,
                    callee_files.path as callee_file
                FROM function_calls fc
                JOIN functions f ON fc.caller_function_id = f.id
                JOIN files ON f.file_id = files.id
                LEFT JOIN functions callee_func ON fc.callee_function_id = callee_func.id
                LEFT JOIN files callee_files ON callee_func.file_id = callee_files.id
                WHERE f.name = ? OR f.name = ? OR f.name LIKE ?
                ORDER BY fc.call_line
                ''', (function_name, simple_name, f'%::{simple_name}'))
            return [{'callee_name': row['callee_name'], 'call_line': row['call_line'], 'call_type': row['call_type'], 'caller_file': row['caller_file'], 'callee_file': row['callee_file'], 'resolved_name': row['resolved_callee_name']} for row in cursor.fetchall()]

    def get_call_chain(self, function_name: str, direction: str='callers', depth: int=3) -> dict:
        if depth <= 0:
            return {'name': function_name, 'children': []}
        if direction == 'callers':
            related = self.get_callers(function_name)
            related_names = {r['caller_name'] for r in related}
        else:
            related = self.get_callees(function_name)
            related_names = {r['callee_name'] for r in related}
        children = []
        for name in related_names:
            child = self.get_call_chain(name, direction, depth - 1)
            children.append(child)
        return {'name': function_name, 'children': children}