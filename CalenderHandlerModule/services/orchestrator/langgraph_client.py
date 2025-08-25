# echoagents/services/orchestrator/langgraph_client.py

class LangGraphClient:
    def call_llm(self, prompt: str):
        # For testing, return a fixed response to call tools
        return {
            "write_timeline": {
                "event": "Meeting scheduled",
                "time": "2025-08-15 10:00"
            },
            "send_message": {
                "recipient": "alice@example.com",
                "message": "Meeting confirmed for Aug 15 10:00"
            }
        }

    def save_state(self, state: dict):
        print("State saved:", state)
