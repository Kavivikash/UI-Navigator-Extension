async function captureScreenshot() {
  return new Promise((resolve, reject) => {
    chrome.runtime.sendMessage({ type: "CAPTURE_SCREENSHOT" }, (response) => {
      if (chrome.runtime.lastError) {
        reject(chrome.runtime.lastError.message);
        return;
      }
      if (response?.error) {
        reject(response.error);
        return;
      }
      resolve(response.screenshot);
    });
  });
}

async function runActionOnPage(actionData) {
  return new Promise((resolve, reject) => {
    chrome.runtime.sendMessage(
      {
        type: "RUN_ACTION_ON_PAGE",
        payload: actionData,
      },
      (response) => {
        if (chrome.runtime.lastError) {
          reject(chrome.runtime.lastError.message);
          return;
        }
        resolve(response);
      },
    );
  });
}

async function callAgent(command, screenshot, step) {
  const response = await fetch("http://127.0.0.1:8000/agent", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      command,
      screenshot,
      step,
    }),
  });

  return await response.json();
}

document.getElementById("sendBtn").addEventListener("click", async () => {
  const command = document.getElementById("commandInput").value.trim();
  const resultBox = document.getElementById("result");

  if (!command) {
    resultBox.textContent = "Please enter a command.";
    return;
  }

  resultBox.textContent = "Running agent loop...\n";

  try {
    for (let step = 1; step <= 3; step++) {
      const screenshot = await captureScreenshot();
      const agentResult = await callAgent(command, screenshot, step);

      resultBox.textContent += `\nStep ${step}:\n${JSON.stringify(agentResult, null, 2)}\n`;

      await runActionOnPage(agentResult);

      if (agentResult.status === "completed") {
        resultBox.textContent += "\nTask completed.";
        break;
      }

      await new Promise((resolve) => setTimeout(resolve, 1500));
    }
  } catch (error) {
    resultBox.textContent += `\nError: ${error}`;
  }
});
