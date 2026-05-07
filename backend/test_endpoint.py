import requests
import json

# Test the booking history endpoint
headers = {
    'X-User-Id': '2',
    'X-User-Role': 'customer'
}

response = requests.get('http://127.0.0.1:5000/booking-history/10', headers=headers)
print(f"Status Code: {response.status_code}")
print(f"Response: {json.dumps(response.json(), indent=2, default=str)}")
