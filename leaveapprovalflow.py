import asyncio
import httpx
import time
import random

# 🌐 TARGET INSTANCE
API_URL = "https://leave-system-testenv.onrender.com"

# 📅 TEST WAVE CONFIGURATION
BASE_MONTH = "08" 

async def submit_and_approve_workflow(client, user_idx):
    # ⏱️ STAGE 1: Initial Submission Delay (Human Arrival Pace)
    stagger_delay = random.uniform(10.0, 60.0)
    await asyncio.sleep(stagger_delay)

    username = f"test_staff_{user_idx}"
    fullname = f"Test Employee {user_idx}"
    
    # 📋 Payload configuration
    form_data = {
        "employee_name": fullname,
        "approver_name": "Muted Test Approver 1",  
        "leave_type": "Annual Leave",
        "start_date": f"2026-{BASE_MONTH}-04", # 🗓️ Tuesday
        "end_date": f"2026-{BASE_MONTH}-05",   # 🗓️ Wednesday
        "is_half_day": "false",
        "reason": f"🔥 Multi-Stage Concurrency Wave (User {user_idx})"
    }
    
    headers = {
        "x-username": username,
        "current-user-role": "employee",
        "X-Session-ID": f"load-test-token-id-{user_idx}",
        "X-Requester-Name": fullname
    }
    
    try:
        start_time = time.time()
        
        # 🚀 SUBMIT REQUEST
        response = await client.post(
            f"{API_URL}/leaves/", 
            data=form_data, 
            files={"file": (None, b"")}, 
            headers=headers
        )
        
        if response.status_code not in [200, 201]:
            print(f"❌ User {user_idx} Submission Rejected ({response.status_code}): {response.text}")
            return False, 0
            
        # 🛠️ SMART ID EXTRACTION STRATEGY
        leave_data = response.json()
        
        # Looks for 'id', 'leave_id', or nested 'id' properties depending on Pydantic schemas
        leave_id = (
            leave_data.get("id") or 
            leave_data.get("leave_id") or 
            leave_data.get("data", {}).get("id") if isinstance(leave_data.get("data"), dict) else None
        )
        
        if not leave_id:
            print(f"⚠️ User {user_idx} written to DB but could not parse ID. Raw JSON footprint: {leave_data}")
            return False, 0
            
        print(f"✅ User {user_idx} written to DB (Leave ID: {leave_id})")

        # ⏱️ STAGE 2: Approver 1 Delay (Breathing room for database locks)
        await asyncio.sleep(random.uniform(5.0, 10.0))
        
        # 👍 APPROVAL LEVEL 1
        app_1_headers = {
            "x-username": "muted_approver_1",
            "current-user-role": "manager",
            "X-Requester-Name": "Muted Test Approver 1"
        }
        
        # 👑 Explicitly naming 'Muted Test Approver 2' prevents the backend from defaulting to Tony
        app_1_payload = {
            "status": "approved",
            "next_approver": "Muted Test Approver 2"
        }
        
        response_app1 = await client.put(
            f"{API_URL}/leaves/{leave_id}/approve", 
            json=app_1_payload, 
            headers=app_1_headers
        )
        
        if response_app1.status_code not in [200, 202]:
            print(f"⚠️ Leave ID {leave_id} failed Level 1 Approval ({response_app1.status_code}): {response_app1.text}")
            return False, 0
        print(f"👍 Leave ID {leave_id} passed Level 1 Approval.")

        # ⏱️ STAGE 3: Approver 2 Delay (Breathing room to avoid race conditions)
        await asyncio.sleep(random.uniform(5.0, 10.0))
        
        # 👑 APPROVAL LEVEL 2 (Finalized)
        app_2_headers = {
            "x-username": "muted_approver_2",
            "current-user-role": "manager",
            "X-Requester-Name": "Muted Test Approver 2"
        }
        app_2_payload = {
            "status": "approved",
            "next_approver": None  
        }
        
        response_app2 = await client.put(
            f"{API_URL}/leaves/{leave_id}/approve", 
            json=app_2_payload, 
            headers=app_2_headers
        )
        
        duration = time.time() - start_time
        if response_app2.status_code in [200, 202]:
            print(f"👑 Leave ID {leave_id} fully Approved by Level 2!")
            return True, duration
        else:
            print(f"⚠️ Leave ID {leave_id} failed Level 2 Final Approval ({response_app2.status_code}): {response_app2.text}")
            return False, 0

    except Exception as e:
        print(f"💥 Worker execution crash for User {user_idx}: {e}")
        return False, 0

async def main():
    start_user = 200  
    num_users = 10   
    
    print("========================================================")
    print(f"🚀 FIRING MULTI-STAGE CONCURRENCY WAVE: {num_users} Simulators")
    print(f"📅 Target Testing Date Window: 2026-{BASE_MONTH}-04 to 2026-{BASE_MONTH}-05") 
    print(f"🎲 Step 1 Window: 10s - 60s | Step 2 & 3 Window: 5s - 10s")
    print("🤫 Email Notification Mode  : MUTED (Using non-existent Chains)")
    print("========================================================")
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        tasks = [submit_and_approve_workflow(client, i) for i in range(start_user, start_user + num_users)]
        
        start_total = time.time()
        results = await asyncio.gather(*tasks)  
        total_duration = time.time() - start_total
        
        successes = sum(1 for r in results if r[0])
        valid_latencies = [r[1] for r in results if r[1] > 0]
        
        avg_time = sum(valid_latencies) / len(valid_latencies) if valid_latencies else 0
        fastest_time = min(valid_latencies) if valid_latencies else 0
        slowest_time = max(valid_latencies) if valid_latencies else 0
        
        print("\n📊 ================== PERFORMANCE REPORT CARD ==================")
        print(f"Total Pipelines Fully Dispatched   : {num_users}")
        print(f"Successful Full Cycle Completions : {successes} / {num_users}")
        print("----------------------------------------------------------------")
        print(f"🚀 Fastest Pipeline Lifecycle     : {fastest_time:.2f} seconds")
        print(f"🐌 Slowest Pipeline Lifecycle     : {slowest_time:.2f} seconds")
        print(f"📈 Average Pipeline Lifecycle     : {avg_time:.2f} seconds")
        print("----------------------------------------------------------------")
        print(f"🏁 Total Script Wall-Time          : {total_duration:.2f} seconds")
        print("==================================================================")

if __name__ == "__main__":
    asyncio.run(main())