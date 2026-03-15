import re

with open('c:/Projects/UI-nav/extension/content.js', 'r', encoding='utf-8') as f:
    text = f.read()

old_rect_logic = """  const rect = target.getBoundingClientRect();
  const insideTarget =
    clickX >= rect.left &&
    clickX <= rect.right &&
    clickY >= rect.top &&
    clickY <= rect.bottom;

  const finalX = insideTarget ? clickX : Math.round(rect.left + rect.width / 2);
  const finalY = insideTarget ? clickY : Math.round(rect.top + rect.height / 2);"""

new_rect_logic = """  const rect = target.getBoundingClientRect();
  const insideTarget =
    clickX >= rect.left &&
    clickX <= rect.right &&
    clickY >= rect.top &&
    clickY <= rect.bottom;

  let finalX = clickX;
  let finalY = clickY;

  if (rect.width > 0 && rect.height > 0) {
    if (!insideTarget) {
      finalX = Math.round(rect.left + rect.width / 2);
      finalY = Math.round(rect.top + rect.height / 2);
    }
  }"""

text = text.replace(old_rect_logic, new_rect_logic)

with open('c:/Projects/UI-nav/extension/content.js', 'w', encoding='utf-8') as f:
    f.write(text)
print('Updated rect logic')
