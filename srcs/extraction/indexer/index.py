"""
File: index.py
Purpose: Core CodeIndex class for searchable code index.
Category: Utility
Author: artdaq team
Depends: None
Exports: CodeIndex
Complexity: Medium | Lines: 277
"""

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Callable
from ..extractor import CodeExtractor
from ..parser import CodeParser, ParsedNode
from .call_graph import CallGraphMixin
from .config import CodeIndexConfig
from .dependencies import DependencyMixin
from .symbol_search import SymbolSearchMixin
logger = logging.getLogger(__name__)

class CodeIndex(SymbolSearchMixin, CallGraphMixin, DependencyMixin):
    SCHEMA = """
    CREATE TABLE IF NOT EXISTS files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        path TEXT UNIQUE NOT NULL,
        language TEXT,
        last_modified REAL,
        indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        is_stale BOOLEAN DEFAULT FALSE,
        content_hash TEXT
    );

    CREATE TABLE IF NOT EXISTS functions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        file_id INTEGER REFERENCES files(id) ON DELETE CASCADE,
        start_line INTEGER,
        end_line INTEGER,
        signature TEXT,
        return_type TEXT,
        parameters_json TEXT,
        class_name TEXT,
        modifiers_json TEXT,
        docstring TEXT
    );

    CREATE TABLE IF NOT EXISTS classes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        file_id INTEGER REFERENCES files(id) ON DELETE CASCADE,
        start_line INTEGER,
        end_line INTEGER,
        signature TEXT,
        base_classes_json TEXT,
        methods_json TEXT
    );

    CREATE TABLE IF NOT EXISTS symbols (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        symbol_type TEXT,  -- function, class, variable
        file_id INTEGER REFERENCES files(id) ON DELETE CASCADE,
        line INTEGER,
        context TEXT
    );

    CREATE TABLE IF NOT EXISTS function_calls (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        caller_function_id INTEGER REFERENCES functions(id) ON DELETE CASCADE,
        caller_file_id INTEGER REFERENCES files(id) ON DELETE CASCADE,
        callee_name TEXT NOT NULL,
        callee_function_id INTEGER REFERENCES functions(id),
        call_line INTEGER,
        call_type TEXT DEFAULT 'direct'
    );

    CREATE TABLE IF NOT EXISTS file_dependencies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_file_id INTEGER REFERENCES files(id) ON DELETE CASCADE,
        imported_path TEXT NOT NULL,
        resolved_file_id INTEGER REFERENCES files(id),
        import_type TEXT DEFAULT 'include',
        is_system BOOLEAN DEFAULT FALSE,
        line_number INTEGER,
        imported_names_json TEXT
    );

    CREATE INDEX IF NOT EXISTS idx_functions_name ON functions(name);
    CREATE INDEX IF NOT EXISTS idx_functions_class ON functions(class_name);
    CREATE INDEX IF NOT EXISTS idx_functions_file ON functions(file_id);
    CREATE INDEX IF NOT EXISTS idx_classes_name ON classes(name);
    CREATE INDEX IF NOT EXISTS idx_classes_file ON classes(file_id);
    CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name);
    CREATE INDEX IF NOT EXISTS idx_symbols_file ON symbols(file_id);
    CREATE INDEX IF NOT EXISTS idx_files_path ON files(path);
    CREATE INDEX IF NOT EXISTS idx_files_stale ON files(is_stale);
    CREATE INDEX IF NOT EXISTS idx_calls_caller_func ON function_calls(caller_function_id);
    CREATE INDEX IF NOT EXISTS idx_calls_caller_file ON function_calls(caller_file_id);
    CREATE INDEX IF NOT EXISTS idx_calls_callee_name ON function_calls(callee_name);
    CREATE INDEX IF NOT EXISTS idx_calls_callee_func ON function_calls(callee_function_id);
    CREATE INDEX IF NOT EXISTS idx_deps_source ON file_dependencies(source_file_id);
    CREATE INDEX IF NOT EXISTS idx_deps_resolved ON file_dependencies(resolved_file_id);
    CREATE INDEX IF NOT EXISTS idx_deps_path ON file_dependencies(imported_path);
    """
    MIGRATION_SCHEMA = """
    -- Add new columns to files table if they don't exist
    ALTER TABLE files ADD COLUMN is_stale BOOLEAN DEFAULT FALSE;
    ALTER TABLE files ADD COLUMN content_hash TEXT;
    """

    def __init__(self, config: CodeIndexConfig):
        self.config = config
        self.config.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.parser = CodeParser()
        self.extractor = CodeExtractor(self.parser)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.config.index_path) as conn:
            conn.execute('PRAGMA foreign_keys = ON')
            conn.executescript(self.SCHEMA)
            self._migrate_db(conn)

    def _migrate_db(self, conn: sqlite3.Connection) -> None:
        cursor = conn.execute('PRAGMA table_info(files)')
        columns = {row[1] for row in cursor.fetchall()}
        if 'is_stale' not in columns:
            try:
                conn.execute('ALTER TABLE files ADD COLUMN is_stale BOOLEAN DEFAULT FALSE')
                logger.info('Added is_stale column to files table')
            except sqlite3.OperationalError:
                pass
        if 'content_hash' not in columns:
            try:
                conn.execute('ALTER TABLE files ADD COLUMN content_hash TEXT')
                logger.info('Added content_hash column to files table')
            except sqlite3.OperationalError:
                pass

    def build_index(self, progress_callback: Callable[[int, int, Path], None] | None=None) -> dict[str, Any]:
        stats: dict[str, Any] = {'files_indexed': 0, 'functions_found': 0, 'classes_found': 0, 'function_calls_found': 0, 'dependencies_found': 0, 'errors': []}
        files_to_index: list[Path] = []
        for root in self.config.source_roots:
            if not root.exists():
                continue
            for ext in self.config.extensions:
                files_to_index.extend(root.rglob(f'*{ext}'))
        filtered_files = []
        for file_path in files_to_index:
            excluded = False
            for pattern in self.config.exclude_patterns:
                if file_path.match(pattern):
                    excluded = True
                    break
            if not excluded:
                filtered_files.append(file_path)
        total = len(filtered_files)
        logger.info(f'Indexing {total} files...')
        with sqlite3.connect(self.config.index_path) as conn:
            conn.execute('PRAGMA foreign_keys = ON')
            conn.execute('DELETE FROM function_calls')
            conn.execute('DELETE FROM file_dependencies')
            conn.execute('DELETE FROM symbols')
            conn.execute('DELETE FROM functions')
            conn.execute('DELETE FROM classes')
            conn.execute('DELETE FROM files')
            for i, file_path in enumerate(filtered_files):
                if progress_callback:
                    progress_callback(i + 1, total, file_path)
                try:
                    self._index_file(conn, file_path, stats)
                except Exception as e:
                    logger.warning(f'Failed to index {file_path}: {e}')
                    stats['errors'].append(str(file_path))
            conn.commit()
        resolved = self.resolve_call_references()
        stats['call_references_resolved'] = resolved
        logger.info(f"Indexed {stats['files_indexed']} files, {stats['functions_found']} functions, {stats['classes_found']} classes, {stats['function_calls_found']} function calls, {stats['dependencies_found']} dependencies, {resolved} call references resolved")
        return stats

    def _index_file(self, conn: sqlite3.Connection, file_path: Path, stats: dict[str, Any]) -> None:
        mtime = file_path.stat().st_mtime
        cursor = conn.execute('SELECT id, last_modified FROM files WHERE path = ?', (str(file_path),))
        row = cursor.fetchone()
        if row and row[1] == mtime:
            return
        result = self.extractor.extract_from_file(file_path)
        language = CodeParser.LANGUAGE_EXTENSIONS.get(file_path.suffix.lower(), 'unknown')
        if row:
            file_id = row[0]
            conn.execute('UPDATE files SET last_modified = ?, indexed_at = CURRENT_TIMESTAMP, is_stale = FALSE WHERE id = ?', (mtime, file_id))
            conn.execute('DELETE FROM function_calls WHERE caller_file_id = ?', (file_id,))
            conn.execute('DELETE FROM file_dependencies WHERE source_file_id = ?', (file_id,))
            conn.execute('DELETE FROM functions WHERE file_id = ?', (file_id,))
            conn.execute('DELETE FROM classes WHERE file_id = ?', (file_id,))
            conn.execute('DELETE FROM symbols WHERE file_id = ?', (file_id,))
        else:
            cursor = conn.execute('INSERT INTO files (path, language, last_modified, is_stale) VALUES (?, ?, ?, FALSE)', (str(file_path), language, mtime))
            file_id = cursor.lastrowid
        for func in result.get('functions', []):
            conn.execute('''
                INSERT INTO functions (
                    name, file_id, start_line, end_line, signature,
                    return_type, parameters_json, class_name, modifiers_json, docstring
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (func.name, file_id, func.start_line, func.end_line, func.signature, func.return_type, json.dumps(func.parameters), func.class_name, json.dumps(func.modifiers), func.docstring))
            conn.execute('INSERT INTO symbols (name, symbol_type, file_id, line, context) VALUES (?, ?, ?, ?, ?)', (func.name, 'function', file_id, func.start_line, func.signature))
            stats['functions_found'] += 1
        for cls in result.get('classes', []):
            conn.execute('''
                INSERT INTO classes (
                    name, file_id, start_line, end_line, signature,
                    base_classes_json, methods_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (cls.name, file_id, cls.start_line, cls.end_line, cls.signature, json.dumps(cls.base_classes), json.dumps(cls.methods)))
            conn.execute('INSERT INTO symbols (name, symbol_type, file_id, line, context) VALUES (?, ?, ?, ?, ?)', (cls.name, 'class', file_id, cls.start_line, cls.signature))
            stats['classes_found'] += 1
        cursor = conn.execute('SELECT id, name, start_line FROM functions WHERE file_id = ?', (file_id,))
        func_map = {(row[1], row[2]): row[0] for row in cursor.fetchall()}
        parsed = self.parser.parse_file(file_path)
        func_nodes: dict[int, ParsedNode] = {}
        if parsed.root:
            for func_node in parsed.root.find_all('function_definition'):
                func_nodes[func_node.start_line] = func_node
        for func in result.get('functions', []):
            func_id = func_map.get((func.name, func.start_line))
            if func_id is None:
                continue
            matching_node = func_nodes.get(func.start_line)
            if matching_node:
                calls = self.extractor._extract_calls_from_node(matching_node, parsed.language)
                for callee_name, call_line, call_type in calls:
                    conn.execute('''
                        INSERT INTO function_calls (
                            caller_function_id, caller_file_id, callee_name,
                            call_line, call_type
                        ) VALUES (?, ?, ?, ?, ?)
                        ''', (func_id, file_id, callee_name, call_line, call_type))
                    stats['function_calls_found'] += 1
        for dep in result.get('dependencies', []):
            conn.execute('''
                INSERT INTO file_dependencies (
                    source_file_id, imported_path, import_type,
                    is_system, line_number, imported_names_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                ''', (file_id, dep.imported_path, dep.import_type, dep.is_system, dep.line_number, json.dumps(dep.imported_names)))
            stats['dependencies_found'] += 1
        stats['files_indexed'] += 1

    def get_function_source(self, name: str) -> str | None:
        functions = self.find_function(name)
        if not functions:
            return None
        func = functions[0]
        if not func.file_path.exists():
            return None
        lines = func.file_path.read_text().split('\n')
        return '\n'.join(lines[func.start_line - 1:func.end_line])

    def get_class_source(self, name: str) -> str | None:
        classes = self.find_class(name)
        if not classes:
            return None
        cls = classes[0]
        if not cls.file_path.exists():
            return None
        lines = cls.file_path.read_text().split('\n')
        return '\n'.join(lines[cls.start_line - 1:cls.end_line])

    def get_stats(self) -> dict[str, int]:
        with sqlite3.connect(self.config.index_path) as conn:
            cursor = conn.execute('SELECT COUNT(*) FROM files')
            files = cursor.fetchone()[0]
            cursor = conn.execute('SELECT COUNT(*) FROM functions')
            functions = cursor.fetchone()[0]
            cursor = conn.execute('SELECT COUNT(*) FROM classes')
            classes = cursor.fetchone()[0]
            cursor = conn.execute('SELECT COUNT(*) FROM symbols')
            symbols = cursor.fetchone()[0]
            cursor = conn.execute('SELECT COUNT(*) FROM function_calls')
            function_calls = cursor.fetchone()[0]
            cursor = conn.execute('SELECT COUNT(*) FROM file_dependencies')
            dependencies = cursor.fetchone()[0]
            return {'files': files, 'functions': functions, 'classes': classes, 'symbols': symbols, 'function_calls': function_calls, 'dependencies': dependencies}