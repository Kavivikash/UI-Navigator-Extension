console.log("content.js loaded");

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "PING") {
    sendResponse({ status: "alive" });
    return false;
  }

  console.log("message received in content.js:", message);

  if (message.type !== "EXECUTE_ACTION") {
    return false;
  }

  (async () => {
    try {
      const payload = message.payload || {};
      const result = await executeAction(payload);
      sendResponse(result);
    } catch (error) {
      sendResponse({
        status: "error",
        error: error?.message || String(error),
      });
    }
  })();

  return true;
});

function distance(x1, y1, x2, y2) {
  return Math.hypot(x2 - x1, y2 - y1);
}

function getRectCenter(el) {
  const r = el.getBoundingClientRect();
  return {
    x: r.left + r.width / 2,
    y: r.top + r.height / 2,
  };
}

function getElementsMatching(selector) {
  return Array.from(document.querySelectorAll(selector)).filter((el) => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  });
}

function findNearestElementBySelectors(x, y, selectors, maxDistance = 60) {
  const candidates = getElementsMatching(selectors);
  let best = null;
  let bestDist = Infinity;

  // First pass: Prefer elements that actually contain the point
  for (const el of candidates) {
    const r = el.getBoundingClientRect();
    if (x >= r.left && x <= r.right && y >= r.top && y <= r.bottom) {
      // If multiple elements contain the point, pick the smallest one (most specific)
      const area = r.width * r.height;
      if (
        !best ||
        area <
          best.getBoundingClientRect().width *
            best.getBoundingClientRect().height
      ) {
        best = el;
        bestDist = 0; // It contains point
      }
    }
  }

  if (best) return best;

  // Second pass: Find nearest center
  for (const el of candidates) {
    const c = getRectCenter(el);
    const d = distance(x, y, c.x, c.y);
    if (d < bestDist && d <= maxDistance) {
      best = el;
      bestDist = d;
    }
  }

  return best;
}

function inferIntentFromPayload(payload, action) {
  const text =
    `${payload?.goal || ""} ${action?.target_description || ""}`.toLowerCase();

  if (
    text.includes("search bar") ||
    text.includes("search box") ||
    text.includes("search input") ||
    text.includes("input field") ||
    text.includes("textbox")
  ) {
    return "search_input";
  }

  if (
    text.includes("email") ||
    text.includes("password") ||
    text.includes("field") ||
    text.includes("form")
  ) {
    return "form_input";
  }

  if (
    text.includes("link") ||
    text.includes("hyperlink") ||
    text.includes("references") ||
    text.includes("tab")
  ) {
    return "link_like";
  }

  if (
    text.includes("button") ||
    text.includes("submit") ||
    text.includes("menu")
  ) {
    return "button_like";
  }

  return "generic";
}

function refineTargetForIntent(payload, action, hitElement, x, y) {
  const intent = inferIntentFromPayload(payload, action);

  if (intent === "search_input") {
    if (hitElement) {
      const exact = hitElement.closest(
        "input[type='search'], input[type='text'], input[role='searchbox'], input, textarea, [contenteditable='true'], [role='textbox']",
      );
      if (exact) return exact;
    }
    return (
      findNearestElementBySelectors(
        x,
        y,
        "input[type='search'], input[type='text'], input[role='searchbox'], input, textarea, [contenteditable='true'], [role='textbox']",
        80,
      ) || hitElement
    );
  }

  if (intent === "form_input") {
    if (hitElement) {
      const exact = hitElement.closest(
        "input, textarea, [contenteditable='true'], [role='textbox']",
      );
      if (exact) return exact;
    }
    return (
      findNearestElementBySelectors(
        x,
        y,
        "input, textarea, [contenteditable='true'], [role='textbox']",
        60,
      ) || hitElement
    );
  }

  if (intent === "link_like") {
    if (hitElement) {
      const exact = hitElement.closest(
        "a, [role='link'], button, [role='button']",
      );
      if (exact) return exact;
    }
    return (
      findNearestElementBySelectors(
        x,
        y,
        "a, [role='link'], button, [role='button']",
        50,
      ) || hitElement
    );
  }

  if (intent === "button_like") {
    if (hitElement) {
      const exact = hitElement.closest(
        "button, [role='button'], a, input[type='button'], input[type='submit']",
      );
      if (exact) return exact;
    }
    return (
      findNearestElementBySelectors(
        x,
        y,
        "button, [role='button'], a, input[type='button'], input[type='submit']",
        50,
      ) || hitElement
    );
  }

  return hitElement;
}

function getViewportScaleHints() {
  return {
    devicePixelRatio: window.devicePixelRatio || 1,
    innerWidth: window.innerWidth,
    innerHeight: window.innerHeight,
    outerWidth: window.outerWidth,
    outerHeight: window.outerHeight,
  };
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function showPointMarker(x, y, color = "red") {
  const marker = document.createElement("div");
  marker.style.position = "fixed";
  marker.style.left = `${x - 10}px`;
  marker.style.top = `${y - 10}px`;
  marker.style.width = "20px";
  marker.style.height = "20px";
  marker.style.borderRadius = "50%";
  marker.style.background = color;
  marker.style.zIndex = "999999";
  marker.style.pointerEvents = "none";
  marker.style.boxShadow = "0 0 0 2px white";
  document.body.appendChild(marker);

  setTimeout(() => marker.remove(), 1000);
}

function showBoundingBox(bbox) {
  if (!bbox) return;

  const { x1, y1, x2, y2 } = bbox;
  const hasAll = [x1, y1, x2, y2].every(
    (v) => typeof v === "number" && Number.isFinite(v),
  );

  if (!hasAll) return;

  const box = document.createElement("div");
  box.style.position = "fixed";
  box.style.left = `${x1}px`;
  box.style.top = `${y1}px`;
  box.style.width = `${Math.max(0, x2 - x1)}px`;
  box.style.height = `${Math.max(0, y2 - y1)}px`;
  box.style.border = "2px solid #00ff88";
  box.style.background = "rgba(0,255,136,0.08)";
  box.style.zIndex = "999998";
  box.style.pointerEvents = "none";
  box.style.borderRadius = "8px";
  document.body.appendChild(box);

  setTimeout(() => box.remove(), 1200);
}

function getCenterFromBBox(bbox) {
  return {
    x: Math.round((bbox.x1 + bbox.x2) / 2),
    y: Math.round((bbox.y1 + bbox.y2) / 2),
  };
}

function isValidBBox(bbox) {
  return (
    !!bbox &&
    [bbox.x1, bbox.y1, bbox.x2, bbox.y2].every(
      (v) => typeof v === "number" && Number.isFinite(v),
    )
  );
}

function getBestTypableTarget(el) {
  if (!el) return null;

  if (isTextInput(el)) return el;

  const nested = el.querySelector?.(
    "input, textarea, [contenteditable='true'], [contenteditable=''], [role='textbox']",
  );

  if (nested) return nested;

  const closest = el.closest?.(
    "input, textarea, [contenteditable='true'], [contenteditable=''], [role='textbox']",
  );

  return closest || el;
}

function getBestClickableTarget(el) {
  if (!el) return null;
  // If the element itself is inherently interactive, keep it
  const tag = el.tagName?.toLowerCase();
  const role = el.getAttribute?.("role");
  if (
    tag === "a" ||
    tag === "button" ||
    tag === "input" ||
    tag === "textarea" ||
    tag === "select" ||
    el.isContentEditable ||
    role === "button" ||
    role === "link" ||
    role === "textbox"
  ) {
    return el;
  }

  // Prefer a true clickable descendant (e.g. anchor or button) inside the region
  const descendant = el.querySelector?.(
    "a[href], [role='link'], button, [role='button'], input[type='button'], input[type='submit']",
  );

  let candidate = descendant || el;

  // Then walk up to the nearest clickable ancestor if it exists
  const ancestor = candidate.closest?.(
    "a[href], button, [role='button'], [role='link'], input[type='button'], input[type='submit'], [tabindex]",
  );

  return ancestor || candidate;
}

/*
 * Resolves element from coordinates, piercing into same-origin iframes if hit.
 * If a frame is hit but cross-origin, records the error but returns the iframe.
 */
function getElementFromBBoxOrPoint(action, bbox) {
  const tryPoints = [];

  if (typeof action.x === "number" && typeof action.y === "number") {
    tryPoints.push([action.x, action.y]);
  }

  if (isValidBBox(bbox)) {
    const { x, y } = getCenterFromBBox(bbox);
    tryPoints.push(
      [x, y],
      [x, bbox.y1 + 6],
      [x, bbox.y2 - 6],
      [bbox.x1 + 6, y],
      [bbox.x2 - 6, y],
    );
  }

  for (const [x, y] of tryPoints) {
    let el = document.elementFromPoint(x, y);
    if (!el) continue;

    let resolutionChain = "direct";
    let frame_url = null;
    let localX = x;
    let localY = y;
    let crossOriginError = false;

    if (el.tagName && el.tagName.toLowerCase() === "iframe") {
      resolutionChain = "iframe_pierce";
      frame_url = el.src || null;
      try {
        const iframeDoc = el.contentDocument || el.contentWindow?.document;
        if (!iframeDoc) {
          throw new Error("No access to contentDocument");
        }
        const rect = el.getBoundingClientRect();
        const style = window.getComputedStyle(el);
        const borderLeft = parseFloat(style.borderLeftWidth) || 0;
        const borderTop = parseFloat(style.borderTopWidth) || 0;

        localX = x - rect.left - borderLeft;
        localY = y - rect.top - borderTop;

        const innerEl = iframeDoc.elementFromPoint(localX, localY);
        if (innerEl) {
          el = innerEl;
        }
      } catch (e) {
        resolutionChain = "fallback";
        crossOriginError = true;
      }
    }

    return {
      el,
      x: localX,
      y: localY,
      resolutionChain,
      frame_url,
      crossOriginError,
      globalX: x,
      globalY: y,
    };
  }

  return null;
}

function isTextInput(el) {
  if (!el) return false;

  const tag = el.tagName?.toLowerCase();
  if (tag === "textarea") return true;

  if (tag === "input") {
    const type = (el.type || "text").toLowerCase();
    return [
      "text",
      "search",
      "email",
      "url",
      "tel",
      "password",
      "number",
    ].includes(type);
  }

  if (el.isContentEditable) return true;
  if (el.getAttribute?.("role") === "textbox") return true;

  return false;
}

function isFocusable(el) {
  if (!el) return false;
  const tag = el.tagName?.toLowerCase();

  return (
    tag === "input" ||
    tag === "textarea" ||
    tag === "select" ||
    el.isContentEditable ||
    typeof el.focus === "function"
  );
}

function dispatchMouseSequence(el, clientX, clientY) {
  const events = ["pointerdown", "mousedown", "pointerup", "mouseup", "click"];

  for (const type of events) {
    el.dispatchEvent(
      new MouseEvent(type, {
        view: window,
        bubbles: true,
        cancelable: true,
        clientX,
        clientY,
      }),
    );
  }
}

function clickElement(el, clickX, clickY) {
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
    "mouseup",
  ];

  for (const type of events) {
    el.dispatchEvent(
      new MouseEvent(type, {
        view: window,
        bubbles: true,
        cancelable: true,
        clientX: clickX,
        clientY: clickY,
      }),
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
        }),
      );
    }
  } catch (_) {}

  return { clientX: clickX, clientY: clickY };
}

function getNativeValueSetter(target) {
  if (!target) return null;

  if (target instanceof HTMLInputElement) {
    return (
      Object.getOwnPropertyDescriptor(
        window.HTMLInputElement.prototype,
        "value",
      )?.set || null
    );
  }

  if (target instanceof HTMLTextAreaElement) {
    return (
      Object.getOwnPropertyDescriptor(
        window.HTMLTextAreaElement.prototype,
        "value",
      )?.set || null
    );
  }

  return null;
}

function clearEditableTarget(target) {
  if (!target) return;

  if (target.isContentEditable) {
    target.textContent = "";
    return;
  }

  if ("value" in target) {
    const setter = getNativeValueSetter(target);
    if (setter) {
      setter.call(target, "");
    } else {
      target.value = "";
    }
  }
}

function dispatchTypingEvents(target, text) {
  target.dispatchEvent(
    new InputEvent("input", {
      bubbles: true,
      data: text,
      inputType: "insertText",
    }),
  );
  target.dispatchEvent(new Event("change", { bubbles: true }));
}

async function typeIntoTarget(target, text) {
  if (!target) {
    throw new Error("No target found for typing");
  }

  if (!isTextInput(target)) {
    throw new Error(`Element is not typable: ${target.tagName}`);
  }

  if (typeof target.focus === "function") {
    target.focus();
  }

  await sleep(40);

  if (target.isContentEditable) {
    target.textContent = "";
    target.textContent = text;
    dispatchTypingEvents(target, text);
    return { typed: true, mode: "contenteditable" };
  }

  clearEditableTarget(target);

  const setter = getNativeValueSetter(target);
  if (setter) {
    setter.call(target, text);
  } else {
    target.value = text;
  }

  dispatchTypingEvents(target, text);
  return { typed: true, mode: target.tagName.toLowerCase() };
}

async function executeClickAction(payload, action) {
  let hit = null;
  if (action.pre_resolved_element) {
    hit = {
      el: action.pre_resolved_element,
      x: action.x,
      y: action.y,
      globalX: action.x,
      globalY: action.y,
      resolutionChain: "pre_resolved",
    };
  } else {
    const bbox = action.bbox || null;
    hit = getElementFromBBoxOrPoint(action, bbox);
  }

  if (!hit) {
    throw new Error("No element found for click");
  }

  if (hit.crossOriginError) {
    return {
      status: "error",
      error: "cross_origin_iframe_not_accessible",
      tag: hit.el?.tagName || "IFRAME",
      frame_url: hit.frame_url,
    };
  }

  const clickX =
    typeof action.x === "number"
      ? action.x
      : isValidBBox(bbox)
        ? getCenterFromBBox(bbox).x
        : hit.globalX || hit.x;

  const clickY =
    typeof action.y === "number"
      ? action.y
      : isValidBBox(bbox)
        ? getCenterFromBBox(bbox).y
        : hit.globalY || hit.y;

  let target = refineTargetForIntent(payload, action, hit.el, clickX, clickY);
  target = getBestClickableTarget(target);

  if (!target) {
    throw new Error("No clickable target found");
  }

  const rect = target.getBoundingClientRect();
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
  }

  target.scrollIntoView?.({
    block: "center",
    inline: "center",
    behavior: "instant",
  });
  await sleep(40);

  const { clientX, clientY } = clickElement(target, finalX, finalY);

  action.final_element = target;
  return {
    status: "clicked",
    resolved_via: hit.resolutionChain || "direct",
    tag: target.tagName,
    frame_url: hit.frame_url || null,
    x: clientX,
    y: clientY,
    focused: document.activeElement === target,
  };
}

async function executeTypeAction(payload, action) {
  const { text } = action;

  if (typeof text !== "string") {
    throw new Error("Missing text for type action");
  }

  let hit = null;
  if (action.pre_resolved_element) {
    hit = {
      el: action.pre_resolved_element,
      x: action.x,
      y: action.y,
      globalX: action.x,
      globalY: action.y,
      resolutionChain: "pre_resolved",
    };
  } else {
    const bbox = action.bbox || null;
    hit = getElementFromBBoxOrPoint(action, bbox);
  }

  if (!hit) {
    throw new Error("No element found for type");
  }

  if (hit.crossOriginError) {
    return {
      status: "error",
      error: "cross_origin_iframe_not_accessible",
      tag: hit.el?.tagName || "IFRAME",
      frame_url: hit.frame_url,
    };
  }

  const typeX =
    typeof action.x === "number"
      ? action.x
      : isValidBBox(bbox)
        ? getCenterFromBBox(bbox).x
        : hit.globalX || hit.x;

  const typeY =
    typeof action.y === "number"
      ? action.y
      : isValidBBox(bbox)
        ? getCenterFromBBox(bbox).y
        : hit.globalY || hit.y;

  let refined = refineTargetForIntent(payload, action, hit.el, typeX, typeY);
  let target = getBestTypableTarget(refined);

  if (!target) {
    throw new Error("No typable target found");
  }

  target.scrollIntoView?.({
    block: "center",
    inline: "center",
    behavior: "instant",
  });
  await sleep(30);

  if (!isTextInput(target)) {
    const clickable = getBestClickableTarget(refined);
    if (clickable) {
      clickElement(clickable, typeX, typeY);
      await sleep(80);
      target =
        getBestTypableTarget(document.activeElement) ||
        getBestTypableTarget(refined);
    }
  }

  if (!target || !isTextInput(target)) {
    return buildExecutionError(
      target ? target.tagName : hit.el ? hit.el.tagName : "UNKNOWN",
      hit.resolutionChain || "direct",
      typeX,
      typeY,
    );
  }

  if (typeof target.focus === "function") {
    target.focus();
  }

  await sleep(40);
  await typeIntoTarget(target, text);

  action.final_element = target;
  return {
    status: "typed",
    text,
    resolved_via: hit.resolutionChain || "direct",
    tag: target.tagName,
    frame_url: hit.frame_url || null,
    x: typeX,
    y: typeY,
    focused: document.activeElement === target,
  };
}

async function executeScrollAction(action) {
  const amount = Number(action.amount || 800);
  const direction = action.direction === "up" ? -1 : 1;

  const targetY = window.scrollY + direction * amount;

  window.scrollTo({
    top: targetY,
    left: 0,
    behavior: "smooth",
  });

  await sleep(400); // Give smooth scrolling more time to visibly finish before moving on

  return {
    status: "scrolled",
    amount,
    direction: direction === 1 ? "down" : "up",
  };
}

async function executeKeypressAction(action) {
  const key = action.key || "Enter";
  const target = document.activeElement || document.body;

  target.dispatchEvent(
    new KeyboardEvent("keydown", {
      key,
      bubbles: true,
      cancelable: true,
    }),
  );

  target.dispatchEvent(
    new KeyboardEvent("keyup", {
      key,
      bubbles: true,
      cancelable: true,
    }),
  );

  if (key === "Enter" && typeof target.form?.submit === "function") {
    try {
      target.form.submit();
    } catch (_) {}
  }

  return {
    status: "keypressed",
    key,
    tag: target.tagName,
  };
}

const KNOWN_ELEMENT_SELECTORS = {
  // Google Search
  "google search input": 'input[name="q"]',
  "search input": 'input[name="q"], input[type="search"]',
  "google search input field": 'input[name="q"]',
  // Google Forms
  "short answer": '[role="textbox"]',
  // Common patterns
  "email input": 'input[type="email"], input[name="email"]',
  "password input": 'input[type="password"]',
  "username input": 'input[name="username"], input[name="user"]',
  "submit button": '[type="submit"], [role="button"]',
};

function tryNamedElementLookup(target_description) {
  if (!target_description || typeof target_description !== "string")
    return null;
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
  const isIframe = resolvedTag === "IFRAME";

  return {
    status: "error",
    error: "resolved_element_not_typable",
    tag: resolvedTag,
    resolved_via: resolvedVia,
    x,
    y,
    suggestion: isIframe
      ? "iframe_pierce_required"
      : "check_scale_factors_and_snap_radius",
    debug_hint: isIframe
      ? "Element is an IFRAME wrapper. Use frame locator to access inner DOM."
      : `Element resolved to <${resolvedTag}> which is not typable. Likely a scale factor error - check SCALE_X/SCALE_Y values.`,
  };
}

function computeScaleFactors(screenshot_size) {
  let scale_x = 1;
  let scale_y = 1;

  if (screenshot_size && screenshot_size.width && screenshot_size.height) {
    scale_x = window.innerWidth / screenshot_size.width;
    scale_y = window.innerHeight / screenshot_size.height;
    console.log(
      `[SCALE DEBUG] Using dynamic screenshot size to compute scales: Viewport=${window.innerWidth}x${window.innerHeight}, Size=${screenshot_size.width}x${screenshot_size.height} => Scale_x=${scale_x.toFixed(4)}`,
    );
  } else {
    console.warn(
      `[SCALE WARNING] No screenshot_size provided, falling back to old logic!`,
    );
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

    scale_x = window.innerWidth / img_w;
    scale_y = window.innerHeight / img_h;
  }

  return { scale_x, scale_y };
}

function scale_coordinates(agent_x, agent_y, scale_x, scale_y) {
  return {
    x: agent_x * scale_x,
    y: agent_y * scale_y,
  };
}

function resolve_label_target(label_element) {
  if (
    label_element.tagName &&
    label_element.tagName.toLowerCase() === "label" &&
    label_element.htmlFor
  ) {
    const target = document.getElementById(label_element.htmlFor);
    if (target) {
      const rect = target.getBoundingClientRect();
      if (rect.width > 0 && rect.height > 0) {
        return {
          element: target,
          true_center: {
            x: rect.left + rect.width / 2,
            y: rect.top + rect.height / 2,
          },
        };
      }
    }
  }
  return null;
}

function find_best_interactive_element(real_x, real_y) {
  const radii = [10, 20, 40, 80, 160];

  const selectors =
    "input:not([type='hidden']), textarea, select, button, a[href], [role='button'], [role='checkbox'], [role='radio'], [role='combobox'], [role='listbox'], [tabindex]:not([tabindex='-1']), label";
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
      console.log(
        `[SNAP HIT] radius=${radius}px, tag=${best_cand.tagName}, dist=${best_dist.toFixed(1)}px`,
      );
      const labelRes = resolve_label_target(best_cand);
      if (labelRes) {
        return {
          element: labelRes.element,
          true_center: labelRes.true_center,
          distance: best_dist,
        };
      }
      return {
        element: best_cand,
        true_center: best_center,
        distance: best_dist,
      };
    }
  }

  return null;
}
function try_selector_fast_path(target_description) {
  if (!target_description || typeof target_description !== "string")
    return null;
  if (
    target_description.includes("[") ||
    target_description.includes("input") ||
    target_description.includes("placeholder") ||
    target_description.includes("#") ||
    target_description.includes(".")
  ) {
    try {
      let isSingleQuote =
        target_description.includes("'") || target_description.includes('"');
      let isQuery =
        target_description.startsWith("*[ ") ||
        target_description.startsWith("[") ||
        target_description.startsWith("input");
      if (isQuery || isSingleQuote) {
        let el = document.querySelector(target_description);
        if (el) {
          const rect = el.getBoundingClientRect();
          if (rect.width > 0 && rect.height > 0) {
            const style = window.getComputedStyle(el);
            if (style.display !== "none" && style.visibility !== "hidden") {
              console.log(`Fast path hit for selector: ${target_description}`);
              return {
                element: el,
                true_center: {
                  x: rect.left + rect.width / 2,
                  y: rect.top + rect.height / 2,
                },
              };
            }
          }
        }
      }
    } catch (e) {}
  }
  return null;
}

async function verify_action(action_type, element, intended_text) {
  if (!element)
    return { verified: false, error: "No element provided to verify" };

  if (action_type === "click") {
    const isActive = document.activeElement === element;
    if (!isActive) {
      try {
        if (typeof element.focus === "function") {
          element.focus();
        }
      } catch (e) {}
    }
    return {
      verified: document.activeElement === element,
      active_element_tag: document.activeElement
        ? document.activeElement.tagName
        : null,
      active_element_id: document.activeElement
        ? document.activeElement.id
        : null,
    };
  }

  if (action_type === "type") {
    let actual_value = element.value || element.textContent || "";
    if (actual_value === intended_text) {
      return { verified: true, typed: intended_text, actual_value };
    }

    // retry once
    try {
      clearEditableTarget(element);
      const setter = getNativeValueSetter(element);
      if (setter) {
        setter.call(element, intended_text);
      } else {
        element.value = intended_text;
      }
      dispatchTypingEvents(element, intended_text);
    } catch (e) {}

    actual_value = element.value || element.textContent || "";
    return {
      verified: actual_value === intended_text,
      typed: intended_text,
      actual_value,
    };
  }
  return { verified: true };
}

async function executeAction(payload) {
  const processAction = { ...(payload?.next_action || {}) };

  if (payload?.status === "completed" || processAction.type === "none") {
    return {
      status: "completed",
      executed: false,
      reason: payload?.reason || "Task already completed",
    };
  }

  let scale_hints = computeScaleFactors(payload._screenshot_size);
  let snapInfo = {};

  if (
    (processAction.type === "click" || processAction.type === "type") &&
    typeof processAction.x === "number" &&
    typeof processAction.y === "number"
  ) {
    const scaled = scale_coordinates(
      processAction.x,
      processAction.y,
      scale_hints.scale_x,
      scale_hints.scale_y,
    );
    let real_x = scaled.x;
    let real_y = scaled.y;

    if (processAction.bbox && isValidBBox(processAction.bbox)) {
      processAction.bbox = {
        x1: processAction.bbox.x1 * scale_hints.scale_x,
        y1: processAction.bbox.y1 * scale_hints.scale_y,
        x2: processAction.bbox.x2 * scale_hints.scale_x,
        y2: processAction.bbox.y2 * scale_hints.scale_y,
      };
    }

    let fast_path = null;
    let named_el = tryNamedElementLookup(processAction.target_description);
    if (named_el) {
      const r = named_el.getBoundingClientRect();
      fast_path = {
        element: named_el,
        true_center: { x: r.left + r.width / 2, y: r.top + r.height / 2 },
      };
    } else {
      fast_path = try_selector_fast_path(processAction.target_description);
    }

    let snap = null;

    if (!fast_path) {
      snap = find_best_interactive_element(real_x, real_y);
    }

    if (fast_path) {
      processAction.pre_resolved_element = fast_path.element;
      real_x = fast_path.true_center.x;
      real_y = fast_path.true_center.y;
      snapInfo = { snap: "selector_fast_path" };
    } else if (snap) {
      processAction.pre_resolved_element = snap.element;
      real_x = snap.true_center.x;
      real_y = snap.true_center.y;
      snapInfo = {
        snap: "snapped",
        snapped_from: { x: scaled.x, y: scaled.y },
        snapped_to: { x: real_x, y: real_y },
        element: snap.element.tagName,
        distance_px: snap.distance,
      };
    } else {
      snapInfo = { snap: "no_candidate", used_raw: { x: real_x, y: real_y } };
    }

    processAction.x = real_x;
    processAction.y = real_y;
  }

  const action = processAction;
  const bbox = action?.bbox || null;
  if (bbox) showBoundingBox(bbox);
  if (typeof action.x === "number" && typeof action.y === "number") {
    showPointMarker(
      action.x,
      action.y,
      action.type === "type" ? "blue" : "red",
    );
  }

  let res;
  switch (action.type) {
    case "click":
      res = await executeClickAction(payload, action);
      break;
    case "type":
      res = await executeTypeAction(payload, action);
      break;
    case "scroll":
      res = await executeScrollAction(action);
      break;
    case "keypress":
      res = await executeKeypressAction(action);
      break;
    default:
      throw new Error(`Unknown action type: ${action.type}`);
  }

  if (action.type === "click" || action.type === "type") {
    const verified = await verify_action(
      action.type,
      action.pre_resolved_element || action.final_element,
      action.text,
    );
    res.verification = verified;
    res.snap_info = snapInfo;
  }

  return res;
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  console.log("message received in content.js:", message);

  if (message.type !== "EXECUTE_ACTION") {
    return false;
  }

  (async () => {
    try {
      const payload = message.payload || {};
      const result = await executeAction(payload);
      sendResponse(result);
    } catch (error) {
      sendResponse({
        status: "error",
        error: error?.message || String(error),
      });
    }
  })();

  return true;
});
