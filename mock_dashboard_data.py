import requests
import datetime
import time

# 1. Paste the full token string here
TOKEN = "eyJhbGciOiJIUzI1NiIsInR5..." 

# 2. API endpoint (make sure this matches your local server)
API_URL = "http://127.0.0.1:8000"

# 3. Correct Headers Format
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

def seed_stress_test():
    today = datetime.date.today().isoformat()
    print("🚀 Starting Stress Test Seeding...")

    for i in range(1, 21):
        # Data for AWAY TODAY (Approved)
        away_data = {
            "employee_name": f"Away User {i}",
            "leave_type": "Annual Leave",
            "start_date": today,
            "end_date": today,
            "reason": "[DUMMY] Stress Test",
            "status": "Approved"
        }
        # Try /leaves/apply. If you get a 404, check if you need /api/leaves/apply
        requests.post(f"{API_URL}/leaves/apply", json=away_data, headers=HEADERS)
        
        print(f"✅ Progress: Batch {i}/20 sent...")
        time.sleep(0.1)

    print("\n🎉 Seeding Complete! Refresh your dashboard.")

if __name__ == "__main__":
    seed_stress_test()