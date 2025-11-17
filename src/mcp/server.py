"""MCP stdio-based JSON-RPC server skeleton.

MCP (Model Context Protocol) 서버 구현
- stdio(표준 입출력) 기반 JSON-RPC 2.0 통신
- Claude Desktop 등 LLM 클라이언트와 통합
- 외부 도구(블로그 게시, Vector/Graph 검색) 호출 브릿지 역할

주요 기능:
- initialize: 서버 초기화 및 capability 협상
- tools/list: 사용 가능한 도구 목록 제공
- tools/call: 도구 실행 및 결과 반환

통신 방식:
- 입력: stdin으로 JSON-RPC 요청 수신 (한 줄씩)
- 출력: stdout으로 JSON-RPC 응답 전송 (한 줄씩)
- 각 메시지는 개행 문자로 구분

사용 예시:
    $ python src/mcp/server.py
    (stdin) {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
    (stdout) {"jsonrpc": "2.0", "id": 1, "result": {...}}
"""
import asyncio
import json
import sys
import logging
from typing import Dict, Any, List
from src.mcp.tools import (
    post_blog_article,
    search_vector_db,
    search_graph_db,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Tool registry (도구 레지스트리)
# 각 도구는 TOOL(메타데이터)과 run(실행 함수)를 제공
TOOLS = [
    post_blog_article.TOOL,       # 블로그 글 게시
    search_vector_db.TOOL,        # Vector DB 의미론적 검색
    search_graph_db.TOOL,         # Graph DB 구조적 검색
]

# Tool executors (도구 실행 함수 매핑)
# tool_name → async run(arguments) 함수
TOOL_EXECUTORS = {
    "post_blog_article": post_blog_article.run,
    "search_vector_db": search_vector_db.run,
    "search_graph_db": search_graph_db.run,
}


class MCPServer:
    """Stdio-based MCP JSON-RPC server.
    
    MCP 프로토콜을 구현하는 JSON-RPC 2.0 서버
    - stdio를 통한 양방향 통신
    - 비동기 처리로 도구 실행
    - 에러 처리 및 로깅
    """
    
    def __init__(self):
        """서버 인스턴스 초기화.
        
        initialized: 초기화 완료 여부 플래그
        """
        self.initialized = False
    
    async def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """JSON-RPC 요청을 처리하고 응답을 반환합니다.
        
        지원하는 메서드:
        - initialize: 서버 초기화 (capability 협상)
        - tools/list: 사용 가능한 도구 목록 반환
        - tools/call: 특정 도구 실행
        
        JSON-RPC 에러 코드:
        - -32601: Method not found (메서드를 찾을 수 없음)
        - -32603: Internal error (내부 에러)
        
        Args:
            request: JSON-RPC 요청 객체
                - jsonrpc: "2.0" (필수)
                - method: 메서드 이름 (필수)
                - params: 파라미터 객체 (선택)
                - id: 요청 ID (필수)
            
        Returns:
            JSON-RPC 응답 객체
                - jsonrpc: "2.0"
                - id: 요청 ID
                - result: 성공 시 결과 객체
                - error: 실패 시 에러 객체
        """
        method = request.get("method")
        params = request.get("params", {})
        request_id = request.get("id")
        
        try:
            # 메서드별 라우팅
            if method == "initialize":
                return await self.initialize(request_id, params)
            elif method == "tools/list":
                return await self.list_tools(request_id)
            elif method == "tools/call":
                return await self.call_tool(request_id, params)
            else:
                # 지원하지 않는 메서드
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32601,
                        "message": f"Method not found: {method}"
                    }
                }
        except Exception as e:
            # 예외 발생 시 내부 에러 반환
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
        """서버 초기화 요청을 처리합니다.
        
        클라이언트(예: Claude Desktop)와 서버 간 capability를 협상합니다.
        - 프로토콜 버전 확인
        - 서버 정보 전달 (이름, 버전)
        - 지원 기능 광고 (tools)
        
        초기화는 연결 후 한 번만 호출됩니다.
        
        Args:
            request_id: JSON-RPC 요청 ID
            params: 초기화 파라미터 (클라이언트 정보 등)
            
        Returns:
            초기화 응답
                - protocolVersion: MCP 프로토콜 버전
                - serverInfo: 서버 이름 및 버전
                - capabilities: 지원 기능 (tools)
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
                    "tools": {}  # 도구 실행 기능 지원
                }
            }
        }
    
    async def list_tools(self, request_id: int) -> Dict[str, Any]:
        """사용 가능한 도구 목록을 반환합니다.
        
        LLM이 어떤 도구를 사용할 수 있는지 알려줍니다.
        각 도구는 다음 정보를 포함:
        - name: 도구 이름
        - description: 도구 설명
        - inputSchema: 입력 파라미터 스키마 (JSON Schema)
        
        Args:
            request_id: JSON-RPC 요청 ID
            
        Returns:
            도구 목록 응답
                - tools: 도구 메타데이터 배열 (TOOLS)
        """
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "tools": TOOLS  # 전역 TOOLS 배열 반환
            }
        }
    
    async def call_tool(self, request_id: int, params: Dict[str, Any]) -> Dict[str, Any]:
        """도구 실행 요청을 처리합니다.
        
        LLM이 특정 도구를 호출할 때 사용됩니다.
        
        처리 플로우:
        1. tool_name과 arguments 추출
        2. 도구가 등록되어 있는지 확인
        3. TOOL_EXECUTORS에서 실행 함수 가져오기
        4. await executor(arguments) 비동기 실행
        5. 결과를 JSON 포맷으로 반환
        
        JSON-RPC 에러 코드:
        - -32602: Invalid params (도구를 찾을 수 없음)
        - -32603: Internal error (도구 실행 실패)
        
        Args:
            request_id: JSON-RPC 요청 ID
            params: 도구 호출 파라미터
                - name: 도구 이름 (필수)
                - arguments: 도구에 전달할 인자 객체 (선택)
            
        Returns:
            도구 실행 결과
                - content: 결과 배열 (MCP 표준 형식)
                    - type: "text"
                    - text: JSON 문자열 (결과 객체)
        """
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        
        # 도구 존재 여부 확인
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
            # 도구 실행 함수 가져오기 및 실행
            executor = TOOL_EXECUTORS[tool_name]
            result = await executor(arguments)
            
            # 성공 응답 반환 (MCP content 형식)
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(result, indent=2)  # 결과를 JSON 문자열로 변환
                        }
                    ]
                }
            }
        except Exception as e:
            # 도구 실행 실패 시 에러 반환
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
        """stdio 기반 서버 루프를 실행합니다.
        
        표준 입출력을 통한 양방향 통신:
        - stdin: JSON-RPC 요청 수신 (한 줄씩)
        - stdout: JSON-RPC 응답 전송 (한 줄씩)
        
        루프 동작:
        1. stdin에서 한 줄 읽기 (블로킹)
        2. JSON 파싱
        3. handle_request()로 처리
        4. stdout으로 응답 출력
        5. flush()로 즉시 전송
        6. 반복
        
        종료 조건:
        - stdin EOF (빈 줄)
        - KeyboardInterrupt (Ctrl+C)
        
        에러 처리:
        - JSON 파싱 에러는 로깅만 하고 계속 진행
        - 기타 에러도 로깅만 하고 계속 진행
        """
        logger.info("Starting MCP server on stdio")
        
        while True:
            try:
                # stdin에서 한 줄 읽기 (블로킹 작업이므로 executor 사용)
                line = await asyncio.get_event_loop().run_in_executor(
                    None, sys.stdin.readline
                )
                
                # EOF 확인 (빈 줄 = 연결 종료)
                if not line:
                    break
                
                # JSON-RPC 요청 파싱
                request = json.loads(line.strip())
                
                # 요청 처리
                response = await self.handle_request(request)
                
                # stdout으로 응답 출력 (JSON + 개행)
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()  # 버퍼 즉시 전송
                
            except json.JSONDecodeError as e:
                # JSON 파싱 실패 (잘못된 형식)
                logger.error(f"JSON decode error: {e}")
            except KeyboardInterrupt:
                # 사용자 중단 (Ctrl+C)
                logger.info("Server interrupted")
                break
            except Exception as e:
                # 기타 에러
                logger.error(f"Server error: {e}")


async def main():
    """메인 엔트리 포인트.
    
    MCP 서버 인스턴스를 생성하고 실행합니다.
    
    사용법:
        $ python src/mcp/server.py
        
    Claude Desktop 설정 (claude_desktop_config.json):
        {
          "mcpServers": {
            "ts-llm-bridge": {
              "command": "python",
              "args": ["src/mcp/server.py"]
            }
          }
        }
    """
    server = MCPServer()
    await server.run()


if __name__ == "__main__":
    # asyncio 이벤트 루프 시작 및 main() 실행
    asyncio.run(main())

