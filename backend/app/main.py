from dotenv import load_dotenv
load_dotenv()

from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from app.agent import analyze_command

app = FastAPI(title="UI Navigator Agent Backend")


class ActionHistoryItem(BaseModel):
    step: int
    action: Optional[Dict[str, Any]] = None
    screen_summary: Optional[str] = None
    result_summary: Optional[str] = None


class AgentMemory(BaseModel):
    history: List[ActionHistoryItem] = Field(default_factory=list)


class AgentRequest(BaseModel):
    command: str
    screenshot: str
    step: int
    memory: Optional[AgentMemory] = None


@app.get("/")
def read_root():
    return {
        "message": "UI Navigator Agent Backend Running",
        "vertex_project_configured": True,
    }


@app.post("/agent")
def run_agent(request: AgentRequest):
    try:
        result = analyze_command(
            command=request.command,
            screenshot=request.screenshot,
            step=request.step,
            memory=request.memory.model_dump() if request.memory else None,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))