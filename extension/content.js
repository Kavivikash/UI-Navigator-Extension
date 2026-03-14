console.log("content.js loaded");

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

function getElementFromBBoxOrPoint(action, bbox) {
  const tryPoints = [];

  if (
    bbox &&
    [bbox.x1, bbox.y1, bbox.x2, bbox.y2].every((v) => typeof v === "number")
  ) {
    const cx = Math.round((bbox.x1 + bbox.x2) / 2);
    const cy = Math.round((bbox.y1 + bbox.y2) / 2);

    tryPoints.push(
      [cx, cy],
      [cx, bbox.y1 + 8],
      [cx, bbox.y2 - 8],
      [bbox.x1 + 8, cy],
      [bbox.x2 - 8, cy],
    );
  }

  if (typeof action.x === "number" && typeof action.y === "number") {
    tryPoints.push([action.x, action.y]);
  }

  for (const [x, y] of tryPoints) {
    const el = document.elementFromPoint(x, y);
    if (!el) continue;

    const preferred = el.closest(
      "input, textarea, [contenteditable='true'], button, a, select, label, [role='button']",
    );

    if (preferred) {
      return { el: preferred, x, y };
    }

    return { el, x, y };
  }

  return null;
}

function dispatchRealClick(el, x, y) {
  const rect = el.getBoundingClientRect();
  const clickX = Math.round(rect.left + rect.width / 2);
  const clickY = Math.round(rect.top + rect.height / 2);

  const events = ["pointerdown", "mousedown", "pointerup", "mouseup", "click"];

  for (const type of events) {
    el.dispatchEvent(
      new MouseEvent(type, {
        view: window,
        bubbles: true,
        cancelable: true,
        clientX: clickX || x,
        clientY: clickY || y,
      }),
    );
  }
}

function isFocusable(el) {
  if (!el) return false;
  const tag = el.tagName;
  return (
    tag === "INPUT" ||
    tag === "TEXTAREA" ||
    tag === "SELECT" ||
    el.isContentEditable ||
    typeof el.focus === "function"
  );
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  console.log("message received in content.js:", message);

  if (message.type !== "EXECUTE_ACTION") {
    return true;
  }

  const payload = message.payload || {};
  const action = payload.next_action || {};
  const bbox = payload.target?.bbox;

  showBoundingBox(bbox);

  console.log("action:", action);

  if (payload.status === "completed" || action.type === "none") {
    sendResponse({
      status: "completed",
      executed: false,
      reason: payload.reason || "Task already completed",
    });
    return true;
  }

  if (action.type === "click") {
    const { x, y } = action;

    if (typeof x !== "number" || typeof y !== "number") {
      sendResponse({ status: "invalid_click_coordinates" });
      return true;
    }

    showPointMarker(x, y);

    const hit = getElementFromBBoxOrPoint(action, bbox);
    if (!hit) {
      sendResponse({ status: "no element found" });
      return true;
    }
    const el = hit.el;
    const actualTarget = el.matches("input, textarea, [contenteditable='true']")
      ? el
      : el.querySelector?.("input, textarea, [contenteditable='true']") || el;

    if (!el) {
      sendResponse({ status: "no element found" });
      return true;
    }

    if (isFocusable(actualTarget)) {
      actualTarget.focus();
    }

    dispatchRealClick(actualTarget, x, y);

    const focused = document.activeElement === actualTarget;
    sendResponse({
      status: "clicked",
      tag: actualTarget.tagName,
      focused,
    });
    return true;
  }

  if (action.type === "scroll") {
    const amount = Number(action.amount || 500);
    const direction = action.direction === "up" ? -1 : 1;

    window.scrollBy({
      top: direction * amount,
      left: 0,
      behavior: "smooth",
    });

    sendResponse({
      status: "scrolled",
      amount,
      direction: direction === 1 ? "down" : "up",
    });
    return true;
  }

  if (action.type === "type") {
    const { x, y, text } = action;

    if (typeof x !== "number" || typeof y !== "number") {
      sendResponse({ status: "invalid_type_coordinates" });
      return true;
    }

    showPointMarker(x, y, "blue");

    const hit = getElementFromBBoxOrPoint(action, bbox);
    if (!hit) {
      sendResponse({ status: "no element found" });
      return true;
    }
    const el = hit.el;
    if (!el) {
      sendResponse({ status: "no element found" });
      return true;
    }

    if (typeof el.focus === "function") {
      el.focus();
    }

    const target =
      el.tagName === "INPUT" || el.tagName === "TEXTAREA"
        ? el
        : el.querySelector?.("input, textarea, [contenteditable='true']") || el;

    if (target.isContentEditable) {
      target.textContent = text;
      target.dispatchEvent(
        new InputEvent("input", { bubbles: true, data: text }),
      );
      sendResponse({ status: "typed in contenteditable", text });
      return true;
    }

    if ("value" in target) {
      const inputSetter = Object.getOwnPropertyDescriptor(
        window.HTMLInputElement.prototype,
        "value",
      )?.set;

      const textAreaSetter = Object.getOwnPropertyDescriptor(
        window.HTMLTextAreaElement.prototype,
        "value",
      )?.set;

      const setter = inputSetter || textAreaSetter;

      if (setter) {
        setter.call(target, text);
      } else {
        target.value = text;
      }

      target.dispatchEvent(new Event("input", { bubbles: true }));
      target.dispatchEvent(new Event("change", { bubbles: true }));

      sendResponse({
        status: "typed",
        text,
        tag: target.tagName,
      });
      return true;
    }

    sendResponse({
      status: "element not typable",
      tag: target.tagName,
    });
    return true;
  }

  sendResponse({ status: "unknown action", actionType: action.type });
  return true;
});
