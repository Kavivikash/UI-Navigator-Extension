import sys

with open('content.js', 'r', encoding='utf-8') as f:
    text = f.read()

new_helpers = '''function compute_scale_factors() {
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
  
  return {
    scale_x: window.innerWidth / img_w,
    scale_y: window.innerHeight / img_h
  };
}

function scale_coordinates(agent_x, agent_y, scale_x, scale_y) {
  return {
    x: agent_x * scale_x,
    y: agent_y * scale_y
  };
}

function resolve_label_target(label_element) {
  if (label_element.tagName && label_element.tagName.toLowerCase() === 'label' && label_element.htmlFor) {
    const target = document.getElementById(label_element.htmlFor);
    if (target) {
      const rect = target.getBoundingClientRect();
      if (rect.width > 0 && rect.height > 0) {
        return {
          element: target,
          true_center: {
            x: rect.left + rect.width / 2,
            y: rect.top + rect.height / 2
          }
        };
      }
    }
  }
  return null;
}

function find_best_interactive_element(real_x, real_y, search_radius=40) {
  const selectors = "input, textarea, select, button, a[href], [role='button'], [role='checkbox'], [role='radio'], [role='combobox'], [role='listbox'], [tabindex]:not([tabindex='-1']), label";
  const candidates = Array.from(document.querySelectorAll(selectors));
  
  let best_dist = Infinity;
  let best_cand = null;
  let best_center = null;

  for (const el of candidates) {
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) continue;
    
    const style = window.getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden') continue;
    
    const true_center = {
      x: rect.left + rect.width / 2,
      y: rect.top + rect.height / 2
    };
    
    const dist = Math.hypot(true_center.x - real_x, true_center.y - real_y);
    if (dist < best_dist) {
      best_dist = dist;
      best_cand = el;
      best_center = true_center;
    }
  }

  if (best_cand && best_dist <= search_radius) {
    const labelRes = resolve_label_target(best_cand);
    if (labelRes) {
      console.log(`Resolved label ${best_cand.htmlFor} to target`);
      return { element: labelRes.element, true_center: labelRes.true_center, distance: best_dist };
    }
    return { element: best_cand, true_center: best_center, distance: best_dist };
  }
  
  if (search_radius === 40) {
    return find_best_interactive_element(real_x, real_y, 80);
  }
  
  return null;
}

function try_selector_fast_path(target_description) {
  if (!target_description || typeof target_description !== 'string') return null;
  if (target_description.includes('[') || target_description.includes('input') || target_description.includes('placeholder') || target_description.includes('#') || target_description.includes('.')) {
    try {
      let isSingleQuote = target_description.includes("'") || target_description.includes('"');
      let isQuery = target_description.startsWith("*[ ") || target_description.startsWith("[") || target_description.startsWith("input");
      if (isQuery || isSingleQuote) {
         let el = document.querySelector(target_description);
         if (el) {
           const rect = el.getBoundingClientRect();
           if (rect.width > 0 && rect.height > 0) {
             const style = window.getComputedStyle(el);
             if (style.display !== 'none' && style.visibility !== 'hidden') {
               console.log(`Fast path hit for selector: ${target_description}`);
               return {
                 element: el,
                 true_center: {
                   x: rect.left + rect.width / 2,
                   y: rect.top + rect.height / 2
                 }
               };
             }
           }
         }
      }
    } catch (e) {
    }
  }
  return null;
}

async function verify_action(action_type, element, intended_text) {
  if (!element) return { verified: false, error: "No element provided to verify" };
  
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
      active_element_tag: document.activeElement ? document.activeElement.tagName : null,
      active_element_id: document.activeElement ? document.activeElement.id : null
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
      actual_value
    };
  }
  return { verified: true };
}

async function executeAction(payload) {'''

text = text.replace('async function executeAction(payload) {', new_helpers)

new_execute = '''
  const processAction = { ...(payload?.next_action || {}) };
  
  if (payload?.status === "completed" || processAction.type === "none") {
    return { status: "completed", executed: false, reason: payload?.reason || "Task already completed" };
  }

  let scale_hints = compute_scale_factors();
  let snapInfo = {};
  
  if ((processAction.type === "click" || processAction.type === "type") && typeof processAction.x === "number" && typeof processAction.y === "number") {
    const scaled = scale_coordinates(processAction.x, processAction.y, scale_hints.scale_x, scale_hints.scale_y);
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
    
    let fast_path = try_selector_fast_path(processAction.target_description);
    let snap = null;
    
    if (!fast_path) {
      snap = find_best_interactive_element(real_x, real_y, 40);
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
      snapInfo = { snap: "snapped", snapped_from: {x: scaled.x, y: scaled.y}, snapped_to: {x: real_x, y: real_y}, element: snap.element.tagName, distance_px: snap.distance };
    } else {
      snapInfo = { snap: "no_candidate", used_raw: {x: real_x, y: real_y} };
    }
    
    processAction.x = real_x;
    processAction.y = real_y;
  }
  
  const action = processAction;
  const bbox = action?.bbox || null;
  if (bbox) showBoundingBox(bbox);
  if (typeof action.x === "number" && typeof action.y === "number") {
    showPointMarker(action.x, action.y, action.type === "type" ? "blue" : "red");
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
    const verified = await verify_action(action.type, action.pre_resolved_element || action.final_element, action.text);
    res.verification = verified;
    res.snap_info = snapInfo;
  }
  
  return res;
}'''

lines = text.split('\n')
execute_idx = -1
for i, line in enumerate(lines):
    if line.startswith('async function executeAction(payload)'):
        execute_idx = i
        break

if execute_idx != -1:
    end_idx = -1
    for i in range(execute_idx + 1, len(lines)):
        if lines[i].startswith('chrome.runtime.onMessage.addListener'):
            end_idx = i
            break
            
    if end_idx != -1:
        del lines[execute_idx+1:end_idx]
        lines.insert(execute_idx + 1, new_execute + '\n')
        text = '\n'.join(lines)


with open('content.js', 'w', encoding='utf-8') as f:
    f.write(text)
print('Updated executeAction')
