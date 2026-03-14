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
        resolve(response || { status: "no_response" });
      },
    );
  });
}

async function callAgent(command, screenshot, step, memory) {
  const response = await fetch("http://127.0.0.1:8000/agent", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      command,
      screenshot,
      step,
      memory,
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

  const memory = { history: [] };
  resultBox.textContent = "Running agent loop...\n";

  try {
    for (let step = 1; step <= 5; step++) {
      const screenshot = await captureScreenshot();
      const agentResult = await callAgent(command, screenshot, step, memory);

      resultBox.textContent += `\nStep ${step}:\n${JSON.stringify(agentResult, null, 2)}\n`;

      if (agentResult.error) {
        resultBox.textContent += `\nAgent error: ${agentResult.error}`;
        break;
      }

      if (
        agentResult.status === "completed" ||
        agentResult.next_action?.type === "none"
      ) {
        resultBox.textContent += "\nTask completed.";
        break;
      }

      const executionResult = await runActionOnPage(agentResult);

      resultBox.textContent += `Execution Result:\n${JSON.stringify(executionResult, null, 2)}\n`;

      memory.history.push({
        step,
        action: agentResult.next_action,
        screen_summary: agentResult.screen_summary || "",
        result_summary: executionResult?.status || "executed",
      });

      if (
        executionResult?.status === "clicked" ||
        executionResult?.status === "typed" ||
        executionResult?.status === "typed in contenteditable" ||
        executionResult?.status === "scrolled"
      ) {
        resultBox.textContent += "\nTask completed.";
        break;
      }

      await new Promise((resolve) => setTimeout(resolve, 1200));
    }
  } catch (error) {
    resultBox.textContent += `\nError: ${error}`;
  }
});
