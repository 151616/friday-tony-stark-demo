"""File Tools (Phase 2 read + Phase 7 write/move/delete)."""
import os
import glob
import shutil
import logging
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from friday.config import FRIDAY_FILE_ROOTS

logger = logging.getLogger("friday-agent")

# Maximum allowed bytes for read_file to prevent blowing up LLM context.
MAX_READ_BYTES = 20 * 1024  # 20KB

# Pending confirmations: tool stores an action here, user confirms, then executes.
# Key = short confirmation code, value = (action, kwargs)
_PENDING_CONFIRMATIONS: dict[str, tuple[str, dict]] = {}

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

    # ------------------------------------------------------------------
    # Phase 7 — Write / Move / Delete (with confirmation)
    # ------------------------------------------------------------------

    @mcp.tool()
    def write_file(file_path: str, content: str) -> str:
        """Write text content to a file. Creates the file if it doesn't exist,
        overwrites if it does. The file must be inside an allowed directory."""
        target = _resolve_and_check(file_path)
        if not target:
            return f"Access denied: '{file_path}' is outside permitted directories."
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            logger.info("write_file: %s (%d bytes)", target, len(content))
            return f"Written to {target.name} ({len(content)} bytes)."
        except Exception as e:
            return f"Failed to write file: {e}"

    @mcp.tool()
    def create_folder(directory: str) -> str:
        """Create a new folder inside an allowed directory."""
        target = _resolve_and_check(directory)
        if not target:
            return f"Access denied: '{directory}' is outside permitted directories."
        if target.exists():
            return f"Folder '{target.name}' already exists."
        try:
            target.mkdir(parents=True, exist_ok=True)
            logger.info("create_folder: %s", target)
            return f"Created folder: {target.name}"
        except Exception as e:
            return f"Failed to create folder: {e}"

    @mcp.tool()
    def move_file(source: str, destination: str) -> str:
        """Move or rename a file/folder. Both paths must be inside allowed
        directories. Use this for renaming too — just change the filename
        in the destination. This is a DESTRUCTIVE action — ask for
        confirmation before calling."""
        src = _resolve_and_check(source)
        dst = _resolve_and_check(destination)
        if not src:
            return f"Access denied: source '{source}' is outside permitted directories."
        if not dst:
            return f"Access denied: destination '{destination}' is outside permitted directories."
        if not src.exists():
            return f"Source '{src.name}' does not exist."
        if dst.exists():
            return f"Destination '{dst.name}' already exists. Delete it first or choose a different name."
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            logger.info("move_file: %s → %s", src, dst)
            return f"Moved {src.name} to {dst.name}."
        except Exception as e:
            return f"Failed to move: {e}"

    @mcp.tool()
    def copy_file(source: str, destination: str) -> str:
        """Copy a file or folder. Both paths must be inside allowed directories."""
        src = _resolve_and_check(source)
        dst = _resolve_and_check(destination)
        if not src:
            return f"Access denied: source '{source}' is outside permitted directories."
        if not dst:
            return f"Access denied: destination '{destination}' is outside permitted directories."
        if not src.exists():
            return f"Source '{src.name}' does not exist."
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.is_dir():
                shutil.copytree(str(src), str(dst))
            else:
                shutil.copy2(str(src), str(dst))
            logger.info("copy_file: %s → %s", src, dst)
            return f"Copied {src.name} to {dst.name}."
        except Exception as e:
            return f"Failed to copy: {e}"

    @mcp.tool()
    def delete_file(file_path: str, confirm: bool = False) -> str:
        """Delete a file or folder. The path must be inside allowed directories.
        This is DESTRUCTIVE and IRREVERSIBLE. You MUST set confirm=True to
        actually delete. If confirm is false, just describe what would be
        deleted and ask the user to confirm."""
        target = _resolve_and_check(file_path)
        if not target:
            return f"Access denied: '{file_path}' is outside permitted directories."
        if not target.exists():
            return f"'{target.name}' does not exist."

        # Safety: never delete a root itself
        for root in FRIDAY_FILE_ROOTS:
            if target == root:
                return "I can't delete a root directory. That would be catastrophic, sir."

        if not confirm:
            if target.is_dir():
                count = sum(1 for _ in target.rglob("*"))
                return (f"This would delete the folder '{target.name}' and everything "
                        f"inside it ({count} items). Say 'yes, delete it' to confirm.")
            size = target.stat().st_size
            size_str = f"{size} bytes" if size < 1024 else f"{size / 1024:.1f} KB"
            return (f"This would delete '{target.name}' ({size_str}). "
                    f"Say 'yes, delete it' to confirm.")

        try:
            if target.is_dir():
                shutil.rmtree(str(target))
            else:
                target.unlink()
            logger.info("delete_file: %s (confirmed)", target)
            return f"Deleted {target.name}."
        except Exception as e:
            return f"Failed to delete: {e}"
