import asyncio
import httpx
import time
import random

# 🌐 TARGET INSTANCE
API_URL = "https://leave-system-testenv.onrender.com"

# 📅 TEST WAVE CONFIGURATION
BASE_MONTH = "07" 

async def submit_simultaneous_leave(client, user_idx):
    # 🎲 Paces out entries to keep your Render connection pool safe
    stagger_delay = random.uniform(10.0, 60.0)
    await asyncio.sleep(stagger_delay)

    username = f"test_staff_{user_idx}"
    fullname = f"Test Employee {user_idx}"
    
    form_data = {
        "employee_name": fullname,
        "approver_name": "Muted Test Approver",  
        "leave_type": "Annual Leave",
        "start_date": f"2026-{BASE_MONTH}-01",
        "end_date": f"2026-{BASE_MONTH}-02",
        "is_half_day": "false",
        "reason": f"🔥 Production Concurrency Stress Wave (User {user_idx})"
    }
    
    headers = {
        "x-username": username,
        "current-user-role": "employee",
        "X-Session-ID": f"load-test-token-id-{user_idx}",
        "X-Requester-Name": fullname
    }
    
    try:
        start_time = time.time()
        
        response = await client.post(
            f"{API_URL}/leaves/", 
            data=form_data, 
            files={"file": (None, b"")}, 
            headers=headers
        )
        duration = time.time() - start_time
        
        if response.status_code in [200, 201]:
            print(f"✅ User {user_idx} written to DB in {duration:.2f}s (after delaying {stagger_delay:.2f}s)")
            return True, duration
        else:
            print(f"❌ User {user_idx} rejected ({response.status_code}): {response.text}")
            return False, duration
    except Exception as e:
        print(f"💥 Worker execution crash for User {user_idx}: {e}")
        return False, 0

async def main():
    start_user = 113
    num_users = 50
    
    print("========================================================")
    print(f"🚀 FIRING CONCURRENCY WAVE: {num_users} Simulators -> {API_URL}")
    print(f"📅 Target Testing Date Window: 2026-{BASE_MONTH}-01 to 2026-{BASE_MONTH}-02")
    print(f"🎲 Jitter Interval Enabled: 0.6s - 16.0s Random Delay Stagger")
    print("🤫 Email Notification Mode  : MUTED (Using non-existent Approver)")
    print("========================================================")
    
    # ⏱️ FIXED: Raised client-side connection timeout from 30.0 to 90.0 seconds
    async with httpx.AsyncClient(timeout=90.0) as client:
        tasks = [submit_simultaneous_leave(client, i) for i in range(start_user, start_user + num_users)]
        
        start_total = time.time()
        results = await asyncio.gather(*tasks)  
        total_duration = time.time() - start_total
        
        successes = sum(1 for r in results if r[0])
        valid_latencies = [r[1] for r in results if r[1] > 0]
        
        avg_time = sum(valid_latencies) / len(valid_latencies) if valid_latencies else 0
        fastest_time = min(valid_latencies) if valid_latencies else 0
        slowest_time = max(valid_latencies) if valid_latencies else 0
        
        print("\n📊 ================== PERFORMANCE REPORT CARD ==================")
        print(f"Total Requests Dispatched   : {num_users}")
        print(f"Successful DB Writes        : {successes} / {num_users}")
        print("----------------------------------------------------------------")
        print(f"🚀 Fastest Server Response  : {fastest_time:.2f} seconds")
        print(f"🐌 Slowest Server Response  : {slowest_time:.2f} seconds")
        print(f"📈 Average Server Latency   : {avg_time:.2f} seconds")
        print("----------------------------------------------------------------")
        print(f"🏁 Total Script Wall-Time   : {total_duration:.2f} seconds")
        print("==================================================================")

if __name__ == "__main__":
    asyncio.run(main())