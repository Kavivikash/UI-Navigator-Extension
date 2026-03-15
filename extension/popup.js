const BACKEND_URL = "http://127.0.0.1:8000/agent";
const MAX_STEPS = 8;

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function appendResult(text) {
  const resultBox = document.getElementById("result");
  resultBox.textContent += text;
  resultBox.scrollTop = resultBox.scrollHeight;
}

function setResult(text) {
  const resultBox = document.getElementById("result");
  resultBox.textContent = text;
  resultBox.scrollTop = resultBox.scrollHeight;
}

function normalizeExecutionStatus(status) {
  return String(status || "").toLowerCase();
}

function getPostActionDelay(actionType) {
  switch (actionType) {
    case "click":
      return 250;
    case "type":
      return 180;
    case "scroll":
      return 350;
    case "keypress":
      return 220;
    default:
      return 200;
  }
}

async function measureScreenshot(dataUrl) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve({ width: img.width, height: img.height });
    img.onerror = () =>
      reject(new Error("Failed to load image for measurement"));
    img.src = dataUrl;
  });
}

async function captureScreenshot() {
  return new Promise((resolve, reject) => {
    chrome.runtime.sendMessage({ type: "CAPTURE_SCREENSHOT" }, (response) => {
      if (chrome.runtime.lastError) {
        reject(new Error(chrome.runtime.lastError.message));
        return;
      }

      if (!response) {
        reject(new Error("No response received while capturing screenshot."));
        return;
      }

      if (response.status === "error" || response.error) {
        reject(new Error(response.error || "Screenshot capture failed."));
        return;
      }

      if (!response.screenshot) {
        reject(new Error("Screenshot missing from response."));
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
          reject(new Error(chrome.runtime.lastError.message));
          return;
        }

        if (!response) {
          reject(new Error("No response received from page executor."));
          return;
        }

        resolve(response);
      },
    );
  });
}

async function callAgent(command, screenshot, step, memory) {
  const response = await fetch(BACKEND_URL, {
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

  const data = await response.json();

  if (!response.ok) {
    const detail =
      typeof data?.detail === "string"
        ? data.detail
        : JSON.stringify(data?.detail || data);
    throw new Error(detail || `Backend error (${response.status})`);
  }

  return data;
}

function shouldStopBecauseDone(agentResult) {
  return (
    agentResult?.status === "completed" ||
    agentResult?.next_action?.type === "none"
  );
}

function isExecutionSuccess(executionResult) {
  const status = normalizeExecutionStatus(executionResult?.status);

  return ["clicked", "typed", "scrolled", "keypressed", "completed"].includes(
    status,
  );
}

function summarizeExecutionResult(executionResult) {
  const status = executionResult?.status || "unknown";

  if (executionResult?.error) {
    return `error: ${executionResult.error}`;
  }

  if (status === "typed" && executionResult?.text) {
    return `typed: ${executionResult.text}`;
  }

  if (status === "keypressed" && executionResult?.key) {
    return `keypressed: ${executionResult.key}`;
  }

  return status;
}

function pushMemory(memory, step, agentResult, executionResult) {
  memory.history.push({
    step,
    action: agentResult?.next_action || null,
    screen_summary: agentResult?.screen_summary || "",
    result_summary: summarizeExecutionResult(executionResult),
  });

  if (memory.history.length > 5) {
    memory.history = memory.history.slice(-5);
  }
}

function formatJsonBlock(label, obj) {
  return `\n${label}:\n${JSON.stringify(obj, null, 2)}\n`;
}

async function runAgentLoop(command) {
  const memory = { history: [] };

  setResult("Running agent loop...\n");

  for (let step = 1; step <= MAX_STEPS; step++) {
    appendResult(`\n--- Step ${step} ---\n`);
    appendResult("Capturing screenshot...\n");
    const screenshot = await captureScreenshot();
    let capSize = null;
    try {
      capSize = await measureScreenshot(screenshot);
      console.log("Captured screenshot size:", capSize);
    } catch (e) {}

    appendResult("Calling agent...\n");
    const agentResult = await callAgent(command, screenshot, step, memory);
    if (agentResult && capSize) {
      agentResult._screenshot_size = capSize;
    }
    appendResult(formatJsonBlock("Agent Result", agentResult));

    if (agentResult?.error) {
      appendResult(`\nAgent error: ${agentResult.error}\n`);
      return;
    }

    if (shouldStopBecauseDone(agentResult)) {
      appendResult("\nTask completed.\n");
      return;
    }

    if (agentResult?.needs_confirmation) {
      appendResult(
        "\nStopped: agent requested confirmation for a potentially risky action.\n",
      );
      return;
    }

    appendResult("Executing action on page...\n");
    const executionResult = await runActionOnPage(agentResult);
    appendResult(formatJsonBlock("Execution Result", executionResult));

    pushMemory(memory, step, agentResult, executionResult);

    if (!isExecutionSuccess(executionResult)) {
      appendResult(
        `\nExecution failed or was not successful enough to continue.\n`,
      );
      return;
    }

    const actionType = agentResult?.next_action?.type || "unknown";
    const delay = getPostActionDelay(actionType);

    appendResult(`Waiting ${delay}ms for UI to settle...\n`);
    await sleep(delay);
  }

  appendResult(
    `\nStopped after ${MAX_STEPS} steps to avoid an infinite loop.\n`,
  );
}

document.getElementById("sendBtn").addEventListener("click", async () => {
  const commandInput = document.getElementById("commandInput");
  const sendBtn = document.getElementById("sendBtn");
  const command = commandInput.value.trim();

  if (!command) {
    setResult("Please enter a command.");
    return;
  }

  sendBtn.disabled = true;
  commandInput.disabled = true;

  try {
    await runAgentLoop(command);
  } catch (error) {
    appendResult(`\nError: ${error?.message || String(error)}\n`);
  } finally {
    sendBtn.disabled = false;
    commandInput.disabled = false;
  }
});

async function handleExecutionError(errorObj, command, tabId) {
  console.warn("[RECOVERY] Execution error intercepted:", errorObj);

  if (errorObj.suggestion === "iframe_pierce_required") {
    return {
      status: "error",
      reason: "Cross-origin iframe boundary hit. Agent needs URL parameter.",
      fatal: true,
    };
  }

  if (
    errorObj.suggestion === "check_scale_factors_and_snap_radius" &&
    errorObj.x
  ) {
    console.log("[RECOVERY] Attempting Unscaled Retry...");
    const result_unscaled = await runActionOnPage({
      next_action: {
        type: "click",
        x: errorObj.x / 1.875,
        y: errorObj.y / 1.875,
      },
    });
    if (
      result_unscaled &&
      ["clicked", "typed", "completed"].includes(result_unscaled.status)
    ) {
      return result_unscaled;
    }
  }

  if (
    command.toLowerCase().includes("google") ||
    command.toLowerCase().includes("search")
  ) {
    console.log("[RECOVERY] Attempting Named Selector Hardcode...");
    const result_named = await runActionOnPage({
      next_action: {
        type: "type",
        text: command.split("for ")[1] || command,
        target_description: "google search input field",
      },
    });
    if (
      result_named &&
      ["clicked", "typed", "completed"].includes(result_named.status)
    ) {
      return result_named;
    }
  }

  return { status: "error", reason: errorObj.error, fatal: false };
}
