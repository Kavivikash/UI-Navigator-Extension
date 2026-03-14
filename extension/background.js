chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "RUN_ACTION_ON_PAGE") {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      const activeTab = tabs[0];

      if (!activeTab?.id) {
        sendResponse({ status: "error", error: "No active tab found" });
        return;
      }

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

          sendResponse(response || { status: "no_response" });
        },
      );
    });

    return true;
  }

  if (message.type === "CAPTURE_SCREENSHOT") {
    chrome.tabs.captureVisibleTab(null, { format: "png" }, (dataUrl) => {
      if (chrome.runtime.lastError) {
        sendResponse({ error: chrome.runtime.lastError.message });
        return;
      }

      sendResponse({ screenshot: dataUrl });
    });

    return true;
  }
});
