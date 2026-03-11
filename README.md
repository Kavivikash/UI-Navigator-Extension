# UI-nav

AI-powered browser extension that navigates and interacts with web UIs based on natural-language instructions.

## Structure

```
UI-nav/
├── extension/          # Chrome extension (Manifest V3)
│   ├── manifest.json
│   ├── popup.html / popup.js / styles.css
│   ├── background.js   # Service worker — calls backend & executes actions
│   ├── content.js      # Page-level action executor
│   └── icons/
│
└── backend/            # FastAPI + OpenAI agent
    ├── app/
    │   ├── main.py             # API entry point
    │   ├── agent.py            # Core agent loop
    │   ├── tools/
    │   │   ├── screenshot_analyzer.py   # Vision model integration
    │   │   ├── action_formatter.py      # Instruction → actions via LLM
    │   │   └── safety_checker.py        # Block dangerous instructions
    │   └── schemas/
    │       └── action_schema.py         # Pydantic action models
    ├── requirements.txt
    └── .env
```

## Setup

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
# Edit .env and set OPENAI_API_KEY
uvicorn app.main:app --reload
```

### Extension

1. Open Chrome → `chrome://extensions`
2. Enable **Developer mode**
3. Click **Load unpacked** → select the `extension/` folder
4. Click the UI-nav icon to open the popup

## Usage

Type a natural-language instruction in the popup (e.g. _"Click the Sign In button"_) and press **Run**. The agent will analyze the current page screenshot and execute the appropriate actions.