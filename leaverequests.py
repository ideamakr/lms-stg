import asyncio
import httpx
import time

# 🎯 Target Local Instance
API_URL = "http://127.0.0.1:8000"  

async def submit_local_leave(client, user_idx):
    username = f"test_staff_{user_idx}"
    fullname = f"Test Employee {user_idx}"
    
    # 📋 Payload configured to pass your backend Form validations
    form_data = {
        "employee_name": fullname,
        "approver_name": "Sarah Connor",
        "leave_type": "Annual Leave",
        "start_date": "2026-09-01",
        "end_date": "2026-09-02",
        "is_half_day": "false",
        "reason": f"📜 Layout Overflow Verification Row (User {user_idx})"
    }
    
    headers = {
        "x-username": username,
        "current-user-role": "employee",
        "X-Session-ID": f"local-verify-token-{user_idx}",
        "X-Requester-Name": fullname
    }
    
    try:
        start_time = time.time()
        # Submitting payload to the router endpoint
        response = await client.post(
            f"{API_URL}/leaves/", 
            data=form_data, 
            files={"file": (None, b"")}, 
            headers=headers
        )
        duration = time.time() - start_time
        
        if response.status_code in [200, 201]:
            print(f"✅ Row {user_idx} injected into local database in {duration:.2f}s")
            return True
        else:
            print(f"❌ Row {user_idx} failed validation ({response.status_code}): {response.text}")
            return False
    except Exception as e:
        print(f"💥 Network adapter pipeline drop on Row {user_idx}. Details: {e}")
        return False

async def main():
    # Targets the exact wallet boundaries we just seeded (113 - 162)
    start_user = 113
    num_users = 50
    pacing_interval = 0.15 # Stagger spacing window to protect pool headroom
    
    print("========================================================")
    print(f"🚀 Firing Proxy-Bypassing Wave: {num_users} Users to Local Storage")
    print(f"🎯 Target Endpoint: {API_URL}/leaves/")
    print("========================================================")
    
    # 🛡️ trust_env=False explicitly cuts off corporate firewalls/proxies from hijacking local connections
    async with httpx.AsyncClient(trust_env=False, timeout=10.0) as client:
        tasks = []
        for loop_idx, user_idx in enumerate(range(start_user, start_user + num_users)):
            
            async def staggered_launch(u_idx, delay):
                await asyncio.sleep(delay)
                return await submit_local_leave(client, u_idx)
                
            tasks.append(staggered_launch(user_idx, loop_idx * pacing_interval))
            
        await asyncio.gather(*tasks)
        print("\n🏁 Batch injection complete! Check your database browser canvas.")

if __name__ == "__main__":
    asyncio.run(main())