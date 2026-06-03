import asyncio
import httpx
import time

# 🌐 TARGET INSTANCE
API_URL = "https://leave-system-testenv.onrender.com"

async def submit_simultaneous_leave(client, user_idx):
    username = f"test_staff_{user_idx}"
    fullname = f"Test Employee {user_idx}"
    
    # 📋 Form data payload mapped precisely to your backend POST specs
    form_data = {
        "employee_name": fullname,
        "approver_name": "Sarah Connor",
        "leave_type": "Annual Leave",
        "start_date": "2026-09-01",
        "end_date": "2026-09-02",
        "is_half_day": "false",
        "reason": f"🔥 Concurrency Load Test Stress Wave (User {user_idx})"
    }
    
    # 🛡️ Authenticated security headers matching dashboard mechanics
    headers = {
        "x-username": username,
        "current-user-role": "employee",
        "X-Session-ID": f"load-test-token-id-{user_idx}",
        "X-Requester-Name": fullname
    }
    
    try:
        start_time = time.time()
        # 🚀 MULTIPART FIX: Passing an empty files tuple forces httpx to encode as multipart/form-data, 
        # matching the browser's FormData behavior and preventing 422 backend routing validation errors.
        response = await client.post(
            f"{API_URL}/leaves/", 
            data=form_data, 
            files={"file": (None, b"")}, 
            headers=headers
        )
        duration = time.time() - start_time
        
        if response.status_code in [200, 201]:
            print(f"✅ User {user_idx} written to DB in {duration:.2f}s")
            return True, duration
        else:
            print(f"❌ User {user_idx} rejected ({response.status_code}): {response.text}")
            return False, duration
    except Exception as e:
        print(f"💥 Worker execution crash for User {user_idx}: {e}")
        return False, 0

async def main():
    # Targets a block of 50 users from your newly seeded batch
    start_user = 113
    num_users = 50
    
    print("========================================================")
    print(f"🚀 FIRING CONCURRENCY WAVE: {num_users} Simulators -> {API_URL}")
    print("========================================================")
    
    # Open an async network client pool with a generous timeout for high write load
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Queue up 50 non-blocking tasks concurrently
        tasks = [submit_simultaneous_leave(client, i) for i in range(start_user, start_user + num_users)]
        
        start_total = time.time()
        results = await asyncio.gather(*tasks)  # ⚡ Fires them all at the exact same split-second
        total_duration = time.time() - start_total
        
        # Compile Metrics
        successes = sum(1 for r in results if r[0])
        avg_time = sum(r[1] for r in results) / num_users if num_users > 0 else 0
        
        print("\n📊 ================== REPORT CARD ==================")
        print(f"Total Requests Dispatched : {num_users}")
        print(f"Successful DB Writes      : {successes} / {num_users}")
        print(f"Average Request Latency   : {avg_time:.2f} seconds")
        print(f"Total Wave Execution Time : {total_duration:.2f} seconds")
        print("======================================================")

if __name__ == "__main__":
    asyncio.run(main())