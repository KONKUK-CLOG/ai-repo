"""Tool for creating git commits and pushing to remote."""
from typing import Dict, Any, List, Optional
from src.adapters import github

TOOL = {
    "name": "create_commit_and_push",
    "title": "Create Commit and Push",
    "description": "Create a git commit and push to remote repository",
    "input_schema": {
        "type": "object",
        "properties": {
            "repo_path": {
                "type": "string",
                "description": "Local repository path"
            },
            "files": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of file paths to commit"
            },
            "commit_message": {
                "type": "string",
                "description": "Commit message"
            },
            "branch": {
                "type": "string",
                "description": "Optional branch name (defaults to current)"
            }
        },
        "required": ["repo_path", "files", "commit_message"]
    }
}


async def run(params: Dict[str, Any]) -> Dict[str, Any]:
    """Execute the tool.
    
    Args:
        params: Tool parameters (repo_path, files, commit_message, branch)
        
    Returns:
        Execution result
    """
    repo_path = params.get("repo_path")
    files = params.get("files", [])
    commit_message = params.get("commit_message")
    branch = params.get("branch")
    
    result = await github.create_commit_and_push(
        repo_path=repo_path,
        files=files,
        commit_message=commit_message,
        branch=branch
    )
    
    return {
        "success": True,
        "commit": result
    }

