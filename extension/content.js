console.log("content.js loaded");

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  console.log("message received in content.js:", message);

  if (message.type === "EXECUTE_ACTION") {
    const action = message.payload.next_action;
    console.log("action:", action);

    if (action.type === "click") {
      const { x, y } = action;

      const marker = document.createElement("div");
      marker.style.position = "fixed";
      marker.style.left = `${x - 10}px`;
      marker.style.top = `${y - 10}px`;
      marker.style.width = "20px";
      marker.style.height = "20px";
      marker.style.borderRadius = "50%";
      marker.style.background = "red";
      marker.style.zIndex = "999999";
      marker.style.pointerEvents = "none";
      document.body.appendChild(marker);

      setTimeout(() => marker.remove(), 1000);

      const el = document.elementFromPoint(x, y);
      if (el) {
        el.click();
        sendResponse({ status: "clicked", tag: el.tagName });
      } else {
        sendResponse({ status: "no element found" });
      }
    } else if (action.type === "scroll") {
      window.scrollBy(0, action.amount || 500);
      sendResponse({ status: "scrolled", amount: action.amount || 500 });
    } else if (action.type === "type") {
      const { x, y, text } = action;
      const el = document.elementFromPoint(x, y);

      if (!el) {
        sendResponse({ status: "no element found" });
        return true;
      }

      el.focus();

      const target =
        el.tagName === "INPUT" || el.tagName === "TEXTAREA"
          ? el
          : el.querySelector?.("input, textarea, [contenteditable='true']") ||
            el;

      if (target.isContentEditable) {
        target.textContent = text;
        target.dispatchEvent(
          new InputEvent("input", { bubbles: true, data: text }),
        );
        sendResponse({ status: "typed in contenteditable", text });
      } else if ("value" in target) {
        const nativeSetter =
          Object.getOwnPropertyDescriptor(
            window.HTMLInputElement.prototype,
            "value",
          )?.set ||
          Object.getOwnPropertyDescriptor(
            window.HTMLTextAreaElement.prototype,
            "value",
          )?.set;

        if (nativeSetter) {
          nativeSetter.call(target, text);
        } else {
          target.value = text;
        }

        target.dispatchEvent(new Event("input", { bubbles: true }));
        target.dispatchEvent(new Event("change", { bubbles: true }));
        sendResponse({ status: "typed", text, tag: target.tagName });
      } else {
        sendResponse({ status: "element not typable", tag: target.tagName });
      }
    } else {
      sendResponse({ status: "unknown action" });
    }
  }

  return true;
});
