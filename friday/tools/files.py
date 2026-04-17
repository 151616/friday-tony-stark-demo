"""File Read Tools (Phase 2)."""
import os
import glob
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from friday.config import FRIDAY_FILE_ROOTS

# Maximum allowed bytes for read_file to prevent blowing up LLM context.
MAX_READ_BYTES = 20 * 1024  # 20KB

def _resolve_and_check(raw_path: str) -> Path | None:
    """Resolve a raw path string, resolving aliases like 'Downloads', and check against security boundaries."""
    raw_path_lower = raw_path.lower().strip()
    
    # Handle natural language aliases
    if raw_path_lower in ["root", "workspace", "friday folder", "friday"]:
        target = FRIDAY_FILE_ROOTS[0]
    elif "documents" in raw_path_lower:
        target = FRIDAY_FILE_ROOTS[1]
    elif "downloads" in raw_path_lower:
        target = FRIDAY_FILE_ROOTS[2]
    else:
        target = Path(raw_path).resolve()
        
    # Security boundary check
    for root in FRIDAY_FILE_ROOTS:
        try:
            if root in target.parents or target == root:
                return target
        except Exception:
            continue
            
    return None

def register(mcp: FastMCP):
    
    @mcp.tool()
    def list_files(directory: str) -> str:
        """List files and folders inside an allowed directory.
        Supported aliases: 'Downloads', 'Documents', 'Friday' (root workspace)."""
        target = _resolve_and_check(directory)
        
        if not target:
            return f"Access Denied: The path '{directory}' is outside of my permitted sight lines."
            
        if not target.exists() or not target.is_dir():
            return f"Directory '{target}' does not exist or is not a folder."
            
        try:
            items = []
            for item in target.iterdir():
                prefix = "[D] " if item.is_dir() else "[F] "
                items.append(f"{prefix}{item.name}")
                
            if not items:
                return f"The directory '{target}' is empty."
                
            # Limit returned entries to avoid massive spam
            if len(items) > 50:
                summary = "\\n".join(items[:50])
                return f"Contents of {target} (Showing 50/{len(items)} items):\\n{summary}"
            return f"Contents of {target}:\\n" + "\\n".join(items)
        except Exception as e:
            return f"Failed to list directory: {e}"

    @mcp.tool()
    def read_file(file_path: str) -> str:
        """Read the text content of a specific file. Large files are safely truncated.
        Do NOT use this for binary files like images."""
        target = _resolve_and_check(file_path)
        
        if not target:
            return f"Access Denied: The file '{file_path}' is outside my permitted sight lines."
            
        if not target.is_file():
            return f"File '{target}' does not exist or is a directory."
            
        try:
            # Check size to avoid giant loading
            size = target.stat().st_size
            with open(target, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read(MAX_READ_BYTES)
                
            if size > MAX_READ_BYTES:
                return f"--- Content of {target.name} (Truncated after 20KB) ---\\n{content}\\n--- End ---"
            return f"--- Content of {target.name} ---\\n{content}\\n--- End ---"
        except Exception as e:
            return f"Failed to read file: {e}"

    @mcp.tool()
    def search_files(query: str, directory: str) -> str:
        """Perform a quick filename search for a keyword inside an allowed directory.
        Supported aliases: 'Downloads', 'Documents', 'Friday' (root workspace)."""
        target = _resolve_and_check(directory)
        
        if not target:
            return f"Access Denied: The directory '{directory}' is restricted."
            
        if not target.is_dir():
            return f"Directory '{target}' does not exist."
            
        try:
            results = []
            # Recursive glob query ignoring case locally
            search_pattern = target / "**" / f"*{query}*"
            
            for path_str in glob.iglob(str(search_pattern), recursive=True):
                path = Path(path_str)
                rel_path = path.relative_to(target)
                prefix = "[D]" if path.is_dir() else "[F]"
                results.append(f"{prefix} {rel_path}")
                if len(results) >= 20: 
                    break # Safe cap
                    
            if not results:
                return f"No results found for '{query}' in {target}."
                
            return f"Found {len(results)} matches for '{query}' in {target}:\\n" + "\\n".join(results)
        except Exception as e:
            return f"Failed to search: {e}"
