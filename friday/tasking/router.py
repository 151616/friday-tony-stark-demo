"""Task routing logic."""
import re
from typing import Literal
from friday.config import TASK_MODE_ENABLED

_TASK_KEYWORDS = [
    r"\bhandle it\b",
    r"\bwork on it\b",
    r"\bresearch (it|this|that)\b",
    r"\bdo this in the background\b",
    r"\bin the background\b",
    r"\blook (it )?up\b",
]

def classify_request(text: str) -> Literal["fast", "slow", "task"]:
    """Classify the incoming natural language request."""
    if not TASK_MODE_ENABLED:
        return "fast"
        
    text_lower = text.lower()
    
    for pattern in _TASK_KEYWORDS:
        if re.search(pattern, text_lower):
            return "task"
            
    # For now, everything else goes to the fast path.
    return "fast"
