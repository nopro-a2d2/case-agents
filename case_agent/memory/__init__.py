"""Case-bound memory system: MEMORY.md index + frontmatter memory files.

See :mod:`case_agent.memory.memdir` for the public API.
"""

from .memdir import (
    MEMORY_DIR,
    MEMORY_INDEX,
    MEMORY_INDEX_MAX_BYTES,
    MEMORY_INDEX_MAX_LINES,
    MemoryEntry,
    MemoryType,
    list_memories,
    read_memory,
    read_memory_index,
    write_memory,
)

__all__ = [
    "MEMORY_DIR",
    "MEMORY_INDEX",
    "MEMORY_INDEX_MAX_BYTES",
    "MEMORY_INDEX_MAX_LINES",
    "MemoryEntry",
    "MemoryType",
    "list_memories",
    "read_memory",
    "read_memory_index",
    "write_memory",
]
