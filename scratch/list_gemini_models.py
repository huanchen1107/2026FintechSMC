import httpx
import os

api_key = "AIzaSyDtraUgiv__LAvtPPQh4h5muQeP3eTkSMI"
url = "https://generativelanguage.googleapis.com/v1beta/openai/models"
headers = {"Authorization": f"Bearer {api_key}"}

try:
    response = httpx.get(url, headers=headers)
    response.raise_for_status()
    print(response.json())
except Exception as e:
    print(f"Error: {e}")
    if hasattr(e, 'response'):
        print(f"Response: {e.response.text}")
