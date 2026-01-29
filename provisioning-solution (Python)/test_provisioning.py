"""
Test script for Azure Provisioning Functions
Run this to test the complete provisioning workflow
"""

import requests
import json
import time

# Configuration
FUNCTION_APP_URL = "http://localhost:7071"  # Change for deployed function
INGEST_ENDPOINT = f"{FUNCTION_APP_URL}/api/provisioning/ingest"

def test_provisioning_flow():
    """Test the complete provisioning workflow"""
    
    print("=" * 60)
    print("Azure Provisioning Function Test")
    print("=" * 60)
    
    # Test payload
    test_user = {
        "email": "testuser@example.com",
        "name": "Test User",
        "firstName": "Test",
        "lastName": "User",
        "purchaseId": f"TEST-{int(time.time())}",
        "productSku": "PREMIUM-MEMBERSHIP",
        "organization": "Test Organization",
        "callbackUrl": "https://webhook.site/unique-id"  # Replace with your test URL
    }
    
    print("\n1. Testing Ingest Function")
    print("-" * 60)
    print(f"Sending request to: {INGEST_ENDPOINT}")
    print(f"Payload: {json.dumps(test_user, indent=2)}")
    
    try:
        # Send request to ingest function
        response = requests.post(
            INGEST_ENDPOINT,
            json=test_user,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        
        print(f"\nResponse Status: {response.status_code}")
        print(f"Response Body: {json.dumps(response.json(), indent=2)}")
        
        if response.status_code == 202:
            print("\n✅ Ingest function accepted the request")
            provisioning_id = response.json().get('provisioningId')
            print(f"Provisioning ID: {provisioning_id}")
            
            print("\n2. Worker Function Processing")
            print("-" * 60)
            print("Worker function is now processing the request...")
            print("This will:")
            print("  - Send Entra ID guest invite")
            print("  - Create Teams site with private channel")
            print("  - Create SharePoint site and list")
            print("  - Send callback to WordPress")
            
            print("\n3. Check Results")
            print("-" * 60)
            print(f"Monitor the callback URL: {test_user['callbackUrl']}")
            print("Check Azure Portal logs for detailed execution")
            print("Check blob storage: provisioning-logs/{provisioning_id}.json")
            
        else:
            print(f"\n❌ Ingest function failed")
            
    except requests.exceptions.RequestException as e:
        print(f"\n❌ Error: {str(e)}")
        print("\nTroubleshooting:")
        print("- Ensure functions are running (func start)")
        print("- Check if the endpoint URL is correct")
        print("- Verify network connectivity")

def test_validation():
    """Test input validation"""
    
    print("\n\n" + "=" * 60)
    print("Testing Input Validation")
    print("=" * 60)
    
    # Test cases
    test_cases = [
        {
            "name": "Missing email",
            "payload": {"name": "Test User"},
            "expected": 400
        },
        {
            "name": "Invalid email format",
            "payload": {"email": "invalid-email", "name": "Test User"},
            "expected": 400
        },
        {
            "name": "Missing name",
            "payload": {"email": "test@example.com"},
            "expected": 400
        }
    ]
    
    for test in test_cases:
        print(f"\nTest: {test['name']}")
        print(f"Payload: {json.dumps(test['payload'], indent=2)}")
        
        try:
            response = requests.post(
                INGEST_ENDPOINT,
                json=test['payload'],
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            
            if response.status_code == test['expected']:
                print(f"✅ Validation passed (expected {test['expected']})")
            else:
                print(f"❌ Unexpected status: {response.status_code}")
                
        except requests.exceptions.RequestException as e:
            print(f"❌ Error: {str(e)}")

if __name__ == "__main__":
    print("\nAzure Provisioning Function Test Suite\n")
    
    # Run tests
    test_provisioning_flow()
    test_validation()
    
    print("\n\n" + "=" * 60)
    print("Test Complete")
    print("=" * 60)
    print("\nNext Steps:")
    print("1. Check Azure Portal for function execution logs")
    print("2. Verify callback was received at webhook URL")
    print("3. Check blob storage for provisioning results")
    print("4. Verify resources in Microsoft 365 admin center")
