"""
Web Search MCP Server
======================

A simple MCP server that provides web search capabilities using
Claude's built-in web search tool via the Anthropic API.

This server exposes a single tool: `search` that performs web searches
and returns summarized results with citations.
"""

import json
import os
import sys
from typing import Any

from anthropic import Anthropic


def create_mcp_response(id: str, result: Any) -> dict:
    """Create a JSON-RPC response."""
    return {"jsonrpc": "2.0", "id": id, "result": result}


def create_mcp_error(id: str, code: int, message: str) -> dict:
    """Create a JSON-RPC error response."""
    return {"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}}


def handle_initialize(request_id: str) -> dict:
    """Handle the initialize request."""
    return create_mcp_response(request_id, {
        "protocolVersion": "2024-11-05",
        "capabilities": {
            "tools": {}
        },
        "serverInfo": {
            "name": "web_search",
            "version": "1.0.0"
        }
    })


def handle_tools_list(request_id: str) -> dict:
    """Handle the tools/list request."""
    return create_mcp_response(request_id, {
        "tools": [
            {
                "name": "search",
                "description": "Search the web for current information. Use this when you need up-to-date information, documentation, troubleshooting help, or any information not available in local files.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query. Be specific and descriptive for best results."
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of search results to return (1-10). Default is 5.",
                            "default": 5,
                            "minimum": 1,
                            "maximum": 10
                        }
                    },
                    "required": ["query"]
                }
            }
        ]
    })


def perform_web_search(query: str, max_results: int = 5) -> str:
    """
    Perform a web search using Claude's web search tool.
    
    Args:
        query: The search query
        max_results: Maximum number of results to summarize
        
    Returns:
        A formatted string with search results and citations
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return "Error: ANTHROPIC_API_KEY environment variable not set"
    
    try:
        client = Anthropic(api_key=api_key)
        
        response = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=2048,
            tools=[{
                "type": "web_search_20250305",
                "name": "web_search",
                "max_uses": 3
            }],
            messages=[{
                "role": "user",
                "content": f"""Search the web for: {query}

Provide a concise summary of the most relevant information found.
Include specific details, code examples if relevant, and cite your sources.
Focus on the top {max_results} most relevant results."""
            }]
        )
        
        # Extract the text response
        result_text = ""
        citations = []
        
        for block in response.content:
            if hasattr(block, "text"):
                result_text += block.text
            if hasattr(block, "citations"):
                for citation in block.citations:
                    if hasattr(citation, "url") and hasattr(citation, "title"):
                        citations.append(f"- [{citation.title}]({citation.url})")
        
        # Format the response
        formatted_result = f"## Web Search Results for: {query}\n\n{result_text}"
        
        if citations:
            formatted_result += "\n\n### Sources:\n" + "\n".join(set(citations))
        
        return formatted_result
        
    except Exception as e:
        return f"Error performing web search: {str(e)}"


def handle_tools_call(request_id: str, params: dict) -> dict:
    """Handle the tools/call request."""
    tool_name = params.get("name")
    arguments = params.get("arguments", {})
    
    if tool_name != "search":
        return create_mcp_error(request_id, -32601, f"Unknown tool: {tool_name}")
    
    query = arguments.get("query")
    if not query:
        return create_mcp_error(request_id, -32602, "Missing required parameter: query")
    
    max_results = arguments.get("max_results", 5)
    
    # Perform the search
    result = perform_web_search(query, max_results)
    
    return create_mcp_response(request_id, {
        "content": [
            {
                "type": "text",
                "text": result
            }
        ]
    })


def main():
    """Main loop for the MCP server using stdio transport."""
    # Read JSON-RPC messages from stdin, write responses to stdout
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break
            
            # Parse the JSON-RPC request
            try:
                request = json.loads(line.strip())
            except json.JSONDecodeError:
                continue
            
            request_id = request.get("id")
            method = request.get("method")
            params = request.get("params", {})
            
            # Handle different methods
            if method == "initialize":
                response = handle_initialize(request_id)
            elif method == "notifications/initialized":
                # This is a notification, no response needed
                continue
            elif method == "tools/list":
                response = handle_tools_list(request_id)
            elif method == "tools/call":
                response = handle_tools_call(request_id, params)
            else:
                # For unknown methods, return empty result
                response = create_mcp_response(request_id, {})
            
            # Write response to stdout
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
            
        except Exception as e:
            # Log errors to stderr (won't interfere with MCP protocol)
            sys.stderr.write(f"Error: {str(e)}\n")
            sys.stderr.flush()


if __name__ == "__main__":
    main()
