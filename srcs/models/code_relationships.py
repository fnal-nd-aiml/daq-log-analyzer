"""
File: code_relationships.py
Purpose: Data models for code relationships (call graphs and dependencies).
Category: Data
Author: artdaq team
Depends: pydantic
Exports: FunctionCall, FileImport, CallGraphEntry, DependencyEntry
Complexity: Medium | Lines: 47
"""

from pydantic import BaseModel, Field

class FunctionCall(BaseModel):
    caller_file: str
    'Path to the file containing the calling function.'
    caller_function: str
    'Name of the function making the call.'
    callee_name: str
    'Name of the function being called.'
    call_line: int
    'Line number where the call occurs.'
    call_type: str = 'direct'
    'Type of call: direct, method, constructor.'

class FileImport(BaseModel):
    source_file: str
    'Path to the file containing the import.'
    imported_path: str
    "The imported path as written (e.g., 'artdaq/Fragment.hh' or 'os.path')."
    import_type: str = 'include'
    'Type of import: include, import, from_import.'
    is_system: bool = False
    'True if this is a system/standard library import (e.g., <iostream>).'
    line_number: int = 0
    'Line number where the import occurs.'
    imported_names: list[str] = Field(default_factory=list)
    'For from_import, the names being imported.'

class CallGraphEntry(BaseModel):
    function_name: str
    'Name of the function.'
    file_path: str
    'Path to the file containing the function.'
    line_number: int
    'Line number where the function is defined.'
    signature: str = ''
    'Function signature if available.'

class DependencyEntry(BaseModel):
    file_path: str
    'Path to the dependent file.'
    import_type: str
    'Type of import relationship.'
    is_system: bool = False
    'Whether this is a system import.'
    line_number: int = 0
    'Line where the import occurs.'