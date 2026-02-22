from azure.ai.agents.models import ConnectedAgentTool
import json

t = ConnectedAgentTool('id123', 'TestAgent', 'Test')
print("Dict representation:")
print(t.__dict__)
print("\nConverting to dict with type:")
tool_dict = {
    "type": "connected_agent",
    **t.__dict__
}
print(json.dumps(tool_dict, indent=2))
