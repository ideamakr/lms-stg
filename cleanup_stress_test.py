import requests

API_URL = "http://your-api-url"
TOKEN = "your_auth_token"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

def cleanup():
    print("🗑️ Cleaning up dummy records...")
    # This logic assumes your API supports a filter or you handle deletion loop
    # If your API doesn't have a 'delete-by-reason' endpoint, you may need 
    # to manually delete them via your DB management tool or a similar loop.
    # Search for anything with "[DUMMY]" in the reason.
    print("Cleanup logic depends on your specific DELETE API implementation.")

if __name__ == "__main__":
    cleanup()