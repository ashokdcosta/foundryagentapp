import json
import urllib.request

message = "What should I do if planogram compliance is low?"
url = "http://localhost:9000/chat"

request_data = json.dumps({
    "userId": "test",
    "message": message
}).encode('utf-8')

req = urllib.request.Request(
    url,
    data=request_data,
    headers={'Content-Type': 'application/json'}
)

try:
    with urllib.request.urlopen(req, timeout=60) as response:
        response_data = json.loads(response.read().decode('utf-8'))
        print(json.dumps(response_data, indent=2))
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
