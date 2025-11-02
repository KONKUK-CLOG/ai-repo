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


async def update_code_graph(files: List[str], contents: Optional[Dict[str, str]] = None) -> int:
    """Update code graph with file changes.
    
    Creates/updates nodes and relationships for code entities.
    
    Args:
        files: List of file paths that changed
        contents: Optional dict of {file_path: file_content}
        
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
                    await session.run("""
                        MERGE (f:File {path: $path})
                        SET f.updated_at = $updated_at
                        """,
                        path=file_path,
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
                                    MERGE (e:Entity {name: $name, file: $file})
                                    SET e.type = $type,
                                        e.line_start = $line_start,
                                        e.line_end = $line_end,
                                        e.updated_at = $updated_at
                                    """,
                                    name=entity["name"],
                                    file=file_path,
                                    type=entity["type"],
                                    line_start=entity["line_start"],
                                    line_end=entity["line_end"],
                                    updated_at=datetime.now().isoformat()
                                )
                                
                                # 4. 파일 → 엔티티 관계
                                await session.run("""
                                    MATCH (f:File {path: $file})
                                    MATCH (e:Entity {name: $name, file: $file})
                                    MERGE (f)-[:CONTAINS]->(e)
                                    """,
                                    file=file_path,
                                    name=entity["name"]
                                )
                                
                                # 5. 함수 호출 관계
                                if entity["type"] == "function":
                                    for called in entity.get("calls", []):
                                        # 같은 파일 내 함수 호출만 연결 (단순화)
                                        await session.run("""
                                            MATCH (caller:Entity {name: $caller, file: $file})
                                            MATCH (callee:Entity {name: $callee, file: $file})
                                            MERGE (caller)-[:CALLS]->(callee)
                                            """,
                                            caller=entity["name"],
                                            callee=called,
                                            file=file_path
                                        )
                            
                            # 6. Import 관계
                            for imported in parsed["imports"]:
                                await session.run("""
                                    MATCH (f:File {path: $file})
                                    MERGE (m:Module {name: $module})
                                    MERGE (f)-[:IMPORTS]->(m)
                                    """,
                                    file=file_path,
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


async def delete_file_nodes(files: List[str]) -> int:
    """Graph DB에서 파일 노드 삭제"""
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
                # 파일 노드와 관련 엔티티 모두 삭제
                await session.run("""
                    MATCH (f:File {path: $path})
                    OPTIONAL MATCH (f)-[:CONTAINS]->(e:Entity)
                    DETACH DELETE f, e
                    """,
                    path=file_path
                )
        
        logger.info(f"Successfully deleted {len(files)} file nodes from Neo4j")
        return len(files)
        
    except Exception as e:
        logger.error(f"Failed to delete file nodes: {e}")
        raise


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

