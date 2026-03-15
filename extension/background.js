async function getActiveTab() {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  return tabs[0];
}

async function waitForTabComplete(tabId, timeoutMs = 8000) {
  const tab = await chrome.tabs.get(tabId);
  if (tab.status === "complete") return;

  await new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      chrome.tabs.onUpdated.removeListener(listener);
      reject(new Error("Timed out waiting for tab to finish loading"));
    }, timeoutMs);

    function listener(updatedTabId, info) {
      if (updatedTabId === tabId && info.status === "complete") {
        clearTimeout(timeout);
        chrome.tabs.onUpdated.removeListener(listener);
        resolve();
      }
    }

    chrome.tabs.onUpdated.addListener(listener);
  });
}

async function pingContentScript(tabId) {
  return await chrome.tabs.sendMessage(tabId, { type: "PING" });
}

async function ensureContentScript(tabId) {
  try {
    await pingContentScript(tabId);
    return;
  } catch (_) {
    await chrome.scripting.executeScript({
      target: { tabId },
      files: ["content.js"],
    });

    await new Promise((resolve) => setTimeout(resolve, 120));
    await pingContentScript(tabId);
  }
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  (async () => {
    try {
      if (message.type === "RUN_ACTION_ON_PAGE") {
        const activeTab = await getActiveTab();

        if (!activeTab?.id) {
          sendResponse({ status: "error", error: "No active tab found" });
          return;
        }

        await waitForTabComplete(activeTab.id);
        await ensureContentScript(activeTab.id);

        chrome.tabs.sendMessage(
          activeTab.id,
          {
            type: "EXECUTE_ACTION",
            payload: message.payload,
          },
          (response) => {
            if (chrome.runtime.lastError) {
              sendResponse({
                status: "error",
                error: chrome.runtime.lastError.message,
              });
              return;
            }

            sendResponse(
              response || {
                status: "error",
                error: "No response from content script",
              },
            );
          },
        );

        return;
      }

      if (message.type === "CAPTURE_SCREENSHOT") {
        const activeTab = await getActiveTab();

        if (!activeTab?.id) {
          sendResponse({ status: "error", error: "No active tab found" });
          return;
        }

        await waitForTabComplete(activeTab.id);

        chrome.tabs.captureVisibleTab(
          null,
          { format: "jpeg", quality: 75 },
          (dataUrl) => {
            if (chrome.runtime.lastError) {
              sendResponse({
                status: "error",
                error: chrome.runtime.lastError.message,
              });
              return;
            }

            sendResponse({ status: "success", screenshot: dataUrl });
          },
        );

        return;
      }

      sendResponse({ status: "error", error: "Unknown message type" });
    } catch (error) {
      sendResponse({
        status: "error",
        error: error?.message || String(error),
      });
    }
  })();

  return true;
});
