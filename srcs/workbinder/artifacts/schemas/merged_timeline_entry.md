## Merged Timeline Entry

### MSG Facility Format

artdaq log files use the MessageFacility (MSG) format. Each log block has a header line followed by body lines:

```
%MSG-<level> <component>:  <category> <timestamp> <host> <application> <pid>
      <source_location>
<message body lines...>
%MSG
```

Header fields:
- `level`: Single letter — `e` (error), `s` (severe/error), `w` (warning), `i` (info), `d` (debug)
- `component`: The module or class name that emitted the message
- `category`: A secondary classification (often same as component)
- `timestamp`: `DD-Mon-YYYY HH:MM:SS TZ`
- `source_location`: `SourceFile.cc:lineNumber` identifying where the log call was made

### Fields

- `timestamp` (string): Timestamp from the MSG block (e.g., "16-Jan-2026 15:24:47")
- `source_file` (string): Source log filename
- `board_name` (string): Short board name from filename
- `level` (string): One of: error, warning, info, debug
- `component` (string): Component name from MSG header
- `message` (string): Full message content (all body lines joined with newline)
- `source_location` (string): Source code location from MSG header (e.g., "BoardReader_generator.cc:345")

### JSON Format

```json
{
  "entries": [
    {
      "timestamp": "16-Jan-2026 15:24:47",
      "source_file": "run14001-icaruspmtwwtop03.log",
      "board_name": "wwtop03",
      "level": "error",
      "component": "BoardReader03",
      "message": "Fragment timeout: FragID 8194\nCAENReadData() tried to write 312596 bytes",
      "source_location": "BoardReader_generator.cc:345"
    }
  ],
  "total_entries": 1,
  "total_errors": 1,
  "total_warnings": 0,
  "total_info": 0,
  "file_count": 1,
  "earliest_timestamp": "16-Jan-2026 15:24:47",
  "latest_timestamp": "16-Jan-2026 15:24:47"
}
```
