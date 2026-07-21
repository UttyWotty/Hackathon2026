# MCP Protocol Support

## Overview

The Manufacturing Analytics API now supports **Model Context Protocol (MCP)** endpoints alongside the existing REST API. This enables LLM integration and MCP-compatible clients to interact with the server.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│         Unified Server (Port 3020)                       │
│                                                           │
│  ┌──────────────────┐  ┌──────────────────┐            │
│  │   REST API       │  │   MCP Protocol   │            │
│  │   Endpoints      │  │   Endpoints      │            │
│  │                  │  │                  │            │
│  │ /analytics/roi   │  │ /tools/list      │            │
│  │ /database/query  │  │ /tools/call      │            │
│  │ /visualization/* │  │ /mcp/info        │            │
│  └──────────────────┘  └──────────────────┘            │
│           │                      │                       │
│           └──────────┬───────────┘                       │
│                      │                                    │
│           ┌──────────▼──────────┐                       │
│           │   execute_tool()     │                       │
│           │   (shared backend)   │                       │
│           └─────────────────────┘                       │
└─────────────────────────────────────────────────────────┘
```

## MCP Protocol Endpoints

### 1. List Tools

**Endpoint:** `POST /tools/list`

**Description:** Returns all available tools in MCP protocol format.

**Request:**
```json
{}
```

**Response:**
```json
{
  "tools": [
    {
      "name": "run_roi_analysis",
      "description": "Calculate ROI and cycle time efficiency metrics...",
      "inputSchema": {
        "type": "object",
        "properties": {
          "equipment_codes": {
            "type": "array",
            "items": {"type": "string"}
          },
          "start_date": {
            "type": "string"
          },
          "end_date": {
            "type": "string"
          }
        },
        "required": ["start_date", "end_date"]
      }
    },
    ...
  ],
  "count": 15
}
```

**Example:**
```bash
curl -X POST http://localhost:3020/tools/list \
  -H "Content-Type: application/json" \
  -d '{}'
```

### 2. Call Tool

**Endpoint:** `POST /tools/call`

**Description:** Execute a tool using MCP protocol format.

**Request:**
```json
{
  "name": "run_roi_analysis",
  "arguments": {
    "equipment_codes": ["EMA-4104"],
    "start_date": "2024-01-01",
    "end_date": "2024-12-31"
  }
}
```

**Alternative formats supported:**
```json
{
  "tool": "run_roi_analysis",
  "args": {
    "equipment_codes": ["EMA-4104"],
    "start_date": "2024-01-01",
    "end_date": "2024-12-31"
  }
}
```

**Response (Success):**
```json
{
  "content": [
    {
      "type": "text",
      "text": "{\n  \"status\": \"success\",\n  \"message\": \"...\",\n  \"data\": {...}\n}"
    }
  ],
  "isError": false
}
```

**Response (Error):**
```json
{
  "content": [
    {
      "type": "text",
      "text": "{\n  \"error\": \"Error message\",\n  \"status\": \"error\"\n}"
    }
  ],
  "isError": true
}
```

**Example:**
```bash
curl -X POST http://localhost:3020/tools/call \
  -H "Content-Type: application/json" \
  -d '{
    "name": "run_roi_analysis",
    "arguments": {
      "equipment_codes": ["EMA-4104"],
      "start_date": "2024-01-01",
      "end_date": "2024-12-31"
    }
  }'
```

### 3. Server Info

**Endpoint:** `GET /mcp/info`

**Description:** Get MCP server information and capabilities.

**Response:**
```json
{
  "name": "Manufacturing Analytics MCP Server",
  "version": "2.0.0",
  "protocol": "mcp",
  "capabilities": {
    "tools": true,
    "resources": false,
    "prompts": false
  },
  "tools_count": 15,
  "endpoints": {
    "list_tools": "/tools/list",
    "call_tool": "/tools/call",
    "info": "/mcp/info"
  }
}
```

**Example:**
```bash
curl http://localhost:3020/mcp/info
```

## Available Tools

All tools from `core/tools_config.py` are automatically available via MCP protocol:

- `refresh_master_shot_table` - Refresh master data table
- `run_roi_analysis` - ROI and cycle time efficiency analysis
- `run_runrate_analysis` - RunRate with MTTR/MTBF metrics
- `run_capacity_analysis` - Capacity planning and OEE analysis
- `run_rca_analysis` - Root cause analysis
- `run_ct_deviation_analysis` - Cycle time deviation analysis
- `run_ct_efficiency_analysis` - CT efficiency and supplier benchmarking
- `run_tooling_eol_analysis` - Tool end-of-life prediction
- `run_sql_query` - Execute Snowflake SQL queries
- `list_tables` - List available database tables
- `describe_table` - Get table schema information
- `create_chart` - Create Plotly visualizations
- `schedule_job` - Schedule automated jobs
- `list_scheduled_jobs` - List all scheduled jobs
- `cancel_job` - Cancel a scheduled job

## Integration Examples

### Python Client

```python
import requests

# List available tools
response = requests.post("http://localhost:3020/tools/list", json={})
tools = response.json()["tools"]
print(f"Available tools: {len(tools)}")

# Call a tool
result = requests.post(
    "http://localhost:3020/tools/call",
    json={
        "name": "run_roi_analysis",
        "arguments": {
            "equipment_codes": ["EMA-4104"],
            "start_date": "2024-01-01",
            "end_date": "2024-12-31"
        }
    }
)

mcp_response = result.json()
if not mcp_response["isError"]:
    # Parse the JSON text from content
    import json
    tool_result = json.loads(mcp_response["content"][0]["text"])
    print(f"Status: {tool_result['status']}")
else:
    print("Error occurred")
```

### JavaScript/TypeScript Client

```typescript
// List tools
const listResponse = await fetch('http://localhost:3020/tools/list', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({})
});
const { tools } = await listResponse.json();

// Call tool
const callResponse = await fetch('http://localhost:3020/tools/call', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    name: 'run_roi_analysis',
    arguments: {
      equipment_codes: ['EMA-4104'],
      start_date: '2024-01-01',
      end_date: '2024-12-31'
    }
  })
});

const mcpResult = await callResponse.json();
if (!mcpResult.isError) {
  const toolResult = JSON.parse(mcpResult.content[0].text);
  console.log('Success:', toolResult);
} else {
  console.error('Error:', mcpResult);
}
```

## Comparison: REST API vs MCP Protocol

| Feature | REST API | MCP Protocol |
|---------|----------|--------------|
| **Endpoint** | `/analytics/roi` | `/tools/call` |
| **Tool Discovery** | Manual (check `/docs`) | `/tools/list` |
| **Format** | Direct JSON | MCP protocol format |
| **Use Case** | Web apps, direct API calls | LLM integration, MCP clients |
| **Response** | Direct result | Wrapped in MCP format |

**Both use the same backend** - `execute_tool()` function handles all tool execution.

## Benefits

✅ **Unified Server**: One port (3020) for both REST and MCP  
✅ **Backward Compatible**: All existing REST endpoints still work  
✅ **LLM Ready**: MCP protocol enables LLM tool integration  
✅ **Tool Discovery**: Automatic tool listing via `/tools/list`  
✅ **Standard Protocol**: Follows MCP protocol specification  

## Testing

Test MCP endpoints using curl or any HTTP client:

```bash
# 1. Check server info
curl http://localhost:3020/mcp/info

# 2. List all tools
curl -X POST http://localhost:3020/tools/list \
  -H "Content-Type: application/json" \
  -d '{}'

# 3. Call a tool
curl -X POST http://localhost:3020/tools/call \
  -H "Content-Type: application/json" \
  -d '{
    "name": "run_roi_analysis",
    "arguments": {
      "equipment_codes": ["EMA-4104"],
      "start_date": "2024-01-01",
      "end_date": "2024-12-31"
    }
  }'
```

## Notes

- MCP protocol endpoints are available at the root level (no prefix)
- All tools are automatically converted from Bedrock format to MCP format
- Error handling follows MCP protocol standards
- Response format matches MCP protocol specification
- Both REST and MCP endpoints use the same `execute_tool()` backend function

