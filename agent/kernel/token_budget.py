# agent/kernel/token_budget.py

def estimate_tokens(text: str) -> int:
    """Returns estimated token count using a cheap heuristic (4 characters per token)."""
    return max(1, len(text) // 4)

def fit_to_budget(sections: list[tuple[str, str, int]], max_tokens: int) -> dict[str, str]:
    """
    Fits sections into a token budget based on priority.
    Input is a list of (section_name, content, priority), where priority 1 is most important.
    Returns a dict of {section_name: final_content} for sections that fit (fully or truncated).
    """
    # Sort sections by priority ascending
    sorted_sections = sorted(sections, key=lambda x: x[2])
    
    remaining_tokens = max_tokens
    result = {}
    
    for name, content, priority in sorted_sections:
        if remaining_tokens <= 0:
            # Budget exhausted, drop lower-priority sections entirely
            continue
            
        tokens = estimate_tokens(content)
        if tokens <= remaining_tokens:
            result[name] = content
            remaining_tokens -= tokens
        else:
            # Truncate to the remaining budget
            max_chars = remaining_tokens * 4
            if max_chars > 0:
                result[name] = content[:max_chars] + "\n[TRUNCATED]"
            remaining_tokens = 0
            
    return result
