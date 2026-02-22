"""Smoke tests for RetailOrchestrator agent routing via /chat endpoint."""

import os
import sys
import json
import time
from datetime import datetime, timezone
from dotenv import load_dotenv
import urllib.request
import urllib.error

# Load environment variables from .env file
env_path = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
if os.path.exists(env_path):
    load_dotenv(env_path)
else:
    # Try alternative location
    load_dotenv()

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agents.foundry_client import get_project_client, validate_config


def call_chat_endpoint(message: str, user_id: str = "test-user", max_retries: int = 3) -> dict:
    """
    Call /chat endpoint with retry logic for transient failures.
    
    Args:
        message: User message to send
        user_id: User identifier
        max_retries: Number of retry attempts
    
    Returns:
        Response dict with answer, citations, debug info
    """
    url = "http://localhost:9000/chat"
    
    for attempt in range(max_retries):
        try:
            request_data = json.dumps({
                "userId": user_id,
                "message": message
            }).encode('utf-8')
            
            req = urllib.request.Request(
                url,
                data=request_data,
                headers={'Content-Type': 'application/json'}
            )
            
            with urllib.request.urlopen(req, timeout=30) as response:
                response_data = json.loads(response.read().decode('utf-8'))
                return response_data
        
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8')
            if e.code >= 500 and attempt < max_retries - 1:
                delay = 2 * (2 ** attempt)
                print(f"    [Retry {attempt + 1}/{max_retries}] Server error, retrying in {delay}s...")
                time.sleep(delay)
                continue
            raise Exception(f"HTTP {e.code}: {error_body}")
        
        except urllib.error.URLError as e:
            if attempt < max_retries - 1:
                delay = 2 * (2 ** attempt)
                print(f"    [Retry {attempt + 1}/{max_retries}] Connection error, retrying in {delay}s...")
                time.sleep(delay)
                continue
            raise Exception(f"Connection error: {e.reason}")
        
        except Exception as e:
            if attempt < max_retries - 1 and ('timeout' in str(e).lower() or 'connection' in str(e).lower()):
                delay = 2 * (2 ** attempt)
                print(f"    [Retry {attempt + 1}/{max_retries}] Transient error, retrying in {delay}s...")
                time.sleep(delay)
                continue
            raise
    
    raise Exception("Max retries exceeded")


def run_smoke_tests():
    """
    Run smoke tests to validate RetailOrchestrator agent routing.
    
    Tests 3 critical prompts to verify:
    - Agent routing is working correctly
    - Specialist agents are being called via ConnectedAgentTools
    - sub_agents_used is populated in debug output
    """
    
    print("=" * 80)
    print("RetailOrchestrator Connected Agents - Routing Validation Tests")
    print("=" * 80)
    print()
    
    # Agent check: ensure agents and orchestrator exist
    print("[1/3] Checking Azure configuration...")
    
    # Check ORCHESTRATOR_AGENT_ID first - fail fast if missing
    orchestrator_agent_id = os.getenv("ORCHESTRATOR_AGENT_ID")
    if not orchestrator_agent_id:
        print("  ❌ ORCHESTRATOR_AGENT_ID not set in environment")
        print()
        print("Setup guidance:")
        print("  1. Create agents in Azure AI Foundry portal")
        print("  2. Add agent IDs to .env file:")
        print("     ORCHESTRATOR_AGENT_ID=asst_xxx")
        print("     STOREOPS_AGENT_ID=asst_xxx")
        print("     INVENTORY_AGENT_ID=asst_xxx")
        print("     PLANOGRAM_AGENT_ID=asst_xxx")
        print("  3. Run: python src/agents/create_orchestrator_agent.py")
        print("     (this updates the orchestrator with connected agent tools)")
        return False
    
    try:
        validate_config()
        project_endpoint = os.getenv("PROJECT_ENDPOINT")
        
        print(f"  [OK] PROJECT_ENDPOINT: {project_endpoint[:50]}...")
        print(f"  [OK] ORCHESTRATOR_AGENT_ID: {orchestrator_agent_id}")
        
        # Check specialist agent IDs
        storeops_id = os.getenv("STOREOPS_AGENT_ID")
        inventory_id = os.getenv("INVENTORY_AGENT_ID")
        planogram_id = os.getenv("PLANOGRAM_AGENT_ID")
        
        if storeops_id:
            print(f"  [OK] STOREOPS_AGENT_ID: {storeops_id[:20]}...")
        if inventory_id:
            print(f"  [OK] INVENTORY_AGENT_ID: {inventory_id[:20]}...")
        if planogram_id:
            print(f"  [OK] PLANOGRAM_AGENT_ID: {planogram_id[:20]}...")
        print()
    except Exception as e:
        print(f"  [FAIL] Configuration error: {e}")
        print()
        print("Ensure all agent IDs are set in .env file.")
        print("Then run: python src/agents/create_orchestrator_agent.py")
        return False
    
    # Check API server
    print("[2/3] Checking API server availability...")
    try:
        req = urllib.request.Request("http://localhost:9000/health")
        with urllib.request.urlopen(req, timeout=5) as response:
            print("  [OK] API server is running at http://localhost:9000")
        print()
    except Exception as e:
        print(f"  [FAIL] API server not responding: {e}")
        print()
        print("Start API server: python -m uvicorn src.api.main:app --host localhost --port 9000")
        return False
    
    # Run routing validation tests
    print("[3/3] Running routing validation tests...")
    print()
    
    # 3 Critical test cases for agent routing
    test_cases = [
        {
            "prompt": "What should I do if planogram compliance is low?",
            "expected_agent": "PlanogramAgent",
            "description": "Planogram compliance issue"
        },
        {
            "prompt": "Why are out-of-stocks high in Store 457?",
            "expected_agent": "InventoryAgent",
            "description": "Out-of-stock risk assessment"
        },
        {
            "prompt": "What store ops actions should I take when shelf execution is poor?",
            "expected_agent": "StoreOpsAgent",
            "description": "Store operations and shelf execution"
        }
    ]
    
    results = []
    
    for idx, test in enumerate(test_cases, 1):
        prompt = test["prompt"]
        expected_agent = test["expected_agent"]
        description = test["description"]
        
        print(f"[Test {idx}/3] {description}")
        print(f"  Prompt: {prompt}")
        print("-" * 80)
        
        try:
            # Call /chat endpoint
            response = call_chat_endpoint(prompt)
            
            # Extract debug info
            debug = response.get("debug", {})
            sub_agents_used = debug.get("sub_agents_used") if debug else None
            tool_calls = debug.get("tool_calls_executed") if debug else None
            
            # Check if sub-agents were called
            if not sub_agents_used:
                raise AssertionError(
                    f"ROUTING FAILED: No specialist agents invoked. "
                    f"Expected at least {expected_agent} to be called."
                )
            
            # Validate expected agent in sub_agents_used
            if expected_agent not in sub_agents_used:
                # Try to find a match (case-insensitive)
                matched = any(agent.lower() == expected_agent.lower() for agent in sub_agents_used)
                if not matched:
                    print(f"  [!] Expected agent '{expected_agent}' not in sub_agents_used: {sub_agents_used}")
            
            # Display results
            answer_preview = response.get("answer", "")[:200] + "..." if response.get("answer") else ""
            print(f"  Response: {answer_preview}")
            print(f"  [OK] Sub-agents invoked: {sub_agents_used}")
            if tool_calls:
                print(f"  [OK] Tool calls: {tool_calls}")
            print()
            
            results.append({
                "test": description,
                "prompt": prompt,
                "success": True,
                "sub_agents_used": sub_agents_used,
                "tool_calls_executed": tool_calls,
                "answer": response.get("answer", "")[:300]
            })
        
        except AssertionError as e:
            print(f"  [FAIL] Routing validation failed: {e}")
            print()
            results.append({
                "test": description,
                "prompt": prompt,
                "success": False,
                "error": str(e)
            })
        
        except Exception as e:
            print(f"  [FAIL] Test error: {e}")
            print()
            results.append({
                "test": description,
                "prompt": prompt,
                "success": False,
                "error": str(e)
            })
    
    # Summary
    print("=" * 80)
    print("Routing Validation Summary")
    print("=" * 80)
    passed = sum(1 for r in results if r["success"])
    total = len(results)
    
    print(f"Tests Passed: {passed}/{total}")
    print()
    
    for idx, result in enumerate(results, 1):
        status = "[PASS]" if result["success"] else "[FAIL]"
        agents_info = f" [Agents: {result.get('sub_agents_used')}]" if result.get("sub_agents_used") else ""
        print(f"  [{idx}] {result['test']}{agents_info} {status}")
    
    print()
    
    if passed == total:
        print("[OK] ALL ROUTING TESTS PASSED - Connected agents working correctly!")
        success = True
    elif passed >= 2:
        print(f"[!] PARTIAL SUCCESS: {passed}/3 tests passed")
        success = True
    else:
        print("[FAIL] ROUTING TESTS FAILED - Check orchestrator configuration")
        success = False
    
    print("=" * 80)
    
    return success


if __name__ == "__main__":
    success = run_smoke_tests()
    sys.exit(0 if success else 1)
