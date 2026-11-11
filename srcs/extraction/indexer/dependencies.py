"""
File: dependencies.py
Purpose: File dependency tracking mixin for CodeIndex.
Category: Utility
Author: artdaq team
Depends: None
Exports: DependencyMixin
Complexity: Medium | Lines: 108
"""

import json
import sqlite3
from pathlib import Path
from .config import CodeIndexConfig

class DependencyMixin:
    config: CodeIndexConfig

    def get_file_dependencies(self, file_path: str) -> list[dict]:
        with sqlite3.connect(self.config.index_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute('''
                SELECT
                    fd.imported_path,
                    fd.import_type,
                    fd.is_system,
                    fd.line_number,
                    fd.imported_names_json,
                    resolved.path as resolved_path
                FROM file_dependencies fd
                JOIN files source ON fd.source_file_id = source.id
                LEFT JOIN files resolved ON fd.resolved_file_id = resolved.id
                WHERE source.path = ?
                ORDER BY fd.line_number
                ''', (file_path,))
            return [{'imported_path': row['imported_path'], 'import_type': row['import_type'], 'is_system': bool(row['is_system']), 'line_number': row['line_number'], 'imported_names': json.loads(row['imported_names_json'] or '[]'), 'resolved_path': row['resolved_path']} for row in cursor.fetchall()]

    def get_dependents(self, file_path: str) -> list[dict]:
        with sqlite3.connect(self.config.index_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute('''
                SELECT DISTINCT
                    source.path as dependent_file,
                    fd.import_type,
                    fd.line_number
                FROM file_dependencies fd
                JOIN files source ON fd.source_file_id = source.id
                LEFT JOIN files resolved ON fd.resolved_file_id = resolved.id
                WHERE resolved.path = ?
                   OR fd.imported_path LIKE ?
                ORDER BY source.path
                ''', (file_path, f'%{Path(file_path).name}'))
            return [{'dependent_file': row['dependent_file'], 'import_type': row['import_type'], 'line_number': row['line_number']} for row in cursor.fetchall()]

    def resolve_references(self) -> int:
        resolved_count = 0
        with sqlite3.connect(self.config.index_path) as conn:
            cursor = conn.execute('''
                SELECT fc.id, fc.callee_name
                FROM function_calls fc
                WHERE fc.callee_function_id IS NULL
                ''')
            unresolved = cursor.fetchall()
            for call_id, callee_name in unresolved:
                cursor = conn.execute('SELECT id FROM functions WHERE name = ? LIMIT 1', (callee_name,))
                row = cursor.fetchone()
                if row:
                    conn.execute('UPDATE function_calls SET callee_function_id = ? WHERE id = ?', (row[0], call_id))
                    resolved_count += 1
            cursor = conn.execute('''
                SELECT fd.id, fd.imported_path
                FROM file_dependencies fd
                WHERE fd.resolved_file_id IS NULL AND fd.is_system = FALSE
                ''')
            unresolved_deps = cursor.fetchall()
            for dep_id, imported_path in unresolved_deps:
                cursor = conn.execute('SELECT id FROM files WHERE path LIKE ? LIMIT 1', (f'%{imported_path}',))
                row = cursor.fetchone()
                if row:
                    conn.execute('UPDATE file_dependencies SET resolved_file_id = ? WHERE id = ?', (row[0], dep_id))
                    resolved_count += 1
            conn.commit()
        return resolved_count

    def mark_stale_files(self) -> int:
        stale_count = 0
        with sqlite3.connect(self.config.index_path) as conn:
            cursor = conn.execute('''
                SELECT DISTINCT source.id
                FROM files source
                JOIN file_dependencies fd ON fd.source_file_id = source.id
                JOIN files resolved ON fd.resolved_file_id = resolved.id
                WHERE source.is_stale = FALSE
                  AND resolved.indexed_at > source.indexed_at
                ''')
            stale_ids = [row[0] for row in cursor.fetchall()]
            if stale_ids:
                placeholders = ','.join('?' * len(stale_ids))
                conn.execute(f'UPDATE files SET is_stale = TRUE WHERE id IN ({placeholders})', stale_ids)
                stale_count = len(stale_ids)
                conn.commit()
        return stale_count

    def get_affected_files(self, changed_file: str) -> list[str]:
        affected: set[str] = set()

        def collect_dependents(file_path: str, visited: set) -> None:
            if file_path in visited:
                return
            visited.add(file_path)
            dependents = self.get_dependents(file_path)
            for dep in dependents:
                dep_file = dep['dependent_file']
                if dep_file not in affected:
                    affected.add(dep_file)
                    collect_dependents(dep_file, visited)
        collect_dependents(changed_file, set())
        return list(affected)