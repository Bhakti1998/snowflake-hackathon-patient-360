"""Page-local, measured chunks using a declared tokenizer."""

import re
from typing import Callable, Dict, List


def split_page(text: str, count_tokens: Callable[[str], int],
               maximum: int = 800, overlap: int = 75) -> List[Dict[str, object]]:
    if not 500 <= maximum <= 900 or not 50 <= overlap <= 100:
        raise ValueError("Chunk settings must honor the approved token ranges")
    words = list(re.finditer(r"\S+", text))
    if not words:
        raise ValueError("Parsed page has no text")
    result = []
    start = 0
    while start < len(words):
        lo, hi = start + 1, len(words)
        end = start
        while lo <= hi:
            mid = (lo + hi) // 2
            candidate = text[words[start].start():words[mid - 1].end()]
            if count_tokens(candidate) <= maximum:
                end = mid
                lo = mid + 1
            else:
                hi = mid - 1
        if end == start:
            raise ValueError("Single text token exceeds chunk limit; cannot preserve source span")
        chunk = text[words[start].start():words[end - 1].end()]
        tokens = count_tokens(chunk)
        result.append({"text": chunk, "tokens": tokens, "start": words[start].start(),
                       "end": words[end - 1].end(),
                       "exception": "SHORT_PAGE" if len(result) == 0 and end == len(words) and tokens < 500
                       else "RESIDUAL" if tokens < 500 else None,
                       "overlap_tokens": 0})
        if end == len(words):
            break
        next_start = end
        for candidate_start in range(end - 1, start, -1):
            n = count_tokens(text[words[candidate_start].start():words[end - 1].end()])
            if n >= overlap:
                if n > 100:
                    raise ValueError("Cannot construct overlap within 50-100 tokens")
                next_start = candidate_start
                break
        if next_start == end:
            raise ValueError("Cannot construct required overlap")
        result[-1]["overlap_tokens"] = count_tokens(text[words[next_start].start():words[end - 1].end()])
        start = next_start
    return result
