from google import genai
from google.genai import types
import os
import json
import base64
from typing import Any, Dict, List, Optional


ALLOWED_ACTION_TYPES = {"click", "scroll", "type", "none"}

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
                "bbox",
            ],
            "required": ["type"],
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ["click", "scroll", "type", "none"]
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


def _format_memory(memory: Optional[Dict[str, Any]]) -> str:
    if not memory or not memory.get("history"):
        return "No previous action history."

    lines: List[str] = []
    for item in memory.get("history", [])[-5:]:
        step = item.get("step")
        action = item.get("action") or {}
        screen_summary = item.get("screen_summary")
        result_summary = item.get("result_summary")

        lines.append(
            json.dumps(
                {
                    "step": step,
                    "action": action,
                    "screen_summary": screen_summary,
                    "result_summary": result_summary,
                },
                ensure_ascii=False,
            )
        )

    return "\n".join(lines)


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


def _normalize_action_response(data: Dict[str, Any], command: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "goal": data.get("goal") or command,
        "status": data.get("status") or "in_progress",
        "screen_summary": data.get("screen_summary") or "",
        "next_action": data.get("next_action") or {"type": "none"},
        "needs_confirmation": bool(data.get("needs_confirmation", False)),
        "reason": data.get("reason") or "",
    }

    next_action = result["next_action"]
    action_type = next_action.get("type", "none")

    if action_type not in ALLOWED_ACTION_TYPES:
        next_action["type"] = "none"
        result["status"] = "blocked"
        result["reason"] = (
            f"Model returned unsupported action type '{action_type}'. "
            "Converted to 'none'."
        )
        return result

    bbox = next_action.get("bbox")
    if bbox and (next_action.get("x") is None or next_action.get("y") is None):
        center = _center_from_bbox(bbox)
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
        if next_action.get("x") is None or next_action.get("y") is None:
            result["status"] = "blocked"
            result["next_action"] = {"type": "none"}
            result["reason"] = "Type action missing coordinates."
    elif next_action["type"] == "scroll":
        if next_action.get("direction") is None:
            next_action["direction"] = "down"
        if next_action.get("amount") is None:
            next_action["amount"] = 500

    return result


def _is_same_action(a: Dict[str, Any], b: Dict[str, Any], tolerance: int = 12) -> bool:
    if not a or not b:
        return False

    if a.get("type") != b.get("type"):
        return False

    action_type = a.get("type")

    if action_type == "click":
        ax, ay = a.get("x"), a.get("y")
        bx, by = b.get("x"), b.get("y")
        if None in (ax, ay, bx, by):
            return False
        return abs(ax - bx) <= tolerance and abs(ay - by) <= tolerance

    if action_type == "type":
        ax, ay = a.get("x"), a.get("y")
        bx, by = b.get("x"), b.get("y")
        same_text = (a.get("text") or "") == (b.get("text") or "")
        if None in (ax, ay, bx, by):
            return same_text
        return same_text and abs(ax - bx) <= tolerance and abs(ay - by) <= tolerance

    if action_type == "scroll":
        return (
            (a.get("direction") or "down") == (b.get("direction") or "down")
            and int(a.get("amount") or 500) == int(b.get("amount") or 500)
        )

    if action_type == "none":
        return True

    return False


def _command_looks_atomic(command: str) -> bool:
    command_l = command.lower().strip()
    atomic_starts = (
        "click ",
        "tap ",
        "open ",
        "focus ",
        "select ",
        "press ",
        "choose ",
    )
    return command_l.startswith(atomic_starts)


def _apply_repeat_guard(
    result: Dict[str, Any],
    command: str,
    memory: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    if not memory or not memory.get("history"):
        return result

    history = memory["history"]
    proposed_action = result.get("next_action", {})

    if len(history) >= 1:
        last_action = history[-1].get("action", {})
        if _is_same_action(proposed_action, last_action) and _command_looks_atomic(command):
            result["status"] = "completed"
            result["next_action"] = {"type": "none"}
            result["reason"] = (
                "Prevented repeating the same atomic action from the previous step. "
                "The goal is likely already satisfied."
            )
            return result

    if len(history) >= 2:
        last_action = history[-1].get("action", {})
        prev_action = history[-2].get("action", {})
        if (
            _is_same_action(proposed_action, last_action)
            and _is_same_action(proposed_action, prev_action)
        ):
            result["status"] = "completed"
            result["next_action"] = {"type": "none"}
            result["reason"] = (
                "Prevented a third identical action in a row. "
                "Assuming no further action is required."
            )
            return result

    return result


def analyze_command(command, screenshot, step=1, memory=None):
    client = _get_client()
    image_bytes = _decode_screenshot(screenshot)
    memory_text = _format_memory(memory)

    prompt = f"""
You are UI Navigator, a visual browser navigation agent.

Your job:
- Understand the webpage ONLY from the screenshot.
- Decide the SINGLE next best action.
- Avoid repeating actions that were already attempted.
- Detect when the user's goal is already achieved.
- Prefer returning a bounding box for the target UI element. If you return a bbox, also return the center point x,y.
- Return JSON only.

Current user command:
"{command}"

Current step:
{step}

Recent agent memory:
{memory_text}

Important rules:
1. Use only visible UI evidence from the screenshot.
2. Never rely on DOM, hidden state, or website-specific APIs.
3. Allowed action types: click, scroll, type, none
4. If the goal is already completed, return:
   - "status": "completed"
   - "next_action": {{"type": "none"}}
5. If the current screenshot shows the result of a previous action already happened
   (for example an active search bar, opened menu, selected field, expanded dropdown,
   or text already entered), do NOT repeat that action.
6. If an element is visible, estimate a tight bbox around it and use its center as x,y.
7. For click/type, return coordinates.
8. For scroll, return direction and amount.
9. For type, return the exact text only if the command clearly asks for text entry.
10. If the action would be risky (submit payment, delete, confirm irreversible action),
    set "needs_confirmation": true.
11. Keep "screen_summary" short and factual.
12. Keep "reason" short and precise.

Examples:
- If the command is "click search bar" and the search bar is already focused or active,
  return completed + none.
- If the command is "open language menu" and the menu is already open,
  return completed + none.
- If the requested target is not visible but likely below the fold,
  return a scroll action instead of guessing a random click.

Return a single JSON object matching the required schema.
"""

    response = client.models.generate_content(
        model=os.getenv("VERTEX_MODEL", "gemini-2.5-flash"),
        contents=[
            prompt,
            types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
        ],
        config=types.GenerateContentConfig(
            temperature=0.1,
            response_mime_type="application/json",
            response_schema=ACTION_RESPONSE_SCHEMA,
        ),
    )

    parsed = _safe_json_load(response.text)
    normalized = _normalize_action_response(parsed, command)
    guarded = _apply_repeat_guard(normalized, command, memory)
    return guarded