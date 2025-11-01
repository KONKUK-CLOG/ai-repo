"""MCP stdio-based JSON-RPC server skeleton."""
import asyncio
import json
import sys
import logging
from typing import Dict, Any, List
from src.mcp.tools import (
    post_blog_article,
    update_code_index,
    refresh_rag_indexes,
    publish_to_notion,
    create_commit_and_push
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Tool registry
TOOLS = [
    post_blog_article.TOOL,
    update_code_index.TOOL,
    refresh_rag_indexes.TOOL,
    publish_to_notion.TOOL,
    create_commit_and_push.TOOL,
]

TOOL_EXECUTORS = {
    "post_blog_article": post_blog_article.run,
    "update_code_index": update_code_index.run,
    "refresh_rag_indexes": refresh_rag_indexes.run,
    "publish_to_notion": publish_to_notion.run,
    "create_commit_and_push": create_commit_and_push.run,
}


class MCPServer:
    """Stdio-based MCP JSON-RPC server."""
    
    def __init__(self):
        self.initialized = False
    
    async def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle JSON-RPC request.
        
        Args:
            request: JSON-RPC request object
            
        Returns:
            JSON-RPC response object
        """
        method = request.get("method")
        params = request.get("params", {})
        request_id = request.get("id")
        
        try:
            if method == "initialize":
                return await self.initialize(request_id, params)
            elif method == "tools/list":
                return await self.list_tools(request_id)
            elif method == "tools/call":
                return await self.call_tool(request_id, params)
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32601,
                        "message": f"Method not found: {method}"
                    }
                }
        except Exception as e:
            logger.error(f"Error handling request: {e}")
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32603,
                    "message": f"Internal error: {str(e)}"
                }
            }
    
    async def initialize(self, request_id: int, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle initialize request.
        
        Args:
            request_id: JSON-RPC request ID
            params: Initialization parameters
            
        Returns:
            Initialization response
        """
        self.initialized = True
        logger.info("MCP server initialized")
        
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "1.0",
                "serverInfo": {
                    "name": "ts-llm-mcp-bridge",
                    "version": "1.0.0"
                },
                "capabilities": {
                    "tools": {}
                }
            }
        }
    
    async def list_tools(self, request_id: int) -> Dict[str, Any]:
        """Handle tools/list request.
        
        Args:
            request_id: JSON-RPC request ID
            
        Returns:
            List of available tools
        """
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "tools": TOOLS
            }
        }
    
    async def call_tool(self, request_id: int, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle tools/call request.
        
        Args:
            request_id: JSON-RPC request ID
            params: Tool call parameters (name, arguments)
            
        Returns:
            Tool execution result
        """
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        
        if tool_name not in TOOL_EXECUTORS:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32602,
                    "message": f"Tool not found: {tool_name}"
                }
            }
        
        try:
            executor = TOOL_EXECUTORS[tool_name]
            result = await executor(arguments)
            
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(result, indent=2)
                        }
                    ]
                }
            }
        except Exception as e:
            logger.error(f"Error executing tool {tool_name}: {e}")
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32603,
                    "message": f"Tool execution error: {str(e)}"
                }
            }
    
    async def run(self):
        """Run the stdio-based server loop."""
        logger.info("Starting MCP server on stdio")
        
        while True:
            try:
                # Read line from stdin
                line = await asyncio.get_event_loop().run_in_executor(
                    None, sys.stdin.readline
                )
                
                if not line:
                    break
                
                # Parse JSON-RPC request
                request = json.loads(line.strip())
                
                # Handle request
                response = await self.handle_request(request)
                
                # Write response to stdout
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()
                
            except json.JSONDecodeError as e:
                logger.error(f"JSON decode error: {e}")
            except KeyboardInterrupt:
                logger.info("Server interrupted")
                break
            except Exception as e:
                logger.error(f"Server error: {e}")


async def main():
    """Main entry point."""
    server = MCPServer()
    await server.run()


if __name__ == "__main__":
    asyncio.run(main())

