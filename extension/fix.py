import sys
import re

with open('c:/Projects/UI-nav/extension/content.js', 'r', encoding='utf-8') as f:
    text = f.read()

new_helpers_prefix = """const KNOWN_ELEMENT_SELECTORS = {
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
"""

text = re.sub(r'function compute_scale_factors\(\)\s*\{.*?return \{.*?scale_x:.*?\};(?:[^}]*\})?(?:[^}]*\})?', new_helpers_prefix, text, flags=re.DOTALL)
# careful regex replacement fails if block ends differently.
# let's write safer replacement
