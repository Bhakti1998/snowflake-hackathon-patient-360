"""Transport-independent parsing of public Cortex Agent events."""

import json
import re
from typing import Any, Dict

SCOPE_REFUSAL = "I can summarize synthetic evidence only; I cannot diagnose or recommend treatment."
DISCLAIMER = ("This is synthetic data. The risk score is a demonstration rule, "
              "not a validated clinical model.")


def public(value: Any) -> Any:
    if isinstance(value, dict):
        if value.get("type") in {"thinking", "reasoning", "thinking_delta"}:
            return None
        return {k: public(v) for k, v in value.items()
                if k.lower() not in {"think", "thinking", "reasoning", "signature"}}
    if isinstance(value, list):
        return [clean for v in value if (clean := public(v)) is not None]
    return value


def parse_response(content: Any) -> Dict:
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except json.JSONDecodeError:
            event = ""
            events = []
            for line in content.splitlines():
                if line.startswith("event:"):
                    event = line[6:].strip()
                elif line.startswith("data:") and line[5:].strip() != "[DONE]":
                    try:
                        events.append({"event": event, "data": json.loads(line[5:].strip())})
                    except json.JSONDecodeError:
                        raise RuntimeError("Agent response was truncated or malformed "
                                           "(request may have timed out); no answer was accepted")
            if not events:
                raise RuntimeError("Agent returned a non-JSON response (request may have timed out); "
                                   "no answer was accepted")
            content = events
    if isinstance(content, dict):
        if content.get("error"):
            raise RuntimeError(str(content["error"]))
        content = [{"event": "response", "data": content}]
    if not isinstance(content, list):
        raise RuntimeError("Unexpected Agent response format")
    texts, results, annotations = {}, [], []
    tool_warnings = []
    _USER_TOOLS = {"PatientAnalytics", "ClinicalDocumentSearch", "SharedEvidenceSearch"}
    final = None
    for item in content:
        event, data = item.get("event", ""), item.get("data", {})
        if isinstance(data, str):
            data = json.loads(data)
        if event in ("error", "response.error", "response.warning"):
            raise RuntimeError(f"Agent error/warning: {public(data)}")
        if event == "response.tool_result":
            if data.get("status") not in (None, "success"):
                name = data.get("name", "unknown")
                if name in _USER_TOOLS:
                    tool_warnings.append(f"{name} returned an error")
                continue
            results.append(public(data))
        elif event == "response.text.delta":
            index = data.get("content_index", 0)
            texts[index] = texts.get(index, "") + data.get("text", "")
        elif event == "response.text":
            texts[data.get("content_index", 0)] = data["text"]
            annotations.extend(data.get("annotations", []))
        elif event == "response.text.annotation":
            annotations.append(data["annotation"])
        elif event == "response":
            if data.get("warnings") or data.get("status") not in (None, "completed"):
                raise RuntimeError("Agent final response was incomplete or had warnings")
            final = data
    if final and "content" in final:
        final_texts = []
        for block in final["content"]:
            if block.get("type") == "text":
                final_texts.append(block.get("text", ""))
                annotations.extend(block.get("annotations", []))
            elif block.get("type") == "tool_result":
                result = block.get("tool_result", block)
                if result.get("status") not in (None, "success"):
                    name = result.get("name", "unknown")
                    if name in _USER_TOOLS:
                        tool_warnings.append(f"{name} returned an error")
                    continue
                clean = public(result)
                if clean not in results:
                    results.append(clean)
        if final_texts:
            texts = {0: "".join(final_texts)}
    text = "".join(texts[i] for i in sorted(texts))
    if not text:
        raise RuntimeError("Agent response contained no public answer text")
    if "reached the time limit" in text or text.startswith("Timed out"):
        raise RuntimeError("Cortex Agent hit its time budget before finishing; no answer was accepted")
    unique = {json.dumps(a, sort_keys=True): public(a) for a in annotations}
    return {"text": text, "tool_results": results, "annotations": list(unique.values()),
            "tool_warnings": tool_warnings}


_REQUIRED = ["Summary", "Key Evidence", "Risk Drivers", "Evidence Citations", "Limitations"]
_HEADING_RE = re.compile(
    r"^[ \t]*(#{1,3})\s*\**\s*(Summary|Key Evidence|Risk Drivers|Evidence Citations|Limitations)\s*\**[:\s]*$",
    re.MULTILINE | re.IGNORECASE,
)


def validate_format(text: str) -> str:
    """Validate five-section contract and return text with headings normalised to ``## Heading``."""
    found = _HEADING_RE.findall(text)
    matched = [h.title() for _, h in found]
    # Accept all 5 in correct order; also accept all 5 in any order (LLM reordering)
    if set(matched) != set(_REQUIRED):
        raise ValueError("Answer does not follow the exact five-section contract")
    # Normalise each heading line to strict ``## Heading`` form
    def _normalise(m: re.Match) -> str:
        return f"## {m.group(2).title()}"  # strips leading whitespace too
    text = _HEADING_RE.sub(_normalise, text)
    if not re.sub(r"\s+", " ", text).strip().endswith(DISCLAIMER):
        raise ValueError("The complete final synthetic/demo-risk disclaimer is missing")
    return text
