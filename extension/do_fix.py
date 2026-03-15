import sys

with open('c:/Projects/UI-nav/extension/content.js', 'r', encoding='utf-8') as f:
    lines = f.readlines()

out = []
skip = False

for line in lines:
    if line.startswith('function compute_scale_factors()'):
        skip = True

    if skip and line.strip() == '}':
        skip = False
        # Insert our new things here!
        out.append("""const KNOWN_ELEMENT_SELECTORS = {
  // Google Search
  "google search input":        'input[name="q"]',
  "search input":               'input[name="q"], input[type="search"]',
  "google search input field":  'input[name="q"]',
  // Google Forms
  "short answer":               '[role="textbox"]',
  // Common patterns
  "email input":                'input[type="email"], input[name="email"]',
  "password input":             'input[type="password"]',
  "username input":             'input[name="username"], input[name="user"]',
  "submit button":              '[type="submit"], [role="button"]',
};

function tryNamedElementLookup(target_description) {
  if (!target_description || typeof target_description !== 'string') return null;
  const key = target_description.toLowerCase().trim();

  if (KNOWN_ELEMENT_SELECTORS[key]) {
    const el = document.querySelector(KNOWN_ELEMENT_SELECTORS[key]);
    if (el && el.offsetParent !== null) return el;
  }

  for (const [knownKey, selector] of Object.entries(KNOWN_ELEMENT_SELECTORS)) {
    if (key.includes(knownKey)) {
      const el = document.querySelector(selector);
      if (el && el.offsetParent !== null) return el;
    }
  }

  return null;
}

function buildExecutionError(resolvedTag, resolvedVia, x, y) {
  const isIframe = resolvedTag === 'IFRAME';

  return {
    status: "error",
    error: "resolved_element_not_typable",
    tag: resolvedTag,
    resolved_via: resolvedVia,
    x, y,
    suggestion: isIframe
      ? "iframe_pierce_required"
      : "check_scale_factors_and_snap_radius",
    debug_hint: isIframe
      ? "Element is an IFRAME wrapper. Use frame locator to access inner DOM."
      : `Element resolved to <${resolvedTag}> which is not typable. Likely a scale factor error - check SCALE_X/SCALE_Y values.`
  };
}

function computeScaleFactors() {
  const DPR = window.devicePixelRatio || 1;
  const orig_w = window.innerWidth * DPR;
  const orig_h = window.innerHeight * DPR;

  const max_dimension = 1024;
  let ratio = 1;
  if (Math.max(orig_w, orig_h) > max_dimension) {
    ratio = max_dimension / Math.max(orig_w, orig_h);
  }

  const img_w = Math.round(orig_w * ratio) || 1;
  const img_h = Math.round(orig_h * ratio) || 1;

  const scale_x = window.innerWidth / img_w;
  const scale_y = window.innerHeight / img_h;

  if (scale_x > 1.5 || scale_y > 1.5) {
     console.warn(`[SCALE WARNING] SCALE_X=${scale_x.toFixed(3)}, SCALE_Y=${scale_y.toFixed(3)}`);
  }

  return { scale_x, scale_y };
}
""")
        continue

    if not skip:
        out.append(line)

new_text = "".join(out)

# 2. find_best_interactive_element replacement
import re

new_snapper = '''function find_best_interactive_element(real_x, real_y) {
  const radii = [30, 60, 120, 240];
  
  for (const radius of radii) {
    const SELECTORS = [
      'input:not([type="hidden"])',
      'textarea',
      'select',
      'button',
      '[role="button"]',
      '[role="radio"]',
      '[role="checkbox"]',
      '[role="combobox"]',
      '[role="textbox"]',
      '[role="searchbox"]',
      '[tabindex]:not([tabindex="-1"])',
      'label',
      'a[href]'
    ].join(', ');

    const candidates = Array.from(document.querySelectorAll(SELECTORS))
      .filter(el => {
        const rect = el.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) return false;
        const style = window.getComputedStyle(el);
        return style.display !== 'none' && style.visibility !== 'hidden';
      })
      .map(el => {
        const rect = el.getBoundingClientRect();
        const cx = rect.left + rect.width / 2;
        const cy = rect.top + rect.height / 2;
        const dist = Math.hypot(cx - real_x, cy - real_y);
        return { 
          element: el,
          tag: el.tagName,
          cx, cy, dist, rect,
          typable: ['INPUT','TEXTAREA','SELECT'].includes(el.tagName)
                || ['textbox','searchbox','combobox'].includes(el.getAttribute('role') || '') 
        };
      })
      .filter(c => c.dist <= radius)
      .sort((a, b) => {
        if (a.typable && !b.typable) return -1;
        if (!a.typable && b.typable) return 1;
        return a.dist - b.dist;
      });

    const best = candidates[0] || null;
    if (best) {
      console.log(`[SNAP HIT] radius=${radius}px, tag=${best.tag}, dist=${best.dist.toFixed(1)}px`);
      const labelRes = resolve_label_target(best.element);
      if (labelRes) {
        return { element: labelRes.element, true_center: labelRes.true_center, distance: best.dist };
      }
      return { element: best.element, true_center: {x: best.cx, y: best.cy}, distance: best.dist };
    }
  }

  return null;
}'''

new_text = re.sub(r'function find_best_interactive_element\(real_x, real_y, search_radius=40\) \{.*?(?=function try_selector_fast_path)', new_snapper + '\n\n', new_text, flags=re.DOTALL)

# Update computeScaleFactors call
new_text = new_text.replace('let scale_hints = compute_scale_factors();', 'let scale_hints = computeScaleFactors();')

# 3. Add fast path to executeAction
fast_path_old = '''let fast_path = try_selector_fast_path(processAction.target_description);
    let snap = null;
    
    if (!fast_path) {
      snap = find_best_interactive_element(real_x, real_y, 40);
    }'''

fast_path_new = '''let fast_path = tryNamedElementLookup(processAction.target_description) 
      ? { element: tryNamedElementLookup(processAction.target_description), true_center: (()=>{const el=tryNamedElementLookup(processAction.target_description); const r=el.getBoundingClientRect(); return {x: r.left+r.width/2, y: r.top+r.height/2}})() }
      : try_selector_fast_path(processAction.target_description);
    let snap = null;
    
    if (!fast_path) {
      snap = find_best_interactive_element(real_x, real_y);
    }'''

new_text = new_text.replace(fast_path_old, fast_path_new)

# 4. Error block replacement in executeTypeAction
old_err_type = '''      return {
        status: "error",
        error: "resolved_element_not_typable",
        tag: target ? target.tagName : hit.el ? hit.el.tagName : "UNKNOWN",
        suggestion: "iframe_pierce_required",
        resolved_via: hit.resolutionChain || "direct",
        frame_url: hit.frame_url || null,
        x: typeX,
        y: typeY,
      };'''

new_text = new_text.replace(old_err_type, '''      return buildExecutionError(
        target ? target.tagName : hit.el ? hit.el.tagName : "UNKNOWN",
        hit.resolutionChain || "direct",
        typeX, typeY
      );''')

# Error block replacement in executeClickAction
old_err_clk = '''      return {
        status: "error",
        error: "resolved_element_not_typable",
        tag: target ? target.tagName : hit.el ? hit.el.tagName : "UNKNOWN",
        suggestion: "iframe_pierce_required",
        resolved_via: hit.resolutionChain || "direct",
        frame_url: hit.frame_url || null,
        x: clickX,
        y: clickY,
      };'''

new_text = new_text.replace(old_err_clk, '''      return buildExecutionError(
        target ? target.tagName : hit.el ? hit.el.tagName : "UNKNOWN",
        hit.resolutionChain || "direct",
        clickX, clickY
      );''')

with open('c:/Projects/UI-nav/extension/content.js', 'w', encoding='utf-8') as f:
    f.write(new_text)

print("Replacement complete.")
