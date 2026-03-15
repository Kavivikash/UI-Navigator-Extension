with open('c:/Projects/UI-nav/extension/popup.js', 'r', encoding='utf-8') as f:
    text = f.read()

old_block = """      appendResult("Executing action on page...\\n");
      const executionResult = await runActionOnPage(agentResult);
      appendResult(formatJsonBlock("Execution Result", executionResult));

      pushMemory(memory, step, agentResult, executionResult);

      if (!isExecutionSuccess(executionResult)) {
        appendResult(
          `\\nExecution failed or was not successful enough to continue.\\n`,
        );
        return;
      }"""

new_block = """      appendResult("Executing action on page...\\n");
      let executionResult = await runActionOnPage(agentResult);
      appendResult(formatJsonBlock("Execution Result", executionResult));

      if (!isExecutionSuccess(executionResult) && executionResult?.error) {
         const activeTabs = await chrome.tabs.query({ active: true, currentWindow: true });
         if (activeTabs && activeTabs[0]) {
            const recoveryResult = await handleExecutionError(executionResult, command, activeTabs[0].id);
            if (recoveryResult && (recoveryResult.success || recoveryResult.status === 'success')) {
               executionResult = recoveryResult;
               appendResult(formatJsonBlock("Recovery Success", executionResult));
            } else if (recoveryResult && recoveryResult.fatal) {
               appendResult("\\nFatal Error during recovery, stopping...\\n");
               return;
            }
         }
      }

      pushMemory(memory, step, agentResult, executionResult);

      if (!isExecutionSuccess(executionResult) && (!executionResult || executionResult.status !== 'success')) {
        appendResult(
          `\\nExecution failed or was not successful enough to continue.\\n`,
        );
        return;
      }"""

text = text.replace(old_block, new_block)

with open('c:/Projects/UI-nav/extension/popup.js', 'w', encoding='utf-8') as f:
    f.write(text)
print('popup.js loop updated')
