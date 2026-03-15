with open('c:/Projects/UI-nav/extension/popup.js', 'r', encoding='utf-8') as f:
    text = f.read()

# Add function to measure screenshot
measurer = """async function measureScreenshot(dataUrl) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve({ width: img.width, height: img.height });
    img.onerror = () => reject(new Error("Failed to load image for measurement"));
    img.src = dataUrl;
  });
}

"""
if 'function measureScreenshot' not in text:
    text = text.replace('async function captureScreenshot() {', measurer + 'async function captureScreenshot() {')

# Add screenshotSize parsing in loop
old_loop_capture = """    const screenshot = await captureScreenshot();

    appendResult("Calling agent...\\n");
    const agentResult = await callAgent(command, screenshot, step, memory);"""

new_loop_capture = """    const screenshot = await captureScreenshot();
    let capSize = null;
    try {
      capSize = await measureScreenshot(screenshot);
      console.log("Captured screenshot size:", capSize);
    } catch(e) { }

    appendResult("Calling agent...\\n");
    const agentResult = await callAgent(command, screenshot, step, memory);
    if (agentResult && capSize) {
      agentResult._screenshot_size = capSize;
    }"""

text = text.replace(old_loop_capture, new_loop_capture)

with open('c:/Projects/UI-nav/extension/popup.js', 'w', encoding='utf-8') as f:
    f.write(text)
print('popup.js updated')
