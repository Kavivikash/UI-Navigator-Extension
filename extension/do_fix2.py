import re
with open('c:/Projects/UI-nav/extension/content.js', 'r', encoding='utf-8') as f:
    text = f.read()

text = re.sub(
    r'return \{\s*status:\s*"error",\s*error:\s*"resolved_element_not_typable".*?y:\s*(typeY|clickY),\s*\};',
    lambda m: f'return buildExecutionError(target ? target.tagName : (hit.el ? hit.el.tagName : "UNKNOWN"), hit.resolutionChain || "direct", {"typeX" if m.group(1)=="typeY" else "clickX"}, {m.group(1)});',
    text,
    flags=re.DOTALL
)

with open('c:/Projects/UI-nav/extension/content.js', 'w', encoding='utf-8') as f:
    f.write(text)
print('applied regex replacement')
