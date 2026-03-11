from fastapi import FastAPI
from pydantic import BaseModel
from app.agent import analyze_command

app = FastAPI()

class AgentRequest(BaseModel):
    command: str
    screenshot: str
    step: int

@app.get("/")
def read_root():
    return {"message": "UI Navigator Agent Backend Running"}

@app.post("/agent")
def run_agent(request: AgentRequest):
    try:
        result = analyze_command(request.command, request.screenshot, request.step)
        return result
    except Exception as e:
        return {"error": str(e)}