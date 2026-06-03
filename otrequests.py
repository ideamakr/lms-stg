import asyncio
import httpx
import time

# 🎯 Target Local Instance
API_URL = "http://127.0.0.1:8000"  

async def submit_local_ot(client, user_idx):
    username = f"test_staff_{user_idx}"
    fullname = f"Test Employee {user_idx}"
    
    # 📋 Form payload completely aligned with app/routers/overtime.py requirements
    form_data = {
        "employee_name": fullname,
        "approver_name": "Sarah Connor",
        "ot_type": "Regular",          # 🔗 Matches UI category configuration rules
        "ot_date": "2026-06-01",
        "ot_unit": "hours",            # 🚨 FIXED: Now explicitly provided to pass Form(...) requirements
        "start_time": "18:00",         # 🚨 FIXED: Required for backend internal math parsing
        "end_time": "22:00",           # 🚨 FIXED: Generates a clean diff window of 4.0 hours
        "reason": f"⏱️ OT Layout Overflow Verification Row (User {user_idx})"
    }
    
    headers = {
        "x-username": username,
        "current-user-role": "employee",
        "X-Session-ID": f"local-ot-token-{user_idx}",
        "X-Requester-Name": fullname
    }
    
    try:
        start_time_track = time.time()
        # 🎯 TARGET ROUTE ROUTED PERFECTLY TO /overtime/apply
        response = await client.post(
            f"{API_URL}/overtime/apply", 
            data=form_data, 
            headers=headers
        )
        duration = time.time() - start_time_track
        
        if response.status_code in [200, 201]:
            print(f"✅ OT Row {user_idx} injected into local database in {duration:.2f}s")
            return True
        else:
            print(f"❌ OT Row {user_idx} failed validation ({response.status_code}): {response.text}")
            return False
    except Exception as e:
        print(f"💥 Network adapter pipeline drop on OT Row {user_idx}. Details: {e}")
        return False

async def main():
    # Targets your local user profile block safely
    start_user = 113
    num_users = 50
    pacing_interval = 0.15 
    
    print("========================================================")
    print(f"🚀 Firing Proxy-Bypassing Wave: {num_users} OT Claims to Local Storage")
    print(f"🎯 Target Endpoint: {API_URL}/overtime/apply")
    print("========================================================")
    
    # trust_env=False cuts corporate proxies cleanly out of local system calls
    async with httpx.AsyncClient(trust_env=False, timeout=10.0) as client:
        tasks = []
        for loop_idx, user_idx in enumerate(range(start_user, start_user + num_users)):
            
            async def staggered_launch(u_idx, delay):
                await asyncio.sleep(delay)
                return await submit_local_ot(client, u_idx)
                
            tasks.append(staggered_launch(user_idx, loop_idx * pacing_interval))
            
        await asyncio.gather(*tasks)
        print("\n🏁 OT Batch injection complete! Check your Overtime Claims Queue dashboard link.")

if __name__ == "__main__":
    asyncio.run(main())