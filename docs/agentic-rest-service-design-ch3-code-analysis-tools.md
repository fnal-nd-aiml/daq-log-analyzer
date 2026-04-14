> **Agentic REST API Design Document** | [← Log Analysis Tools](agentic-rest-service-design-ch2-log-analysis-tools.md) | [Table of Contents](agentic-rest-service-design.md) | [Next: Knowledge & Finding Tools →](agentic-rest-service-design-ch4-knowledge-finding-tools.md)

---

# Chapter 3: Code Analysis Tools

### Category: Code Analysis

These tools provide access to the parsed source code index. They let the agent trace error messages back to their origin in C++ source code, inspect function signatures and bodies, generate LLM-based function summaries, explore call graphs, and search for symbols by name or pattern. All code analysis tools require a pre-built `CodeIndex` (SQLite database of parsed functions, classes, symbols, and call relationships) and operate within an active session. When the code index is unavailable, tools raise a `VALIDATION_ERROR` (HTTP 422) with a `recovery_hint` pointing to `init_knowledge_base`.

**Request format:** All tool parameters (except `session_id`) are wrapped in a `params` object in the request body. For example: `{"session_id": "...", "params": {"name": "..."}}`.

**Cross-tool navigation pattern:** Every response includes handles (function names, file paths, line numbers) that can be passed directly into other code analysis tools. For example, a `find_error_source` result returns `function` values that feed directly into `get_call_graph`, `lookup_function`, or `summarize_function` as the `name` parameter, and `file` values that work as `file_filter` inputs.

---

#### Tool 6: find_error_source

##### 1. Purpose

Finds where an error message originates in source code. Given a runtime error string (which may contain variable values like numbers, hex addresses, and timestamps), the tool converts the message into search patterns that match the original C++ string literals, log macros, and exception throws. Returns ranked source locations with file paths, line numbers, match scores, context snippets, and enclosing function names.

Use this tool when the agent encounters an error message in a log file and needs to trace it back to the exact line of C++ code that produced it. This is typically the first code analysis step after identifying a suspicious error in log data.

Returns a flat dict containing: a ranked list of location objects (each with file path, line number, match score, context snippet, and function name), the search patterns that were tried, and the best match.

##### 2. Endpoint

```
POST /api/v1/agent/tools/find_error_source
```

##### 3. Request Schema

```json
{
  "type": "object",
  "properties": {
    "session_id": {
      "type": "string",
      "format": "uuid",
      "description": "Active investigation session ID."
    },
    "params": {
      "type": "object",
      "properties": {
        "error_message": {
          "type": "string",
          "minLength": 5,
          "maxLength": 2000,
          "description": "The runtime error message to locate in source code. May contain variable values (numbers, hex addresses, timestamps) that will be converted to wildcard patterns for matching against C++ string literals."
        }
      },
      "required": ["error_message"]
    }
  },
  "required": ["session_id", "params"]
}
```

##### 4. Response Schema

```json
{
  "locations": [
    {
      "file": "/data/sources/artdaq/artdaq/DAQrate/FragmentBuffer.cc",
      "line": 342,
      "score": 0.87,
      "context": "TLOG(TLVL_ERROR) << \"Fragment timeout after \" << timeout_ms << \"ms on link \" << std::hex << link_id;",
      "function": "CheckAndFillDataBuffer"
    }
  ],
  "search_patterns": [
    "Fragment\\ timeout\\ after",
    "fragment\\ timeout"
  ],
  "best_match": {
    "file": "/data/sources/artdaq/artdaq/DAQrate/FragmentBuffer.cc",
    "line": 342,
    "score": 0.87,
    "function": "CheckAndFillDataBuffer"
  }
}
```

**Navigation handles:**
- `locations[].function` -- pass to `get_call_graph` or `lookup_function` as `name`
- `locations[].file` -- pass to `lookup_function` as `file_filter`
- `best_match.function` -- pass to `get_call_graph` or `lookup_function` as `name` for the top match

##### 5. Error Responses

| HTTP Status | Error Code | Condition |
|---|---|---|
| 422 | `VALIDATION_ERROR` | `error_message` is missing or empty |
| 404 | `SESSION_NOT_FOUND` | The `session_id` does not reference an active session |
| 500 | `INTERNAL_ERROR` | Internal error during file search or pattern matching |

**Note:** Unlike other code analysis tools, `find_error_source` does not raise an error when the code index is unavailable. It calls `get_code_index(settings)` directly and passes the result (which may be `None`) to `SourceLocator`. The tool will still work with source roots alone; the code index is optional for enrichment.

**Example error response:**

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "'error_message' is required for find_error_source.",
    "details": {}
  }
}
```

##### 6. Implementation

**Code path:**

```
POST /api/v1/agent/tools/find_error_source
  -> srcs/api/tools/code_tools.py::find_error_source(ctx)
    -> Extract error_message from ctx.request_body.get("params", {})
    -> Validate error_message is present or raise VALIDATION_ERROR
    -> Build SourceLocator from source_config repos_path directories
    -> await SourceLocator.find_source(error_message)
    -> Returns SourceLocationResult (Pydantic model)
    -> Map locations to flat dicts with file, line, score, context, function
    -> Build best_match from result.best_match (or null if no match)
    -> Return flat dict with locations, search_patterns, best_match
```

**Module:** `srcs/extraction/source_locator.py`
**Class:** `SourceLocator`
**Method:** `async find_source(message) -> SourceLocationResult`

**Internal flow within `find_source`:**
1. `_create_search_patterns(message)` -- generates regex patterns from the runtime message by extracting static segments, converting variable positions to wildcards, and extracting key phrases
2. `_search_files(patterns, max_results, component)` -- searches source files matching the patterns across all configured `source_roots`
3. `_rank_matches(raw_matches, message)` -- scores matches based on log macro presence, pattern specificity, and word overlap
4. `_enrich_with_index_data(match, context_lines)` -- for each top match, looks up the enclosing function via `CodeIndex.find_function`, retrieves callers/callees via `CodeIndex.get_callers/get_callees`, extracts function body via tree-sitter, and fetches summary from ChromaDB

##### 7. Dependencies

| Dependency | Required | Purpose |
|---|---|---|
| `SourceLocator` | Yes | Core search engine; must be initialized with `source_roots` pointing to cloned artdaq repositories |
| `CodeIndex` | Yes | Provides `find_function`, `get_callers`, `get_callees`, `get_function_source` for enrichment; passed as `code_index` to SourceLocator constructor |
| `ChromaStore` | No | Provides function summaries via `find_similar_functions`; optional, summaries will be `null` if unavailable |
| `SessionStore` | Yes | Validates session and optionally stores results as findings |
| `source_roots` | Yes | List of `Path` objects pointing to cloned source code directories |

##### 8. Testing

**Test 1: Successful error source location**
- Mock `SourceLocator.find_source` to return a `SourceLocationResult` with two `SourceLocation` entries
- Assert response status 200, `data["locations"]` has length 2, each location has `file`, `line`, `score`, `context`, and `function`
- Assert `data["search_patterns"]` is a non-empty list

**Test 2: No matches found returns empty locations**
- Mock `SourceLocator.find_source` to return a `SourceLocationResult` with empty `locations` list
- Assert response status 200, `data["locations"]` is `[]`

**Test 3: Missing error_message returns 422**
- Omit `error_message` from `params`
- Assert response status 422, error code `VALIDATION_ERROR`

**Test 4: CodeIndex not initialized returns 422**
- Mock `get_code_index` to return `None`
- Assert response status 422, error code `VALIDATION_ERROR`
- Assert `details.recovery_hint` points to `init_knowledge_base`

**Test 5: Best match is populated for non-empty results**
- Mock `SourceLocator.find_source` to return a result with a `best_match`
- Assert `data["best_match"]` has `file`, `line`, `score`, and `function`

**Mock strategy:** Patch `SourceLocator.find_source` as an `AsyncMock` returning a pre-built `SourceLocationResult` with realistic `SourceLocation` objects. For integration tests, build a small CodeIndex from fixture C++ files.

##### 9. Example

**Request:**

```bash
curl -X POST http://localhost:8000/api/v1/agent/tools/find_error_source \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "params": {
      "error_message": "Fragment timeout after 5000ms on link 0x0100"
    }
  }'
```

**Response:**

```json
{
  "locations": [
    {
      "file": "/data/sources/artdaq/artdaq/DAQrate/FragmentBuffer.cc",
      "line": 342,
      "score": 0.87,
      "context": "TLOG(TLVL_ERROR) << \"Fragment timeout after \" << timeout_ms << \"ms on link \" << std::hex << link_id;",
      "function": "CheckAndFillDataBuffer"
    },
    {
      "file": "/data/sources/artdaq/artdaq/DAQrate/RequestBuffer.cc",
      "line": 118,
      "score": 0.52,
      "context": "TLOG(TLVL_WARNING) << \"Fragment timeout waiting for request on link \" << link_id_;",
      "function": "waitForRequest"
    }
  ],
  "search_patterns": [
    "Fragment\\ timeout\\ after",
    "fragment\\ timeout"
  ],
  "best_match": {
    "file": "/data/sources/artdaq/artdaq/DAQrate/FragmentBuffer.cc",
    "line": 342,
    "score": 0.87,
    "function": "CheckAndFillDataBuffer"
  }
}
```

---

#### Tool 7: lookup_function

##### 1. Purpose

Retrieves detailed metadata for a function from the code index, including its signature, parameters, return type, class membership, and source file location.

Use this tool when the agent needs to understand what a specific function does -- its interface and where it lives. This is the primary tool for inspecting a function identified by another tool (e.g., a `function` value returned by `find_error_source` or a `name` from `get_call_graph`).

Returns a flat dict containing a list of function objects (multiple results are possible when the same function name appears in different files or classes) and a total count.

##### 2. Endpoint

```
POST /api/v1/agent/tools/lookup_function
```

##### 3. Request Schema

```json
{
  "type": "object",
  "properties": {
    "session_id": {
      "type": "string",
      "format": "uuid",
      "description": "Active investigation session ID."
    },
    "params": {
      "type": "object",
      "properties": {
        "name": {
          "type": "string",
          "minLength": 1,
          "maxLength": 500,
          "description": "Function name to look up. Supports SQL LIKE wildcards (%) for pattern matching. Use exact names for precise results or '%fragment%' to search broadly."
        },
        "file_filter": {
          "type": "string",
          "default": null,
          "description": "Optional file path substring to restrict results. The filter is matched with LIKE '%{file_filter}%' against the full file path. Example: 'FragmentBuffer.cc' or 'artdaq/DAQrate'."
        }
      },
      "required": ["name"]
    }
  },
  "required": ["session_id", "params"]
}
```

##### 4. Response Schema

```json
{
  "functions": [
    {
      "name": "CheckAndFillDataBuffer",
      "file_path": "/data/sources/artdaq/artdaq/DAQrate/FragmentBuffer.cc",
      "start_line": 310,
      "end_line": 395,
      "signature": "bool FragmentBuffer::CheckAndFillDataBuffer(int timeout_ms)",
      "return_type": "bool",
      "parameters": [
        ["timeout_ms", "int"]
      ],
      "class_name": "FragmentBuffer"
    }
  ],
  "total": 1
}
```

**Navigation handles:**
- `functions[].name` -- pass to `get_call_graph` as `name`
- `functions[].file_path` -- pass to `lookup_function` as `file_filter`, or to `search_code` combined with file path
- `functions[].class_name` -- pass to `search_code` with `type: "class"` to explore the class

##### 5. Error Responses

| HTTP Status | Error Code | Condition |
|---|---|---|
| 422 | `VALIDATION_ERROR` | `name` is missing or empty |
| 404 | `SESSION_NOT_FOUND` | The `session_id` does not reference an active session |
| 422 | `VALIDATION_ERROR` | Code index not available; `recovery_hint` in details points to `init_knowledge_base` |
| 500 | `INTERNAL_ERROR` | Internal error during SQLite query or source file read |

**Example error response:**

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "'name' is required for lookup_function.",
    "details": {}
  }
}
```

##### 6. Implementation

**Code path:**

```
POST /api/v1/agent/tools/lookup_function
  -> srcs/api/tools/code_tools.py::lookup_function(ctx)
    -> Extract name from ctx.request_body.get("params", {})
    -> Validate name is present or raise VALIDATION_ERROR
    -> Retrieve CodeIndex via _get_code_index_or_error()
    -> Extract optional file_filter from params
    -> functions = CodeIndex.find_function(name, file_filter=file_filter)
    -> Returns list[FunctionInfo]
    -> Map to flat dicts with name, file_path, start_line, end_line, signature, return_type, parameters, class_name
    -> Return flat dict with functions list and total count
```

**Module:** `srcs/extraction/indexer/symbol_search.py`
**Class:** `SymbolSearchMixin` (mixed into `CodeIndex`)
**Method:** `find_function(name, file_filter) -> list[FunctionInfo]`

**SQL query:** Joins `functions` with `files` table, filters with `WHERE f.name LIKE ? AND files.path LIKE ?`. The `name` parameter supports `%` wildcards natively since it uses `LIKE`.

**Source retrieval module:** `srcs/extraction/indexer/index.py`
**Method:** `CodeIndex.get_function_source(name) -> str | None` -- reads file from disk, extracts lines `start_line` through `end_line`.

##### 7. Dependencies

| Dependency | Required | Purpose |
|---|---|---|
| `CodeIndex` | Yes | Provides `find_function` and `get_function_source`; must be initialized with a built index database |
| `SessionStore` | Yes | Validates session existence |
| SQLite database | Yes | The index database at `CodeIndexConfig.index_path` must exist with populated `functions` and `files` tables |

##### 8. Testing

**Test 1: Exact name lookup returns function details**
- Mock `CodeIndex.find_function("CheckAndFillDataBuffer", None)` to return a list with one `FunctionInfo`
- Assert response status 200, `data["total"]` is 1, returned function has correct `name`, `signature`, `class_name`, `start_line`, `end_line`

**Test 2: Wildcard search returns multiple matches**
- Mock `CodeIndex.find_function("%Buffer%", None)` to return three `FunctionInfo` objects
- Assert response status 200, `data["total"]` is 3

**Test 3: file_filter restricts results**
- Mock `CodeIndex.find_function("send_fragments", "BoardReaderCore.cc")` to return one result
- Verify the mock was called with the file_filter parameter

**Test 4: No match with exact name returns 404**
- Mock `CodeIndex.find_function` to return an empty list
- Assert response status 404, error code `FUNCTION_NOT_FOUND`

**Mock strategy:** Patch `CodeIndex.find_function` to return pre-built `FunctionInfo` dataclass instances. No async mocking needed since these are synchronous SQLite queries.

##### 9. Example

**Request:**

```bash
curl -X POST http://localhost:8000/api/v1/agent/tools/lookup_function \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "params": {
      "name": "CheckAndFillDataBuffer"
    }
  }'
```

**Response:**

```json
{
  "functions": [
    {
      "name": "CheckAndFillDataBuffer",
      "file_path": "/data/sources/artdaq/artdaq/DAQrate/FragmentBuffer.cc",
      "start_line": 310,
      "end_line": 395,
      "signature": "bool FragmentBuffer::CheckAndFillDataBuffer(int timeout_ms)",
      "return_type": "bool",
      "parameters": [
        ["timeout_ms", "int"]
      ],
      "class_name": "FragmentBuffer"
    }
  ],
  "total": 1
}
```

---

#### Tool 8: get_call_graph

##### 1. Purpose

Retrieves the call graph for a function -- which functions call it (callers) and which functions it calls (callees). Supports querying in one direction or both, and supports multi-level traversal up to a configurable depth.

Use this tool to understand the execution context around a function of interest. After identifying a suspicious function via `find_error_source` or `lookup_function`, use `get_call_graph` to trace how execution reaches that function (callers) and what downstream effects it triggers (callees). This is essential for distinguishing root causes from symptoms: the root cause is typically upstream in the call graph.

Returns a flat dict containing the function name and caller/callee lists. Each caller or callee entry includes a name, file path, and depth level.

##### 2. Endpoint

```
POST /api/v1/agent/tools/get_call_graph
```

##### 3. Request Schema

```json
{
  "type": "object",
  "properties": {
    "session_id": {
      "type": "string",
      "format": "uuid",
      "description": "Active investigation session ID."
    },
    "params": {
      "type": "object",
      "properties": {
        "name": {
          "type": "string",
          "minLength": 1,
          "maxLength": 500,
          "description": "Name of the function to get the call graph for. Supports both simple names ('send_fragments') and qualified names ('artdaq::BoardReaderCore::send_fragments'). The system searches by both the full name and the simple name (last segment after '::') to maximize coverage."
        },
        "direction": {
          "type": "string",
          "enum": ["callers", "callees", "both"],
          "default": "both",
          "description": "Which direction to traverse. 'callers' returns functions that call the target. 'callees' returns functions the target calls. 'both' returns both directions. Note: the implementation does not validate this value; unrecognized values will result in neither callers nor callees being returned."
        },
        "depth": {
          "type": "integer",
          "default": 1,
          "description": "How many levels deep to traverse the call graph. Depth 1 returns immediate callers/callees. Higher depths increase response size and query time. Note: the implementation does not enforce minimum/maximum bounds on this value; it is passed directly to the CodeIndex."
        }
      },
      "required": ["name"]
    }
  },
  "required": ["session_id", "params"]
}
```

##### 4. Response Schema

```json
{
  "function": "CheckAndFillDataBuffer",
  "callers": [
    {
      "name": "applyRequestsWindowMode",
      "file_path": "/data/sources/artdaq/artdaq/Application/BoardReaderCore.cc",
      "depth": 1
    },
    {
      "name": "processRequestsSafe",
      "file_path": "/data/sources/artdaq/artdaq/Application/BoardReaderCore.cc",
      "depth": 1
    }
  ],
  "callees": [
    {
      "name": "getElapsedTime_",
      "file_path": "/data/sources/artdaq/artdaq/DAQrate/FragmentBuffer.cc",
      "depth": 1
    },
    {
      "name": "reportMetric_",
      "file_path": "/data/sources/artdaq/artdaq/DAQrate/FragmentBuffer.cc",
      "depth": 1
    }
  ]
}
```

When `direction` is `"callers"`, only the `callers` list is included. When `direction` is `"callees"`, only the `callees` list is included. When `direction` is `"both"` (default), both lists are included. At `depth` > 1, entries at deeper levels have their `depth` field set accordingly.

**Note on nullable fields:** The `file_path` and `depth` fields in caller/callee entries use `hasattr` checks against the result objects. If the underlying object does not have a `file_path` attribute, the value will be `null`. If it does not have a `depth` attribute, the value defaults to `1`.

**Navigation handles:**
- `callers[].name` -- pass to `lookup_function` as `name` to inspect the caller, or to `get_call_graph` to continue tracing upstream
- `callees[].name` -- pass to `lookup_function` as `name`, or to `get_call_graph` to trace downstream
- `callers[].file_path` / `callees[].file_path` -- pass to `lookup_function` as `file_filter`

##### 5. Error Responses

| HTTP Status | Error Code | Condition |
|---|---|---|
| 422 | `VALIDATION_ERROR` | `name` is missing or empty |
| 404 | `SESSION_NOT_FOUND` | The `session_id` does not reference an active session |
| 422 | `VALIDATION_ERROR` | Code index not available; `recovery_hint` in details points to `init_knowledge_base` |
| 500 | `INTERNAL_ERROR` | Internal error during call graph traversal |

**Note:** The implementation does not validate `direction` or `depth` values. Invalid `direction` values will silently produce a response with no callers or callees. The `depth` value is passed directly to the CodeIndex without range checking.

**Example error response:**

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "'name' is required for get_call_graph.",
    "details": {}
  }
}
```

##### 6. Implementation

**Code path:**

```
POST /api/v1/agent/tools/get_call_graph
  -> srcs/api/tools/code_tools.py::get_call_graph(ctx)
    -> Extract name from ctx.request_body.get("params", {})
    -> Validate name is present or raise VALIDATION_ERROR
    -> Retrieve CodeIndex via _get_code_index_or_error()
    -> Extract depth (default 1) and direction (default "both") from params
    -> Initialize result dict with {"function": name}
    -> If direction in ("callers", "both"):
         callers = CodeIndex.get_callers(name, max_depth=depth)
         Map to list of {name, file_path, depth} dicts
         file_path uses hasattr check (None if absent)
         depth uses hasattr check (defaults to 1 if absent)
    -> If direction in ("callees", "both"):
         callees = CodeIndex.get_callees(name, max_depth=depth)
         Map to list of {name, file_path, depth} dicts (same hasattr logic)
    -> Return flat dict with function, callers, callees
```

**Module:** `srcs/extraction/indexer/call_graph.py`
**Class:** `CallGraphMixin` (mixed into `CodeIndex`)
**Methods:**
- `get_callers(function_name) -> list[dict]` -- queries `function_calls` table joined with `functions` and `files`, matching by callee_name (string) and callee_function_id (resolved reference)
- `get_callees(function_name) -> list[dict]` -- queries `function_calls` table joined with `functions` and `files`, matching by caller function name
- `get_call_chain(function_name, direction, depth) -> dict` -- recursive traversal, returns nested `{"name": ..., "children": [...]}` tree

**Name resolution:** Both `get_callers` and `get_callees` handle qualified names by extracting the simple name (last segment after `::`) and searching for both the full and simple forms. This ensures matches when call sites use unqualified names.

##### 7. Dependencies

| Dependency | Required | Purpose |
|---|---|---|
| `CodeIndex` | Yes | Provides `get_callers`, `get_callees`, and `get_call_chain`; requires the `function_calls` table to be populated (built during `build_index`) with resolved references (`resolve_call_references`) |
| `SessionStore` | Yes | Validates session existence |
| SQLite database | Yes | The index database must have populated `function_calls`, `functions`, and `files` tables |

##### 8. Testing

**Test 1: Both directions returns callers and callees**
- Mock `CodeIndex.get_callers` to return two caller objects, mock `CodeIndex.get_callees` to return three callee objects
- Assert response status 200, `len(data["callers"])` is 2, `len(data["callees"])` is 3
- Assert each caller has `name`, `file_path`, `depth`
- Assert each callee has `name`, `file_path`, `depth`

**Test 2: Single direction only queries one side**
- Send `direction: "callers"`, mock both `get_callers` and `get_callees`
- Assert `get_callees` was not called, response does not contain `callees`

**Test 3: Depth > 1 includes deeper entries**
- Mock `CodeIndex.get_callers` with `max_depth=2` to return entries at depth 1 and depth 2
- Assert response includes callers with varying `depth` values

**Test 4: Function with no callers returns empty list**
- Mock `CodeIndex.get_callers` to return `[]`
- Assert response status 200, `data["callers"]` is `[]`

**Test 5: Qualified name resolution works**
- Call with `name: "artdaq::BoardReaderCore::send_fragments"`
- Verify the mock receives the full qualified name (the backend handles simple name extraction internally)

**Mock strategy:** Patch `CodeIndex.get_callers` and `CodeIndex.get_callees` to return pre-built lists of objects with `name`, `file_path`, and `depth` attributes. All methods are synchronous.

##### 9. Example

**Request:**

```bash
curl -X POST http://localhost:8000/api/v1/agent/tools/get_call_graph \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "params": {
      "name": "CheckAndFillDataBuffer",
      "direction": "both",
      "depth": 1
    }
  }'
```

**Response:**

```json
{
  "function": "CheckAndFillDataBuffer",
  "callers": [
    {
      "name": "applyRequestsWindowMode",
      "file_path": "/data/sources/artdaq/artdaq/Application/BoardReaderCore.cc",
      "depth": 1
    },
    {
      "name": "processRequestsSafe",
      "file_path": "/data/sources/artdaq/artdaq/Application/BoardReaderCore.cc",
      "depth": 1
    }
  ],
  "callees": [
    {
      "name": "getElapsedTime_",
      "file_path": "/data/sources/artdaq/artdaq/DAQrate/FragmentBuffer.cc",
      "depth": 1
    },
    {
      "name": "reportMetric_",
      "file_path": "/data/sources/artdaq/artdaq/DAQrate/FragmentBuffer.cc",
      "depth": 1
    },
    {
      "name": "write",
      "file_path": null,
      "depth": 1
    }
  ]
}
```

---

#### Tool 9: summarize_function

##### 1. Purpose

Generates an LLM-based summary of a function's behavior. Given a function name, it looks up the function in the code index, reads its source from disk, and uses a `FunctionSummarizer` (backed by the configured LLM provider) to produce a natural-language description of what the function does.

Use this tool when the agent needs a high-level understanding of a function's behavior without manually reading its full source code. This is particularly useful for large or complex functions where the signature alone is not sufficient to understand the logic.

Returns a flat dict containing the function's metadata (name, file path, line range, signature, class name, return type) plus a `summary` string generated by the LLM.

##### 2. Endpoint

```
POST /api/v1/agent/tools/summarize_function
```

##### 3. Request Schema

```json
{
  "type": "object",
  "properties": {
    "session_id": {
      "type": "string",
      "format": "uuid",
      "description": "Active investigation session ID."
    },
    "params": {
      "type": "object",
      "properties": {
        "name": {
          "type": "string",
          "minLength": 1,
          "description": "Function name to summarize. Must match a function in the code index."
        },
        "file_filter": {
          "type": "string",
          "default": null,
          "description": "Optional file path substring to restrict which function is selected when multiple matches exist."
        }
      },
      "required": ["name"]
    }
  },
  "required": ["session_id", "params"]
}
```

##### 4. Response Schema

```json
{
  "name": "CheckAndFillDataBuffer",
  "file_path": "/data/sources/artdaq/artdaq/DAQrate/FragmentBuffer.cc",
  "start_line": 310,
  "end_line": 395,
  "signature": "bool FragmentBuffer::CheckAndFillDataBuffer(int timeout_ms)",
  "class_name": "FragmentBuffer",
  "return_type": "bool",
  "summary": "Checks whether the data buffer has available space and fills it with incoming fragment data. Returns true if the buffer was successfully filled within the given timeout period, false if the timeout expired or the buffer was full."
}
```

**Fallback behavior:** If the function is found but its source cannot be read from disk (file missing or line range invalid), the response still includes metadata fields but the `summary` will be a fallback string: `"Function {name} (source unavailable)"`. In this case, `class_name` and `return_type` are omitted from the response.

If the function is not found at all, the response includes an `error` field alongside empty `functions` list and `total: 0`:

```json
{
  "error": "Function 'nonexistent_func' not found",
  "functions": [],
  "total": 0
}
```

**Navigation handles:**
- `name` -- pass to `get_call_graph` as `name` to explore callers/callees
- `file_path` -- pass to `lookup_function` as `file_filter`

##### 5. Error Responses

| HTTP Status | Error Code | Condition |
|---|---|---|
| 422 | `VALIDATION_ERROR` | `name` is missing or empty |
| 404 | `SESSION_NOT_FOUND` | The `session_id` does not reference an active session |
| 422 | `VALIDATION_ERROR` | Code index not available; `recovery_hint` in details points to `init_knowledge_base` |
| 500 | `INTERNAL_ERROR` | Internal error during LLM summarization or source file read |

##### 6. Implementation

**Code path:**

```
POST /api/v1/agent/tools/summarize_function
  -> srcs/api/tools/code_tools.py::summarize_function(ctx)
    -> Extract name from ctx.request_body.get("params", {})
    -> Validate name is present or raise VALIDATION_ERROR
    -> Retrieve CodeIndex via _get_code_index_or_error()
    -> Extract optional file_filter from params
    -> functions = CodeIndex.find_function(name, file_filter=file_filter)
    -> If no functions found, return error dict with empty functions list
    -> Take first match (functions[0])
    -> Read source from disk using file_path and start_line/end_line
    -> If source unavailable, return metadata with fallback summary string
    -> Determine language from file extension using lang_map lookup
    -> Create FunctionSummarizer(llm_provider) from srcs/extraction/summarizer
    -> summary = await FunctionSummarizer.summarize_function(source, name, file_path, language)
    -> Return flat dict with name, file_path, start_line, end_line, signature, class_name, return_type, summary
```

**Module:** `srcs/extraction/summarizer.py`
**Class:** `FunctionSummarizer`
**Method:** `async summarize_function(source, name, file_path, language) -> str`

**LLM dependency:** This tool requires a configured LLM provider. The provider is created via `create_llm_provider(get_llm_config(settings))` within the tool handler.

##### 7. Dependencies

| Dependency | Required | Purpose |
|---|---|---|
| `CodeIndex` | Yes | Provides `find_function` to locate the function metadata |
| `FunctionSummarizer` | Yes | LLM-backed summarizer from `srcs/extraction/summarizer.py` |
| `LLMProvider` | Yes | Configured LLM provider for generating summaries |
| `SessionStore` | Yes | Validates session existence |

##### 8. Testing

**Test 1: Successful summarization returns metadata and summary**
- Mock `CodeIndex.find_function` to return one `FunctionInfo`, mock file read to return source, mock `FunctionSummarizer.summarize_function` to return a summary string
- Assert response status 200, response has `name`, `file_path`, `start_line`, `end_line`, `signature`, `class_name`, `return_type`, `summary`

**Test 2: Function not found returns error dict**
- Mock `CodeIndex.find_function` to return empty list
- Assert response status 200, response has `error` field, `functions` is `[]`, `total` is 0

**Test 3: Source unavailable returns fallback summary**
- Mock `CodeIndex.find_function` to return a function with a non-existent file path
- Assert response status 200, `summary` contains "source unavailable"

**Test 4: Missing name returns 422**
- Omit `name` from `params`
- Assert response status 422, error code `VALIDATION_ERROR`

**Mock strategy:** Patch `CodeIndex.find_function`, `Path.read_text`, and `FunctionSummarizer.summarize_function` (as `AsyncMock`). The LLM provider and summarizer should be mocked to avoid real LLM calls.

##### 9. Example

**Request:**

```bash
curl -X POST http://localhost:8000/api/v1/agent/tools/summarize_function \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "params": {
      "name": "CheckAndFillDataBuffer"
    }
  }'
```

**Response:**

```json
{
  "name": "CheckAndFillDataBuffer",
  "file_path": "/data/sources/artdaq/artdaq/DAQrate/FragmentBuffer.cc",
  "start_line": 310,
  "end_line": 395,
  "signature": "bool FragmentBuffer::CheckAndFillDataBuffer(int timeout_ms)",
  "class_name": "FragmentBuffer",
  "return_type": "bool",
  "summary": "Checks whether the data buffer has available space and fills it with incoming fragment data. Waits up to timeout_ms milliseconds for space to become available. Returns true if the buffer was successfully filled, false if the timeout expired. Logs an error via TLOG if the timeout is exceeded and reports the metric via reportMetric_."
}
```

---

#### Tool 10: search_code

##### 1. Purpose

Searches the code index for symbols (functions, classes, variables) by name or pattern. This is a broad discovery tool for finding relevant code elements when the agent does not have an exact function name.

Use this tool for exploratory queries: finding all functions related to "fragment" processing, discovering class hierarchies, or locating variables that control timeout behavior. It complements `lookup_function` (which requires a known name) by supporting fuzzy, pattern-based discovery. The query uses SQL LIKE syntax where `%` matches any sequence of characters.

Returns a flat dict containing a list of symbol records (each with the symbol name, type, file path, line number, and context) and a total count. Results are capped at a configurable limit (default 20).

##### 2. Endpoint

```
POST /api/v1/agent/tools/search_code
```

##### 3. Request Schema

```json
{
  "type": "object",
  "properties": {
    "session_id": {
      "type": "string",
      "format": "uuid",
      "description": "Active investigation session ID."
    },
    "params": {
      "type": "object",
      "properties": {
        "query": {
          "type": "string",
          "minLength": 1,
          "maxLength": 500,
          "description": "Search query for symbol names. Supports SQL LIKE wildcards: '%' matches any sequence of characters. Examples: '%Fragment%' finds all symbols containing 'Fragment', 'get%' finds symbols starting with 'get', '%Buffer' finds symbols ending with 'Buffer'. Exact names (no wildcards) match that specific symbol name."
        },
        "type": {
          "type": "string",
          "enum": ["function", "class", "variable"],
          "default": null,
          "description": "Optional filter to restrict results to a specific symbol type. If omitted, all symbol types are searched."
        },
        "limit": {
          "type": "integer",
          "minimum": 1,
          "default": 20,
          "description": "Maximum number of results to return."
        }
      },
      "required": ["query"]
    }
  },
  "required": ["session_id", "params"]
}
```

##### 4. Response Schema

```json
{
  "symbols": [
    {
      "name": "CheckAndFillDataBuffer",
      "type": "function",
      "file_path": "/data/sources/artdaq/artdaq/DAQrate/FragmentBuffer.cc",
      "line": 310,
      "context": "bool FragmentBuffer::CheckAndFillDataBuffer(int timeout_ms)"
    },
    {
      "name": "FragmentBuffer",
      "type": "class",
      "file_path": "/data/sources/artdaq/artdaq/DAQrate/FragmentBuffer.hh",
      "line": 24,
      "context": "class FragmentBuffer : public DataBuffer"
    },
    {
      "name": "processFragment",
      "type": "function",
      "file_path": "/data/sources/artdaq/artdaq/Application/BoardReaderCore.cc",
      "line": 450,
      "context": "void BoardReaderCore::processFragment(artdaq::Fragment&& fragment)"
    },
    {
      "name": "fragment_id_t",
      "type": "variable",
      "file_path": "/data/sources/artdaq/artdaq/DAQdata/Fragment.hh",
      "line": 18,
      "context": "using fragment_id_t = uint64_t"
    }
  ],
  "total": 12
}
```

**Note on nullable fields:** The `file_path`, `line`, and `context` fields use `hasattr` checks against the result objects. If the underlying symbol object does not have these attributes, their values will be `null`. This can occur for symbols returned as dict-style results rather than full dataclass instances.

**Navigation handles:**
- `symbols[].name` -- pass to `lookup_function` (for functions), `get_call_graph`, or as a refined search query
- `symbols[].file_path` -- pass to `lookup_function` as `file_filter` to narrow results to a specific file (may be `null`)
- `symbols[].type` -- use to decide which follow-up tool to call: `lookup_function` for functions, `get_call_graph` for functions, `search_code` with the class name for classes

##### 5. Error Responses

| HTTP Status | Error Code | Condition |
|---|---|---|
| 422 | `VALIDATION_ERROR` | `query` is missing or empty |
| 404 | `SESSION_NOT_FOUND` | The `session_id` does not reference an active session |
| 422 | `VALIDATION_ERROR` | Code index not available; `recovery_hint` in details points to `init_knowledge_base` |
| 500 | `INTERNAL_ERROR` | Internal error during SQLite query |

**Note:** The implementation does not validate the `type` parameter value. Invalid type values are passed directly to `CodeIndex.search_symbols`.

**Example error response:**

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "'query' is required for search_code.",
    "details": {}
  }
}
```

##### 6. Implementation

**Code path:**

```
POST /api/v1/agent/tools/search_code
  -> srcs/api/tools/code_tools.py::search_code(ctx)
    -> Extract query from ctx.request_body.get("params", {})
    -> Validate query is present or raise VALIDATION_ERROR
    -> Retrieve CodeIndex via _get_code_index_or_error()
    -> Extract optional type and limit (default 20) from params
    -> symbols = CodeIndex.search_symbols(query, symbol_type=type, limit=limit)
    -> Returns list of symbol objects
    -> Map to dicts with name, type (from symbol_type), file_path, line, context
       file_path, line, context use hasattr checks (may be null)
    -> Return flat dict with symbols list and total count
```

**Module:** `srcs/extraction/indexer/symbol_search.py`
**Class:** `SymbolSearchMixin` (mixed into `CodeIndex`)
**Method:** `search_symbols(query, symbol_type) -> list[dict]`

**SQL query:** Joins `symbols` with `files` table, filters with `WHERE s.name LIKE ?` and optionally `AND s.symbol_type = ?`. Results ordered by `s.name` with `LIMIT 100`. The `symbols` table is populated during `build_index` from functions, classes, and variables.

**Important:** The result count is controlled by the `limit` parameter (default 20). The response includes a `total` count of the results returned.

##### 7. Dependencies

| Dependency | Required | Purpose |
|---|---|---|
| `CodeIndex` | Yes | Provides `search_symbols`; requires the `symbols` table to be populated during `build_index` |
| `SessionStore` | Yes | Validates session existence |
| SQLite database | Yes | The index database must have a populated `symbols` table with indexed `name` column |

##### 8. Testing

**Test 1: Wildcard search returns mixed symbol types**
- Mock `CodeIndex.search_symbols("%Fragment%", None)` to return a list with function, class, and variable entries
- Assert response status 200, `data["total"]` equals the list length
- Assert each symbol has `name`, `type`, `file_path`, `line`, `context`

**Test 2: type filter restricts results**
- Mock `CodeIndex.search_symbols("%Buffer%", "class")` to return only class entries
- Assert all returned symbols have `type: "class"`
- Verify mock was called with `symbol_type="class"`

**Test 3: Exact name search returns single result**
- Mock `CodeIndex.search_symbols("FragmentBuffer", None)` to return one entry
- Assert `data["total"]` is 1

**Test 4: No matches returns empty list**
- Mock `CodeIndex.search_symbols` to return `[]`
- Assert response status 200, `data["symbols"]` is `[]`, `data["total"]` is 0

**Test 5: Limit parameter controls result count**
- Send `limit: 5`, verify mock was called with `limit=5`
- Assert response returns at most 5 symbols

**Mock strategy:** Patch `CodeIndex.search_symbols` to return pre-built lists of objects with `name`, `symbol_type`, `file_path`, `line`, and `context` attributes. All methods are synchronous SQLite queries.

##### 9. Example

**Request:**

```bash
curl -X POST http://localhost:8000/api/v1/agent/tools/search_code \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "params": {
      "query": "%Fragment%",
      "type": "function"
    }
  }'
```

**Response:**

```json
{
  "symbols": [
    {
      "name": "CheckAndFillDataBuffer",
      "type": "function",
      "file_path": "/data/sources/artdaq/artdaq/DAQrate/FragmentBuffer.cc",
      "line": 310,
      "context": "bool FragmentBuffer::CheckAndFillDataBuffer(int timeout_ms)"
    },
    {
      "name": "addFragment",
      "type": "function",
      "file_path": "/data/sources/artdaq/artdaq/DAQrate/FragmentBuffer.cc",
      "line": 120,
      "context": "void FragmentBuffer::addFragment(artdaq::Fragment&& frag)"
    },
    {
      "name": "getIncompleteFragmentCount",
      "type": "function",
      "file_path": "/data/sources/artdaq/artdaq/DAQrate/FragmentBuffer.cc",
      "line": 85,
      "context": "size_t FragmentBuffer::getIncompleteFragmentCount() const"
    },
    {
      "name": "makeFragment",
      "type": "function",
      "file_path": "/data/sources/artdaq/artdaq/DAQdata/FragmentGenerator.cc",
      "line": 44,
      "context": "artdaq::Fragment FragmentGenerator::makeFragment(size_t payload_size)"
    },
    {
      "name": "processFragment",
      "type": "function",
      "file_path": "/data/sources/artdaq/artdaq/Application/BoardReaderCore.cc",
      "line": 450,
      "context": "void BoardReaderCore::processFragment(artdaq::Fragment&& fragment)"
    },
    {
      "name": "releaseFragment",
      "type": "function",
      "file_path": "/data/sources/artdaq/artdaq/DAQrate/FragmentBuffer.cc",
      "line": 178,
      "context": "bool FragmentBuffer::releaseFragment(fragment_id_t id)"
    },
    {
      "name": "sendFragment",
      "type": "function",
      "file_path": "/data/sources/artdaq/artdaq/TransferPlugins/TransferInterface.cc",
      "line": 67,
      "context": "bool TransferInterface::sendFragment(artdaq::Fragment&& frag, size_t timeout_us)"
    },
    {
      "name": "validateFragment",
      "type": "function",
      "file_path": "/data/sources/artdaq/artdaq/DAQdata/FragmentValidator.cc",
      "line": 22,
      "context": "bool FragmentValidator::validateFragment(const artdaq::Fragment& frag)"
    }
  ],
  "total": 8
}
```

---

> [← Log Analysis Tools](agentic-rest-service-design-ch2-log-analysis-tools.md) | [Table of Contents](agentic-rest-service-design.md) | [Next: Knowledge & Finding Tools →](agentic-rest-service-design-ch4-knowledge-finding-tools.md)
