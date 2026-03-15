import re

with open('c:/Projects/UI-nav/extension/content.js', 'r', encoding='utf-8') as f:
    text = f.read()

# Replace executeAction's fast_path logic
old_fast_path = """    let fast_path = try_selector_fast_path(processAction.target_description);
    let snap = null;

    if (!fast_path) {
      snap = find_best_interactive_element(real_x, real_y, 40);
    }"""

new_fast_path = """    let fast_path = null;
    let named_el = tryNamedElementLookup(processAction.target_description);
    if (named_el) {
      const r = named_el.getBoundingClientRect();
      fast_path = { element: named_el, true_center: {x: r.left+r.width/2, y: r.top+r.height/2} };
    } else {
      fast_path = try_selector_fast_path(processAction.target_description);
    }

    let snap = null;

    if (!fast_path) {
      snap = find_best_interactive_element(real_x, real_y);
    }"""

text = text.replace(old_fast_path, new_fast_path)

# Escalate radii in find_best_interactive_element
old_find_best = re.search(r'function find_best_interactive_element\(real_x, real_y, search_radius = 40\) \{.*?(?=function try_selector_fast_path)', text, re.DOTALL).group(0)

new_find_best = """function find_best_interactive_element(real_x, real_y) {
  const radii = [10, 20, 40, 80, 160];
  
  const selectors = "input:not([type='hidden']), textarea, select, button, a[href], [role='button'], [role='checkbox'], [role='radio'], [role='combobox'], [role='listbox'], [tabindex]:not([tabindex='-1']), label";
  const candidates = Array.from(document.querySelectorAll(selectors));

  for (const radius of radii) {
    let best_dist = Infinity;
    let best_cand = null;
    let best_center = null;

    for (const el of candidates) {
      const rect = el.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) continue;

      const style = window.getComputedStyle(el);
      if (style.display === "none" || style.visibility === "hidden") continue;

      const cx = rect.left + rect.width / 2;
      const cy = rect.top + rect.height / 2;

      const dist = Math.hypot(cx - real_x, cy - real_y);
      if (dist < best_dist && dist <= radius) {
        best_dist = dist;
        best_cand = el;
        best_center = { x: cx, y: cy };
      }
    }

    if (best_cand) {
      console.log(`[SNAP HIT] radius=${radius}px, tag=${best_cand.tagName}, dist=${best_dist.toFixed(1)}px`);
      const labelRes = resolve_label_target(best_cand);
      if (labelRes) {
        return { element: labelRes.element, true_center: labelRes.true_center, distance: best_dist };
      }
      return { element: best_cand, true_center: best_center, distance: best_dist };
    }
  }

  return null;
}
"""

text = text.replace(old_find_best, new_find_best)

with open('c:/Projects/UI-nav/extension/content.js', 'w', encoding='utf-8') as f:
    f.write(text)
print('Updated executeAction and find_best_interactive_element')
