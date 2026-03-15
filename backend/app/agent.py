from google import genai
from google.genai import types
import os
import json
import base64
import re
import io
from PIL import Image
from typing import Any, Dict, List, Optional


ALLOWED_ACTION_TYPES = {"click", "scroll", "type", "none", "keypress"}

ACTION_RESPONSE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "propertyOrdering": [
        "goal",
        "status",
        "screen_summary",
        "next_action",
        "needs_confirmation",
        "reason",
    ],
    "required": [
        "goal",
        "status",
        "screen_summary",
        "next_action",
        "needs_confirmation",
        "reason",
    ],
    "properties": {
        "goal": {"type": "string"},
        "status": {
            "type": "string",
            "enum": ["in_progress", "completed", "blocked"]
        },
        "screen_summary": {"type": "string"},
        "next_action": {
            "type": "object",
            "propertyOrdering": [
                "type",
                "target_description",
                "x",
                "y",
                "text",
                "direction",
                "amount",
                "key",
                "bbox",
            ],
            "required": ["type"],
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ["click", "scroll", "type", "none", "keypress"]
                },
                "target_description": {"type": "string", "nullable": True},
                "x": {"type": "integer", "nullable": True},
                "y": {"type": "integer", "nullable": True},
                "text": {"type": "string", "nullable": True},
                "direction": {
                    "type": "string",
                    "enum": ["up", "down", "left", "right"],
                    "nullable": True,
                },
                "amount": {"type": "integer", "nullable": True},
                "key": {"type": "string", "nullable": True},
                "bbox": {
                    "type": "object",
                    "nullable": True,
                    "required": ["x1", "y1", "x2", "y2"],
                    "properties": {
                        "x1": {"type": "integer"},
                        "y1": {"type": "integer"},
                        "x2": {"type": "integer"},
                        "y2": {"type": "integer"},
                    },
                },
            },
        },
        "needs_confirmation": {"type": "boolean"},
        "reason": {"type": "string"},
    },
}


def _get_client() -> genai.Client:
    project = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")

    if not project:
        raise ValueError(
            "GOOGLE_CLOUD_PROJECT is not set. "
            "Set it in your .env or shell before starting FastAPI."
        )

    return genai.Client(
        vertexai=True,
        project=project,
        location=location,
    )


def _decode_screenshot(screenshot: str) -> bytes:
    if "," in screenshot:
        screenshot = screenshot.split(",", 1)[1]
    return base64.b64decode(screenshot)


def _resize_image(image_bytes: bytes, max_dimension: int = 1024) -> bytes:
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            width, height = img.size
            if max(width, height) <= max_dimension:
                return image_bytes
            
            ratio = max_dimension / max(width, height)
            new_size = (int(width * ratio), int(height * ratio))
            
            img = img.resize(new_size, Image.Resampling.LANCZOS)
            
            out_buffer = io.BytesIO()
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            
            img.save(out_buffer, format="JPEG", quality=85)
            # print(f"Resized image from {width}x{height} to {new_size}")
            return out_buffer.getvalue()
    except Exception as e:
        # print(f"Resize failed: {e}")
        return image_bytes


def _safe_json_load(text: str) -> Dict[str, Any]:
    text = text.strip()
    text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(text)


def _center_from_bbox(bbox: Dict[str, Any]) -> Dict[str, int]:
    x1 = int(bbox["x1"])
    y1 = int(bbox["y1"])
    x2 = int(bbox["x2"])
    y2 = int(bbox["y2"])
    return {
        "x": int((x1 + x2) / 2),
        "y": int((y1 + y2) / 2),
    }


def _normalize_text_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _extract_quoted_text(command: str) -> Optional[str]:
    matches = re.findall(r'"([^"]+)"|\'([^\']+)\'', command)
    for pair in matches:
        value = pair[0] or pair[1]
        if value and value.strip():
            return value.strip()
    return None


def _clean_trailing_followups(text: str) -> str:
    text = text.strip()
    
    # We strip by common textual divisions that indicate multi-step instructions.
    dividers = [
        ", and ", ", then ", " and ", " then ", " if ", ". if ", 
        ". ", ", click", ", open", ", select", ", go ", ", navigate", 
        ", scroll", " to open", " to click", " out"
    ]
    
    lower_text = text.lower()
    best_idx = len(text)
    
    for div in dividers:
        idx = lower_text.find(div)
        if idx != -1 and idx < best_idx:
            best_idx = idx
            
    cleaned = text[:best_idx].strip(" '\"")
    return cleaned

def _extract_search_text(command: str) -> Optional[str]:
    quoted = _extract_quoted_text(command)
    if quoted:
        return _clean_trailing_followups(quoted)

    m = re.search(r"\bsearch\s+(?:for\s+)?(.+)$", command.strip(), flags=re.IGNORECASE)
    if m:
        return _clean_trailing_followups(m.group(1))

    return None

def _extract_fill_details(command: str) -> Dict[str, Optional[str]]:
    original = command.strip()

    patterns = [
        r"fill\s+(.+?)\s+as\s+(.+)$",
        r"enter\s+(.+?)\s+as\s+(.+)$",
        r"type\s+(.+?)\s+in\s+(.+)$",
        r"fill\s+the\s+(.+?)\s+with\s+(.+)$",
    ]

    for pattern in patterns:
        m = re.search(pattern, original, flags=re.IGNORECASE)
        if m:
            first = m.group(1).strip(" '\"")
            second = m.group(2).strip(" '\"")

            if " in " in pattern:
                return {"field_name": second, "field_value": _clean_trailing_followups(first)}

            return {"field_name": first, "field_value": _clean_trailing_followups(second)}

    return {"field_name": None, "field_value": None}

def _extract_click_target(command: str) -> Optional[str]:
    patterns = [
        r"^(click|open|tap|select|choose|focus on|focus)\s+(.+)$",
        r"^(press)\s+(.+)$",
    ]
    for pattern in patterns:
        m = re.match(pattern, command.strip(), flags=re.IGNORECASE)
        if m:
            return _clean_trailing_followups(m.group(2))
    return None

def _extract_type_text(command: str) -> Optional[str]:
    quoted = _extract_quoted_text(command)
    if quoted and re.match(r"^(type|enter|write|input)\b", command.strip(), flags=re.IGNORECASE):
        return quoted

    patterns = [
        r"^type\s+(.+)$",
        r"^enter\s+(.+)$",
        r"^write\s+(.+)$",
        r"^input\s+(.+)$",
    ]
    for pattern in patterns:
        m = re.match(pattern, command.strip(), flags=re.IGNORECASE)
        if m:
            return _clean_trailing_followups(m.group(1))
    return None

def _parse_command(command: str) -> Dict[str, Any]:
    cmd = _normalize_text_spaces(command)
    cmd_lower = cmd.lower()

    search_text = _extract_search_text(cmd)
    fill = _extract_fill_details(cmd)
    click_target = _extract_click_target(cmd)
    type_text = _extract_type_text(cmd)

    # Detect multi-step instructions gracefully.
    is_multi_step = bool(
        re.search(r"[\s,]+(?:and|then|,|\.|\bif\b)?\s*(navigate|click|open|select|go to|choose|scroll)\b", cmd_lower)
    )
    open_first_link = bool(
        re.search(r"\b(open|click|select)\s+(the\s+)?first\s+(link|result)\b", cmd_lower)
    )

    if search_text and open_first_link:
        return {
            "task_type": "search_and_open_first_result",
            "search_text": search_text,
            "follow_up_action": "open_first_result",
            "primary_target": "search bar",
            "field_name": None,
            "field_value": None,
            "type_text": search_text,
        }

    if search_text:
        return {
            "task_type": "search_multi_step" if is_multi_step else "search_only",
            "search_text": search_text,
            "follow_up_action": "llm_decide" if is_multi_step else "submit_search",
            "primary_target": "search bar",
            "field_name": None,
            "field_value": None,
            "type_text": search_text,
        }

    if fill["field_name"] and fill["field_value"]:
        return {
            "task_type": "fill_field",
            "search_text": None,
            "follow_up_action": None,
            "primary_target": fill["field_name"],
            "field_name": fill["field_name"],
            "field_value": fill["field_value"],
            "type_text": fill["field_value"],
        }

    if type_text:
        return {
            "task_type": "type_text",
            "search_text": None,
            "follow_up_action": None,
            "primary_target": "input field",
            "field_name": None,
            "field_value": None,
            "type_text": type_text,
        }

    if click_target:
        return {
            "task_type": "click_target",
            "search_text": None,
            "follow_up_action": None,
            "primary_target": click_target,
            "field_name": None,
            "field_value": None,
            "type_text": None,
        }

    if cmd_lower.startswith(("scroll ", "go down", "go up")):
        return {
            "task_type": "scroll",
            "search_text": None,
            "follow_up_action": None,
            "primary_target": None,
            "field_name": None,
            "field_value": None,
            "type_text": None,
        }

    return {
        "task_type": "general",
        "search_text": None,
        "follow_up_action": None,
        "primary_target": None,
        "field_name": None,
        "field_value": None,
        "type_text": None,
    }


def _extract_action_mode(parsed_command: Dict[str, Any]) -> str:
    task_type = parsed_command["task_type"]

    if task_type in {"type_text", "fill_field"}:
        return "type"
    if task_type in {"search_only", "search_and_open_first_result", "search_multi_step"}:
        return "search"
    if task_type == "scroll":
        return "scroll"
    if task_type == "click_target":
        return "click"
    return "general"


def _format_memory(memory: Optional[Dict[str, Any]]) -> str:
    if not memory or not memory.get("history"):
        return "No previous action history."

    compact_items: List[str] = []
    for item in memory.get("history", [])[-5:]:
        compact_items.append(json.dumps({
            "step": item.get("step"),
            "action": item.get("action") or {},
            "screen_summary": item.get("screen_summary"),
            "result_summary": item.get("result_summary"),
        }, ensure_ascii=False))

    return "\n".join(compact_items)


def _recent_history(memory: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not memory or not memory.get("history"):
        return []
    return memory.get("history", [])


def _recent_actions(memory: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [(item.get("action") or {}) for item in _recent_history(memory)[-5:]]


def _infer_task_phase(parsed_command: Dict[str, Any], memory: Optional[Dict[str, Any]]) -> str:
    history = _recent_history(memory)
    actions = _recent_actions(memory)
    summaries = " ".join(
        [str(item.get("screen_summary") or "") + " " + str(item.get("result_summary") or "") for item in history]
    ).lower()

    task_type = parsed_command["task_type"]

    has_click = any(a.get("type") == "click" for a in actions)
    has_keypress_enter = any(a.get("type") == "keypress" and str(a.get("key", "")).lower() == "enter" for a in actions)
    has_scroll = any(a.get("type") == "scroll" for a in actions)

    typed_query = parsed_command.get("search_text") or parsed_command.get("type_text") or parsed_command.get("field_value")
    has_type_of_expected_text = any(
        a.get("type") == "type" and _normalize_text_spaces(str(a.get("text") or "")).lower() ==
        _normalize_text_spaces(str(typed_query or "")).lower() for a in actions
    )

    if "search" in task_type:
        if not has_type_of_expected_text:
            return "type_search"
        if not has_keypress_enter:
            return "submit_search"
        if task_type == "search_only":
            return "done"
        return "general"  # Multi-step instructions hand over to vision model natural workflow

    if task_type in {"fill_field", "type_text"}:
        if not has_type_of_expected_text:
            return "type_field"
        return "done"

    if task_type == "click_target":
        if has_click:
            return "done"
        return "click_target"

    if task_type == "scroll":
        if has_scroll:
            return "done"
        return "scroll"

    return "general"


def _normalize_action_response(data: Dict[str, Any], command: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "goal": data.get("goal") or command,
        "status": data.get("status") or "in_progress",
        "screen_summary": _normalize_text_spaces(data.get("screen_summary") or ""),
        "next_action": data.get("next_action") or {"type": "none"},
        "needs_confirmation": bool(data.get("needs_confirmation", False)),
        "reason": _normalize_text_spaces(data.get("reason") or ""),
    }

    next_action = result["next_action"]
    action_type = next_action.get("type", "none")

    if action_type not in ALLOWED_ACTION_TYPES:
        result["status"] = "blocked"
        result["next_action"] = {"type": "none"}
        result["reason"] = f"Unsupported action type '{action_type}'."
        return result

    bbox = next_action.get("bbox")
    if bbox:
        center = _center_from_bbox(bbox)
        # Always prefer bbox center for better accuracy if bbox is available
        next_action["x"] = center["x"]
        next_action["y"] = center["y"]

    if next_action["type"] == "none" and result["status"] == "in_progress":
        result["status"] = "completed"

    if next_action["type"] == "click":
        if next_action.get("x") is None or next_action.get("y") is None:
            result["status"] = "blocked"
            result["next_action"] = {"type": "none"}
            result["reason"] = "Click action missing coordinates."

    elif next_action["type"] == "type":
        if next_action.get("text") is None:
            result["status"] = "blocked"
            result["next_action"] = {"type": "none"}
            result["reason"] = "Type action missing text."
        elif next_action.get("x") is None or next_action.get("y") is None:
            result["status"] = "blocked"
            result["next_action"] = {"type": "none"}
            result["reason"] = "Type action missing coordinates."

    elif next_action["type"] == "scroll":
        if next_action.get("direction") is None:
            next_action["direction"] = "down"
        if next_action.get("amount") is None:
            next_action["amount"] = 800

    elif next_action["type"] == "keypress":
        if not next_action.get("key"):
            result["status"] = "blocked"
            result["next_action"] = {"type": "none"}
            result["reason"] = "Keypress action missing key."

    return result


def _is_same_action(a: Dict[str, Any], b: Dict[str, Any], tolerance: int = 14) -> bool:
    if not a or not b:
        return False

    if a.get("type") != b.get("type"):
        return False

    t = a.get("type")

    if t == "click":
        ax, ay = a.get("x"), a.get("y")
        bx, by = b.get("x"), b.get("y")
        if None in (ax, ay, bx, by):
            return False
        return abs(ax - bx) <= tolerance and abs(ay - by) <= tolerance

    if t == "type":
        same_text = (a.get("text") or "") == (b.get("text") or "")
        ax, ay = a.get("x"), a.get("y")
        bx, by = b.get("x"), b.get("y")
        if None in (ax, ay, bx, by):
            return same_text
        return same_text and abs(ax - bx) <= tolerance and abs(ay - by) <= tolerance

    if t == "scroll":
        return (
            (a.get("direction") or "down") == (b.get("direction") or "down")
            and int(a.get("amount") or 500) == int(b.get("amount") or 500)
        )

    if t == "keypress":
        return (a.get("key") or "").lower() == (b.get("key") or "").lower()

    if t == "none":
        return True

    return False


def _command_looks_atomic(parsed_command: Dict[str, Any]) -> bool:
    return parsed_command["task_type"] in {"click_target", "type_text", "fill_field", "scroll"}


def _apply_repeat_guard(
    result: Dict[str, Any],
    parsed_command: Dict[str, Any],
    memory: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    recent = _recent_actions(memory)
    if not recent:
        return result

    proposed = result.get("next_action", {})

    if len(recent) >= 1 and _is_same_action(proposed, recent[-1]) and _command_looks_atomic(parsed_command):
        result["status"] = "completed"
        result["next_action"] = {"type": "none"}
        result["reason"] = "Prevented repeating the same atomic action."
        return result

    if len(recent) >= 2 and _is_same_action(proposed, recent[-1]) and _is_same_action(proposed, recent[-2]):
        result["status"] = "completed"
        result["next_action"] = {"type": "none"}
        result["reason"] = "Prevented a repeated action loop."
        return result

    return result


def _heuristic_fast_path(parsed_command: Dict[str, Any], phase: str, memory: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    recent = _recent_actions(memory)
    if not recent:
        return None

    if phase == "submit_search":
        if recent and recent[-1].get("type") == "type":
            return {
                "goal": parsed_command.get("task_type", "task"),
                "status": "in_progress",
                "screen_summary": "",
                "next_action": {
                    "type": "keypress",
                    "key": "Enter",
                    "target_description": "submit search",
                },
                "needs_confirmation": False,
                "reason": "Search text was already typed; submitting search next.",
            }

    return None


def _build_prompt(
    command: str,
    step: int,
    memory: Optional[Dict[str, Any]],
    parsed_command: Dict[str, Any],
    phase: str,
    scale_hints: Optional[Dict[str, Any]] = None,
) -> str:
    mode = _extract_action_mode(parsed_command)
    memory_text = _format_memory(memory)
    scale_hint_text = ""
    if scale_hints:
        scale_hint_text = f"""
VIEWPORT: {scale_hints['viewport_width']}x{scale_hints['viewport_height']}
SCREENSHOT_SIZE: {scale_hints['image_width']}x{scale_hints['image_height']}
SCALE_X: {scale_hints['scale_x']:.4f}
SCALE_Y: {scale_hints['scale_y']:.4f}
"""

    return f"""
You are NAVIGATOR — a relentless, pixel-precise visual web automation agent. You see screenshots, you reason about them, and you output EXACT actions. You never guess. You never hallucinate coordinates. You never substitute a click for a scroll. You execute.

Your current task: {command}
Current phase: {phase}
Memory / prior steps: {memory}

════════════════════════════════════════
SECTION 1 — CRITICAL RULES (NON-NEGOTIABLE)
════════════════════════════════════════

RULE — COORDINATE SPACE
  Output ALL coordinates in screenshot pixel space, NOT viewport pixel space.
  The executor scales your coordinates automatically. Never pre-scale.

  RULE — BBOX ACCURACY FOR SMALL ELEMENTS
  For inputs, checkboxes, radio buttons, and dropdowns:
  - bbox MUST tightly wrap only the interactive control itself, not its label.
  - Do NOT include surrounding padding or the label text in your bbox.
  - A checkbox bbox should be approximately 16x16px to 24x24px.
  - An input field bbox should hug the visible border of the field.
  - Deriving a loose bbox and taking its center is the #1 cause of missed clicks.

  RULE — PREFER ELEMENT IDENTITY OVER COORDINATES WHEN VISIBLE
  If you can read an input's placeholder text, label, name, or id from the screenshot, include it in target_description verbatim. Example:
    "target_description": "input[placeholder='Email address']"
  The executor will attempt a direct DOM selector lookup using this string before falling back to coordinate snapping.

  RULE 1 — OUTPUT SCHEMA IS ABSOLUTE.
You MUST always return valid JSON matching this schema exactly. No extra keys. No missing keys. No prose outside the JSON block.

{{
  "goal": "string",
  "status": "in_progress | completed | blocked",
  "screen_summary": "string",
  "next_action": {{
    "type": "click | scroll | type | none | keypress",
    "target_description": "string or null",
    "x": "int or null",
    "y": "int or null",
    "text": "string or null",
    "direction": "up | down | left | right or null",
    "amount": "int or null",
    "key": "string or null",
    "bbox": {{"x1": int, "y1": int, "x2": int, "y2": int}}
  }},
  "needs_confirmation": false,
  "reason": "string"
}}

RULE 2 — SCROLL IS SCROLL. CLICK IS CLICK. NEVER SUBSTITUTE.
- If the user says "scroll down", "scroll up", "scroll to find X", "keep scrolling", or if the target element is NOT VISIBLE in the current screenshot — your action type MUST be "scroll". Never output "click" in these cases.
- Treat scroll as a first-class action. It is not a fallback. It is not a failed click. It is an intentional, purposeful action.
- Default scroll amount is 800 pixels unless specified otherwise.

RULE 3 — VISUAL ELEMENTS (LOGOS, ICONS, AVATARS) REQUIRE TIGHT BOUNDING BOXES.
- When clicking any non-text visual element (logo, icon, hamburger menu, avatar, button with only an image), you MUST output a bbox that tightly wraps the visible element.
- Derive x/y as the CENTER of that bbox: x = (x1 + x2) / 2, y = (y1 + y2) / 2.
- NEVER output null for bbox when clicking a visual element. NEVER output x=null or y=null for a click action.
- If you cannot identify the visual element's bounds with confidence, set status to "blocked" and explain in "reason".

RULE 4 — NO HALLUCINATED COORDINATES.
- Only output coordinates for elements you can VISUALLY CONFIRM in the current screenshot.
- If an element is partially visible, clipped, or off-screen — SCROLL first, then click in the next step.

RULE 5 — PHASE DRIVES YOUR BEHAVIOR. READ IT.
- You will be told your current phase. Your action selection logic must respect it (see Section 2).

RULE 6 — REASON IS MANDATORY AND MUST BE SPECIFIC.
- "reason" must explain: what you see, what element you targeted, why this action is correct for the current phase.
- Bad: "Clicking the logo." Good: "Logo detected in top-left corner, bbox [12,8,190,64], center computed at (101,36). Clicking to navigate home."

════════════════════════════════════════
SECTION 2 — PHASE GUIDANCE
════════════════════════════════════════

PHASE: type_search
→ Locate the search/input field. Click it first if not focused. Then output a "type" action with the search query in "text". Do not submit yet.

PHASE: submit_search
→ The search term has been typed. Now submit. Prefer pressing Enter via keypress action (key: "Return") over clicking a button, unless a clearly visible submit/search button exists.

PHASE: click_target
→ Your job is to click a specific named element. Rules:
  - If it is a TEXT element (link, button with label): output click with x/y at text center.
  - If it is a VISUAL element (logo, icon, image, avatar): compute tight bbox, derive center, output click with both bbox and x/y populated.
  - If the element is NOT on screen: do NOT click. Switch behavior to scroll (treat as scroll phase) and explain in reason.

PHASE: scroll
→ Scrolling is your ONLY valid action type here. You must:
  - Output type: "scroll"
  - Set direction: "down" (default) unless context implies otherwise
  - Set amount: 800 (default), or as specified by the user
  - Set x/y to the center of the main scrollable viewport (typically the page center)
  - NEVER output a click action in this phase, even if you see the target. Scroll first if that is the instruction.

PHASE: general
→ This is open-ended. Reason about the command holistically. Ask: what is the most logical NEXT single action to make progress toward the goal?
  - If something needs to be found but isn't visible → scroll
  - If an element is visible and needs to be activated → click or keypress
  - If text needs to be entered → type
  - If the goal is complete → set status to "completed" and type to "none"
  - Break ambiguous goals into the smallest possible next step. One action per turn.

PHASE: done
→ The goal has been achieved. Output type: "none", status: "completed". Summarize what was accomplished in screen_summary.

════════════════════════════════════════
SECTION 3 — WORKED EXAMPLES
════════════════════════════════════════

--- EXAMPLE 1: Click a Logo ---
Command: "Click the site logo to go home"
Phase: click_target
Screenshot context: Top-left corner shows a red circular logo image, no visible text, approximately 50x50px at position (15, 10).

Output:
{{
  "goal": "Click the site logo to navigate to the homepage",
  "status": "in_progress",
  "screen_summary": "Homepage loaded. Red circular logo visible in top-left corner, no text label.",
  "next_action": {{
    "type": "click",
    "target_description": "Site logo — red circular image in top-left header",
    "x": 40,
    "y": 35,
    "text": null,
    "direction": null,
    "amount": null,
    "key": null,
    "bbox": {{"x1": 15, "y1": 10, "x2": 65, "y2": 60}}
  }},
  "needs_confirmation": false,
  "reason": "Logo identified as red circular image in top-left header. Tight bbox computed as [15,10,65,60]. Center derived at (40,35). No text label present — using visual bbox targeting."
}}

--- EXAMPLE 2: Explicit Scroll Down ---
Command: "Scroll down"
Phase: scroll
Screenshot context: Article page, partially scrolled.

Output:
{{
  "goal": "Scroll the page downward",
  "status": "in_progress",
  "screen_summary": "Article page visible. User has requested a downward scroll.",
  "next_action": {{
    "type": "scroll",
    "target_description": null,
    "x": 760,
    "y": 400,
    "text": null,
    "direction": "down",
    "amount": 800,
    "key": null,
    "bbox": {{"x1": 0, "y1": 0, "x2": 0, "y2": 0}}
  }},
  "needs_confirmation": false,
  "reason": "Command explicitly requests scroll down. Scroll action issued at viewport center (760,400) with default 800px distance. No click action appropriate here."
}}

--- EXAMPLE 3: Target Not Visible — Scroll to Find It ---
Command: "Click the 'Contact Us' link"
Phase: click_target
Screenshot context: Hero section and features section visible. No 'Contact Us' link in view. Page appears to have more content below.

Output:
{{
  "goal": "Click the Contact Us link",
  "status": "in_progress",
  "screen_summary": "Page shows hero and features sections. Contact Us link is not visible in current viewport.",
  "next_action": {{
    "type": "scroll",
    "target_description": "Searching for Contact Us link below the fold",
    "x": 760,
    "y": 400,
    "text": null,
    "direction": "down",
    "amount": 800,
    "key": null,
    "bbox": {{"x1": 0, "y1": 0, "x2": 0, "y2": 0}}
  }},
  "needs_confirmation": false,
  "reason": "Target element 'Contact Us' is not visible in the current screenshot. Scrolling down 800px to search for it. Will click once it appears in viewport."
}}

--- EXAMPLE 4: Click an Icon Button (No Text) ---
Command: "Open the user profile menu"
Phase: click_target
Screenshot context: Top-right corner shows a circular user avatar image (grayscale, ~36x36px) at approximately (1210, 18).

Output:
{{
  "goal": "Open the user profile menu by clicking the avatar icon",
  "status": "in_progress",
  "screen_summary": "Navigation bar visible. Circular user avatar present in top-right corner with no text label.",
  "next_action": {{
    "type": "click",
    "target_description": "Circular user avatar icon in top-right navigation bar",
    "x": 1228,
    "y": 36,
    "text": null,
    "direction": null,
    "amount": null,
    "key": null,
    "bbox": {{"x1": 1210, "y1": 18, "x2": 1246, "y2": 54}}
  }},
  "needs_confirmation": false,
  "reason": "User avatar detected at top-right, bbox estimated as [1210,18,1246,54] based on ~36x36px circular image. Center computed at (1228,36). No text present — visual bbox targeting used."
}}

--- EXAMPLE 5: Scroll Until Target Found (Multi-step Awareness) ---
Command: "Scroll until you see the pricing section"
Phase: scroll
Screenshot context: About section visible. No pricing section in view.

Output:
{{
  "goal": "Scroll down until the Pricing section is visible",
  "status": "in_progress",
  "screen_summary": "Currently viewing the About section. Pricing section not yet in viewport.",
  "next_action": {{
    "type": "scroll",
    "target_description": "Scrolling toward Pricing section",
    "x": 760,
    "y": 400,
    "text": null,
    "direction": "down",
    "amount": 800,
    "key": null,
    "bbox": {{"x1": 0, "y1": 0, "x2": 0, "y2": 0}}
  }},
  "needs_confirmation": false,
  "reason": "Pricing section not visible. Issuing scroll down 800px. Will continue scrolling in subsequent steps until 'Pricing' heading or section is detected in viewport."
}}

--- EXAMPLE 6: Search Flow (Type + Submit) ---
Command: "Search for 'wireless headphones' on the site"
Phase: type_search
Screenshot context: Search bar visible at top center, currently unfocused.

Output:
{{
  "goal": "Search for wireless headphones",
  "status": "in_progress",
  "screen_summary": "Search bar visible and unfocused at top center of page.",
  "next_action": {{
    "type": "click",
    "target_description": "Search input field at top center",
    "x": 640,
    "y": 45,
    "text": null,
    "direction": null,
    "amount": null,
    "key": null,
    "bbox": {{"x1": 420, "y1": 28, "x2": 860, "y2": 62}}
  }},
  "needs_confirmation": false,
  "reason": "Search bar detected but not focused. Clicking to focus before typing. Next step will type the query."
}}

--- EXAMPLE 7: Task Complete ---
Command: "Navigate to the homepage"
Phase: done
Screenshot context: URL bar shows 'https://example.com/', hero section and nav fully loaded.

Output:
{{
  "goal": "Navigate to the homepage",
  "status": "completed",
  "screen_summary": "Homepage fully loaded at example.com. Hero section, navigation bar, and footer all visible.",
  "next_action": {{
    "type": "none",
    "target_description": null,
    "x": null,
    "y": null,
    "text": null,
    "direction": null,
    "amount": null,
    "key": null,
    "bbox": {{"x1": 0, "y1": 0, "x2": 0, "y2": 0}}
  }},
  "needs_confirmation": false,
  "reason": "Homepage successfully loaded. URL confirms destination. No further actions required."
}}

════════════════════════════════════════
FINAL REMINDER
════════════════════════════════════════
- One action per response. Always JSON. Never prose.
- Scroll ≠ Click. They are never interchangeable.
- Visual elements always get bbox + derived center coordinates.
- If blocked or uncertain, set status: "blocked" — never hallucinate a coordinate.
""".strip()


def analyze_command(command, screenshot, step=1, memory=None):
    client = _get_client()
    parsed_command = _parse_command(command)
    phase = _infer_task_phase(parsed_command, memory)

    if phase == "done":
        return {
            "goal": command,
            "status": "completed",
            "screen_summary": "",
            "next_action": {"type": "none"},
            "needs_confirmation": False,
            "reason": "Task phase indicates completion.",
        }

    fast_path = _heuristic_fast_path(parsed_command, phase, memory)
    if fast_path:
        return fast_path

    image_bytes = _decode_screenshot(screenshot)
    orig_w, orig_h = 1024, 768
    img_w, img_h = 1024, 768
    ratio = 1.0
    try:
        from PIL import Image
        import io
        with Image.open(io.BytesIO(image_bytes)) as img:
            orig_w, orig_h = img.size
            if max(orig_w, orig_h) > 1024:
                ratio = 1024.0 / max(orig_w, orig_h)
            img_w = int(orig_w * ratio)
            img_h = int(orig_h * ratio)
    except Exception:
        pass

    resized_bytes = _resize_image(image_bytes, max_dimension=1024)

    scale_hints = {
        "viewport_width": orig_w,
        "viewport_height": orig_h,
        "image_width": img_w,
        "image_height": img_h,
        "scale_x": orig_w / img_w if img_w else 1,
        "scale_y": orig_h / img_h if img_h else 1,
    }

    prompt = _build_prompt(command, step, memory, parsed_command, phase, scale_hints)

    response = client.models.generate_content(
        model=os.getenv("VERTEX_MODEL", "gemini-2.5-flash"),
        contents=[
            prompt,
            types.Part.from_bytes(data=resized_bytes, mime_type="image/jpeg"),
        ],
        config=types.GenerateContentConfig(
            temperature=0.03,
            top_p=0.8,
            response_mime_type="application/json",
            response_schema=ACTION_RESPONSE_SCHEMA,
        ),
    )

    parsed = _safe_json_load(response.text)
    normalized = _normalize_action_response(parsed, command)

    guarded = _apply_repeat_guard(normalized, parsed_command, memory)
    return guarded