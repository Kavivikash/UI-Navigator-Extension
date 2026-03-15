import re

with open('c:/Projects/UI-nav/extension/content.js', 'r', encoding='utf-8') as f:
    text = f.read()

# Make computeScaleFactors accept screenshot_size
old_func = """function computeScaleFactors() {
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

  const scale_x = window.innerWidth / img_w;
  const scale_y = window.innerHeight / img_h;

  if (scale_x > 1.5 || scale_y > 1.5) {
     console.warn(`[SCALE WARNING] SCALE_X=${scale_x.toFixed(3)}, SCALE_Y=${scale_y.toFixed(3)}`);
  }

  return { scale_x, scale_y };
}"""

new_func = """function computeScaleFactors(screenshot_size) {
  let scale_x = 1;
  let scale_y = 1;

  if (screenshot_size && screenshot_size.width && screenshot_size.height) {
    scale_x = window.innerWidth / screenshot_size.width;
    scale_y = window.innerHeight / screenshot_size.height;
    console.log(`[SCALE DEBUG] Using dynamic screenshot size to compute scales: Viewport=${window.innerWidth}x${window.innerHeight}, Size=${screenshot_size.width}x${screenshot_size.height} => Scale_x=${scale_x.toFixed(4)}`);
  } else {
    console.warn(`[SCALE WARNING] No screenshot_size provided, falling back to old logic!`);
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

    scale_x = window.innerWidth / img_w;
    scale_y = window.innerHeight / img_h;
  }

  return { scale_x, scale_y };
}"""

text = text.replace(old_func, new_func)

# Change the call site in executeAction
text = text.replace("let scale_hints = computeScaleFactors();", "let scale_hints = computeScaleFactors(payload._screenshot_size);")

with open('c:/Projects/UI-nav/extension/content.js', 'w', encoding='utf-8') as f:
    f.write(text)

print('Updated content.js computeScaleFactors and executeAction')
