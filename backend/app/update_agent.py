import sys, re

with open('agent.py', 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Update analyze_command to compute dimensions and pass to _build_prompt
new_analyze = text.replace(
'''    image_bytes = _decode_screenshot(screenshot)
    prompt = _build_prompt(command, step, memory, parsed_command, phase)''',
'''    image_bytes = _decode_screenshot(screenshot)
    orig_w, orig_h = 1024, 768
    img_w, img_h = 1024, 768
    try:
        from PIL import Image
        import io
        with Image.open(io.BytesIO(image_bytes)) as img:
            orig_w, orig_h = img.size
            if max(orig_w, orig_h) <= 1024:
                img_w, img_h = orig_w, orig_h
            else:
                ratio = 1024 / max(orig_w, orig_h)
                img_w, img_h = int(orig_w * ratio), int(orig_h * ratio)
    except Exception:
        pass

    scale_hints = {
        "viewport_width": orig_w,
        "viewport_height": orig_h,
        "image_width": img_w,
        "image_height": img_h,
        "scale_x": orig_w / img_w if img_w else 1,
        "scale_y": orig_h / img_h if img_h else 1,
    }

    prompt = _build_prompt(command, step, memory, parsed_command, phase, scale_hints)'''
)

# 2. Update _build_prompt signature
new_analyze = new_analyze.replace(
'''def _build_prompt(
    command: str,
    step: int,
    memory: Optional[Dict[str, Any]],
    parsed_command: Dict[str, Any],
    phase: str,
) -> str:''',
'''def _build_prompt(
    command: str,
    step: int,
    memory: Optional[Dict[str, Any]],
    parsed_command: Dict[str, Any],
    phase: str,
    scale_hints: Optional[Dict[str, Any]] = None,
) -> str:'''
)

new_analyze = new_analyze.replace(
'''    memory_text = _format_memory(memory)

    return f"""''',
'''    memory_text = _format_memory(memory)
    scale_hint_text = ""
    if scale_hints:
        scale_hint_text = f"""
VIEWPORT: {scale_hints['viewport_width']}x{scale_hints['viewport_height']}
SCREENSHOT_SIZE: {scale_hints['image_width']}x{scale_hints['image_height']}
SCALE_X: {scale_hints['scale_x']:.4f}
SCALE_Y: {scale_hints['scale_y']:.4f}
"""

    return f"""'''
)

new_analyze = new_analyze.replace(
'''  Memory / prior steps: {memory}''',
'''  Memory / prior steps: {memory}
  {scale_hint_text}
'''
)

new_analyze = new_analyze.replace(
'''Memory / prior steps: {memory_text}''',
'''Memory / prior steps: {memory_text}
  {scale_hint_text}
'''
)

new_analyze = new_analyze.replace(
'''RULE 1 — OUTPUT SCHEMA IS ABSOLUTE.''',
'''RULE — COORDINATE SPACE
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

  RULE 1 — OUTPUT SCHEMA IS ABSOLUTE.'''
)

new_analyze = new_analyze.replace(
'''RULE 1 â€” OUTPUT SCHEMA IS ABSOLUTE.''',
'''RULE — COORDINATE SPACE
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

  RULE 1 — OUTPUT SCHEMA IS ABSOLUTE.'''
)

with open('agent.py', 'w', encoding='utf-8') as f:
    f.write(new_analyze)
print('Updated analyze_command signature')