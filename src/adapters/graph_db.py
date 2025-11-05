"""Graph database adapter for code relationships."""
import logging
import ast
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime
from src.server.settings import settings

logger = logging.getLogger(__name__)

# Neo4j driver (lazy initialization)
_neo4j_driver = None


async def get_neo4j_driver():
    """Neo4j 드라이버 가져오기 (싱글톤)"""
    global _neo4j_driver
    
    if _neo4j_driver is None:
        try:
            from neo4j import AsyncGraphDatabase
            
            if not settings.GRAPH_DB_PASSWORD:
                logger.warning("GRAPH_DB_PASSWORD not set. Using dummy implementation.")
                return None
            
            _neo4j_driver = AsyncGraphDatabase.driver(
                settings.GRAPH_DB_URL,
                auth=(settings.GRAPH_DB_USER, settings.GRAPH_DB_PASSWORD)
            )
            
            # 연결 테스트
            await _neo4j_driver.verify_connectivity()
            logger.info("Neo4j driver initialized successfully")
            
        except ImportError:
            logger.warning("neo4j package not installed. Using dummy implementation.")
            _neo4j_driver = None
        except Exception as e:
            logger.error(f"Failed to initialize Neo4j driver: {e}")
            _neo4j_driver = None
    
    return _neo4j_driver


def parse_python_file(file_path: str, content: str) -> Dict[str, Any]:
    """Python 파일 파싱하여 함수/클래스 추출"""
    try:
        tree = ast.parse(content)
        entities = []
        imports = []
        
        for node in ast.walk(tree):
            # 함수 추출
            if isinstance(node, ast.FunctionDef):
                # 함수 호출 추출
                calls = []
                for child in ast.walk(node):
                    if isinstance(child, ast.Call):
                        if isinstance(child.func, ast.Name):
                            calls.append(child.func.id)
                        elif isinstance(child.func, ast.Attribute):
                            calls.append(child.func.attr)
                
                entities.append({
                    "type": "function",
                    "name": node.name,
                    "line_start": node.lineno,
                    "line_end": node.end_lineno or node.lineno,
                    "calls": list(set(calls))  # 중복 제거
                })
            
            # 클래스 추출
            elif isinstance(node, ast.ClassDef):
                # 메서드 추출
                methods = [
                    m.name for m in node.body
                    if isinstance(m, ast.FunctionDef)
                ]
                
                entities.append({
                    "type": "class",
                    "name": node.name,
                    "line_start": node.lineno,
                    "line_end": node.end_lineno or node.lineno,
                    "methods": methods
                })
            
            # Import 추출
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)
        
        return {
            "file": file_path,
            "entities": entities,
            "imports": list(set(imports))
        }
        
    except SyntaxError as e:
        logger.warning(f"Syntax error in {file_path}: {e}")
        return {"file": file_path, "entities": [], "imports": []}
    except Exception as e:
        logger.error(f"Failed to parse {file_path}: {e}")
        return {"file": file_path, "entities": [], "imports": []}


async def update_code_graph(files: List[str], contents: Optional[Dict[str, str]] = None, user_id: int = 0) -> int:
    """Update code graph with file changes.
    
    Creates/updates nodes and relationships for code entities.
    다중 사용자 지원: 모든 노드에 user_id 속성을 추가하여 데이터를 격리합니다.
    
    Args:
        files: List of file paths that changed
        contents: Optional dict of {file_path: file_content}
        user_id: 사용자 ID (데이터 격리용, 기본값 0은 레거시 데이터용)
        
    Returns:
        Number of graph nodes updated
    """
    if not files:
        return 0
    
    logger.info(f"Updating code graph for {len(files)} files")
    
    driver = await get_neo4j_driver()
    
    if driver is None:
        # Dummy mode
        logger.warning("Graph DB driver not available. Using dummy implementation.")
        return len(files)
    
    try:
        nodes_updated = 0
        
        async with driver.session() as session:
            for file_path in files:
                try:
                    # 1. 파일 노드 생성/업데이트 (MERGE = Upsert)
                    # user_id를 포함하여 사용자별로 고유한 노드 생성
                    await session.run("""
                        MERGE (f:File {path: $path, user_id: $user_id})
                        SET f.updated_at = $updated_at
                        """,
                        path=file_path,
                        user_id=user_id,
                        updated_at=datetime.now().isoformat()
                    )
                    nodes_updated += 1
                    
                    # 2. 파일 내용이 제공된 경우 파싱
                    if contents and file_path in contents:
                        content = contents[file_path]
                        
                        # Python 파일만 파싱
                        if file_path.endswith('.py'):
                            parsed = parse_python_file(file_path, content)
                            
                            # 3. 엔티티 (함수/클래스) 노드 생성
                            for entity in parsed["entities"]:
                                await session.run("""
                                    MERGE (e:Entity {name: $name, file: $file, user_id: $user_id})
                                    SET e.type = $type,
                                        e.line_start = $line_start,
                                        e.line_end = $line_end,
                                        e.updated_at = $updated_at
                                    """,
                                    name=entity["name"],
                                    file=file_path,
                                    user_id=user_id,
                                    type=entity["type"],
                                    line_start=entity["line_start"],
                                    line_end=entity["line_end"],
                                    updated_at=datetime.now().isoformat()
                                )
                                
                                # 4. 파일 → 엔티티 관계 (user_id로 필터링)
                                await session.run("""
                                    MATCH (f:File {path: $file, user_id: $user_id})
                                    MATCH (e:Entity {name: $name, file: $file, user_id: $user_id})
                                    MERGE (f)-[:CONTAINS]->(e)
                                    """,
                                    file=file_path,
                                    user_id=user_id,
                                    name=entity["name"]
                                )
                                
                                # 5. 함수 호출 관계 (user_id로 필터링)
                                if entity["type"] == "function":
                                    for called in entity.get("calls", []):
                                        # 같은 파일 내 함수 호출만 연결 (단순화)
                                        await session.run("""
                                            MATCH (caller:Entity {name: $caller, file: $file, user_id: $user_id})
                                            MATCH (callee:Entity {name: $callee, file: $file, user_id: $user_id})
                                            MERGE (caller)-[:CALLS]->(callee)
                                            """,
                                            caller=entity["name"],
                                            callee=called,
                                            file=file_path,
                                            user_id=user_id
                                        )
                            
                            # 6. Import 관계 (user_id로 필터링)
                            for imported in parsed["imports"]:
                                await session.run("""
                                    MATCH (f:File {path: $file, user_id: $user_id})
                                    MERGE (m:Module {name: $module, user_id: $user_id})
                                    MERGE (f)-[:IMPORTS]->(m)
                                    """,
                                    file=file_path,
                                    user_id=user_id,
                                    module=imported
                                )
                    
                except Exception as e:
                    logger.error(f"Failed to update graph for {file_path}: {e}")
                    continue
        
        logger.info(f"Successfully updated {nodes_updated} file nodes in Neo4j")
        return nodes_updated
        
    except Exception as e:
        logger.error(f"Failed to update code graph: {e}")
        raise


async def delete_file_nodes(files: List[str], user_id: int = 0) -> int:
    """Graph DB에서 파일 노드 삭제.
    
    다중 사용자 지원: user_id로 필터링하여 해당 사용자의 파일만 삭제합니다.
    
    Args:
        files: 삭제할 파일 경로 리스트
        user_id: 사용자 ID (기본값 0은 레거시 데이터용)
        
    Returns:
        삭제된 파일 노드 수
    """
    if not files:
        return 0
    
    logger.info(f"Deleting {len(files)} file nodes from graph DB")
    
    driver = await get_neo4j_driver()
    
    if driver is None:
        logger.warning("Graph DB driver not available. Using dummy implementation.")
        return len(files)
    
    try:
        async with driver.session() as session:
            for file_path in files:
                # 파일 노드와 관련 엔티티 모두 삭제 (user_id로 필터링)
                await session.run("""
                    MATCH (f:File {path: $path, user_id: $user_id})
                    OPTIONAL MATCH (f)-[:CONTAINS]->(e:Entity {user_id: $user_id})
                    DETACH DELETE f, e
                    """,
                    path=file_path,
                    user_id=user_id
                )
        
        logger.info(f"Successfully deleted {len(files)} file nodes from Neo4j")
        return len(files)
        
    except Exception as e:
        logger.error(f"Failed to delete file nodes: {e}")
        raise


async def search_related_code(
    query: str,
    user_id: int,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """Search for related code entities and their relationships in graph DB.
    
    사용자의 쿼리를 바탕으로 관련된 코드 엔티티(함수, 클래스)와 파일을 검색합니다.
    키워드 매칭 및 관계 기반 검색을 수행합니다.
    
    Args:
        query: Search query (keywords to match against entity names)
        user_id: User ID for filtering
        limit: Maximum number of results to return
        
    Returns:
        List of related code entities with their relationships
    """
    logger.info(f"Searching graph DB for user {user_id}: {query[:100]}")
    
    driver = await get_neo4j_driver()
    
    if driver is None:
        logger.warning("Graph DB driver not available. Returning empty results.")
        return []
    
    try:
        # Extract keywords from query (simple tokenization)
        keywords = [word.lower() for word in query.split() if len(word) > 2]
        if not keywords:
            return []
        
        results = []
        
        async with driver.session() as session:
            # Search for entities matching keywords
            for keyword in keywords[:5]:  # Limit to first 5 keywords
                # Use case-insensitive regex matching
                cypher_query = """
                MATCH (e:Entity {user_id: $user_id})
                WHERE toLower(e.name) CONTAINS toLower($keyword)
                OPTIONAL MATCH (f:File {user_id: $user_id})-[:CONTAINS]->(e)
                OPTIONAL MATCH (e)-[r:CALLS]->(called:Entity {user_id: $user_id})
                RETURN e.name as entity_name,
                       e.type as entity_type,
                       e.line_start as line_start,
                       e.line_end as line_end,
                       f.path as file_path,
                       collect(DISTINCT called.name) as calls
                LIMIT $limit
                """
                
                result = await session.run(
                    cypher_query,
                    user_id=user_id,
                    keyword=keyword,
                    limit=limit
                )
                
                async for record in result:
                    entity_name = record["entity_name"]
                    entity_type = record["entity_type"]
                    file_path = record["file_path"]
                    line_start = record["line_start"]
                    line_end = record["line_end"]
                    calls = record["calls"] or []
                    
                    # Build description
                    description = f"{entity_type.capitalize()}: {entity_name}"
                    if calls:
                        description += f" (calls: {', '.join(calls[:3])})"
                    
                    results.append({
                        "file": file_path or "unknown",
                        "entity_name": entity_name,
                        "entity_type": entity_type,
                        "line_start": line_start,
                        "line_end": line_end,
                        "calls": calls,
                        "description": description,
                        "keyword_matched": keyword
                    })
        
        # Deduplicate results
        seen = set()
        unique_results = []
        for result in results:
            key = (result["file"], result["entity_name"])
            if key not in seen:
                seen.add(key)
                unique_results.append(result)
        
        logger.info(f"Found {len(unique_results)} related code entities in graph DB")
        return unique_results[:limit]
        
    except Exception as e:
        logger.error(f"Failed to search graph DB: {e}")
        return []


async def refresh_graph_indexes() -> Dict[str, Any]:
    """Refresh graph database indexes.
    
    Returns:
        Refresh statistics
    """
    logger.info("Refreshing graph database indexes")
    logger.info(f"Graph DB URL: {settings.GRAPH_DB_URL}")
    
    # Dummy implementation
    return {
        "indexes_refreshed": ["file_path", "entity_name"],
        "nodes_count": 500,
        "relationships_count": 1200,
        "success": True
    }

