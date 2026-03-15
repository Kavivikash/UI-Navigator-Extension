import re

with open('c:/Projects/UI-nav/extension/content.js', 'r', encoding='utf-8') as f:
    text = f.read()

new_click = """function clickElement(el, clickX, clickY) {
  if (typeof el.focus === "function") {
    el.focus();
  }

  const events = [
    "pointerover",
    "mouseover",
    "pointerenter",
    "mouseenter",
    "pointerdown",
    "mousedown",
    "pointerup",
    "mouseup"
  ];

  for (const type of events) {
    el.dispatchEvent(
      new MouseEvent(type, {
        view: window,
        bubbles: true,
        cancelable: true,
        clientX: clickX,
        clientY: clickY,
      })
    );
  }

  try {
    if (typeof el.click === "function") {
      el.click();
    } else {
      el.dispatchEvent(
        new MouseEvent("click", {
          view: window,
          bubbles: true,
          cancelable: true,
          clientX: clickX,
          clientY: clickY,
        })
      );
    }
  } catch (_) {}

  return { clientX: clickX, clientY: clickY };
}"""

text = re.sub(r'function clickElement\(el, clickX, clickY\)\s*\{.*?return \{ clientX: clickX, clientY: clickY \};\s*\}', new_click, text, flags=re.DOTALL)

with open('c:/Projects/UI-nav/extension/content.js', 'w', encoding='utf-8') as f:
    f.write(text)
print('Updated clickElement')
