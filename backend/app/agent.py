def analyze_command(command, screenshot, step=1):
    cmd = command.lower()

    if "search" in cmd:
        if step == 1:
            next_action = {
                "type": "click",
                "x": 500,
                "y": 120
            }
        elif step == 2:
            next_action = {
                "type": "type",
                "x": 500,
                "y": 120,
                "text": "OpenAI"
            }
        else:
            next_action = {
                "type": "scroll",
                "direction": "down",
                "amount": 400
            }
    else:
        if step == 1:
            next_action = {
                "type": "click",
                "x": 500,
                "y": 300
            }
        else:
            next_action = {
                "type": "scroll",
                "direction": "down",
                "amount": 400
            }

    done = step >= 3

    return {
        "goal": command,
        "status": "completed" if done else "in_progress",
        "step": step,
        "screen_summary": f"Mock screen received. Screenshot length: {len(screenshot)}",
        "next_action": next_action,
        "needs_confirmation": False,
        "reason": f"Mock agent step {step}"
    }