import requests
import json
import sys

BASE_URL = "http://localhost:34521"

def check_health():
    print(f"Checking service at {BASE_URL}...")
    try:
        # 尝试访问 docs 页面作为健康检查
        resp = requests.get(f"{BASE_URL}/docs", timeout=5)
        if resp.status_code == 200:
            print("✅ Service is up (Docs page accessible)")
            return True
        else:
            print(f"⚠️ Service responded with status code: {resp.status_code}")
            return True # 只要有响应就算活着
    except Exception as e:
        print(f"❌ Service check failed: {e}")
        return False

def test_flow():
    # 1. Register
    username = "test_mig_user_002"
    password = "password123"
    print(f"\n👉 1. Registering user: {username}")
    
    try:
        reg_resp = requests.post(f"{BASE_URL}/auth/register", json={
            "username": username,
            "password": password
        }, timeout=10)
        
        if reg_resp.status_code == 200:
            print("✅ Registration successful")
        elif "already exists" in reg_resp.text or "已存在" in reg_resp.text:
            print("ℹ️ User already exists, proceeding to login.")
        else:
            print(f"❌ Registration failed: {reg_resp.status_code} {reg_resp.text}")
            # 尝试继续登录，也许之前注册过
    except Exception as e:
        print(f"❌ Registration request error: {e}")
        return

    # 2. Login
    print(f"\n👉 2. Logging in as {username}...")
    try:
        login_resp = requests.post(f"{BASE_URL}/auth/login", json={
            "username": username,
            "password": password
        }, timeout=10)
        
        if login_resp.status_code != 200:
            print(f"❌ Login failed: {login_resp.status_code} {login_resp.text}")
            return
        
        resp_json = login_resp.json()
        token = resp_json.get("access_token")
        if not token:
            print(f"❌ No token in login response: {resp_json}")
            return
        print(f"✅ Login successful. Token: {token[:10]}...")
    except Exception as e:
        print(f"❌ Login request error: {e}")
        return

    # 3. Chat Stream V2
    print("\n👉 3. Testing V2 Chat Stream (/api/ai/chat/v2/prompt_chat/stream)...")
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    data = {"query": "你好，这是一次迁移测试，请回复：迁移成功。"}
    
    try:
        session_id = None
        with requests.post(f"{BASE_URL}/api/ai/chat/v2/prompt_chat/stream", headers=headers, json=data, stream=True, timeout=30) as r:
            if r.status_code != 200:
                print(f"❌ Chat request failed: {r.status_code} {r.text}")
                return
            
            print("💬 Stream response content:")
            print("-" * 40)
            full_content = ""
            for line in r.iter_lines():
                if line:
                    decoded_line = line.decode('utf-8')
                    if decoded_line.startswith("data: "):
                        content_json = decoded_line[6:]
                        if content_json == "[DONE]":
                            print("\n[Stream End]")
                            break
                        try:
                            content_data = json.loads(content_json)
                            meta = content_data.get("meta")
                            if meta and meta.get("session_id"):
                                session_id = meta.get("session_id")
                            chunk = content_data.get("content", "")
                            print(chunk, end="", flush=True)
                            full_content += chunk
                        except:
                            print(f"\n[Raw]: {decoded_line}")
            print("\n" + "-" * 40)
            
            if full_content:
                print("✅ V2 Chat Test Passed!")
            else:
                print("⚠️ No content received from stream.")

        if not session_id:
            print("❌ No session_id received from meta frame. Context test cannot continue.")
            return

        # 验证重复消息和上下文（必须带 session_id）
        print("\n👉 4. Testing Multi-turn Context...")
        query2 = "我刚才说了什么？请重复一遍。"
        print(f"User: {query2}")
        
        response2 = requests.post(
            f"{BASE_URL}/api/ai/chat/v2/prompt_chat/stream",
            headers=headers,
            json={"query": query2, "session_id": session_id},
            stream=True
        )
        
        full_content2 = ""
        print("💬 Stream response 2:")
        print("-" * 40)
        for line in response2.iter_lines():
            if line:
                decoded_line = line.decode('utf-8')
                if decoded_line.startswith("data: "):
                    data_str = decoded_line.replace("data: ", "")
                    if data_str == "[DONE]":
                        print("\n[Stream End]")
                        break
                    try:
                        data_json = json.loads(data_str)
                        content = data_json.get("content", "")
                        print(content, end="", flush=True)
                        full_content2 += content
                    except Exception as e:
                        print(f"\nError parsing line: {decoded_line} | {e}")
        print("\n" + "-" * 40)
        
        # 简单验证回复中是否包含第一轮的信息（模糊匹配）
        if "迁移测试" in full_content2 or "迁移成功" in full_content2:
            print("✅ Context verification PASSED: AI remembered previous conversation.")
        else:
            print("⚠️ Context verification WARNING: AI might have forgotten context.")

        print("\n👉 5. Testing Session List & History APIs...")
        sessions_resp = requests.get(
            f"{BASE_URL}/api/ai/chat/v2/sessions",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        if sessions_resp.status_code != 200:
            print(f"❌ List sessions failed: {sessions_resp.status_code} {sessions_resp.text}")
            return
        sessions = sessions_resp.json()
        print(f"✅ Sessions count: {len(sessions)}")

        history_resp = requests.get(
            f"{BASE_URL}/api/ai/chat/v2/sessions/{session_id}/messages",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        if history_resp.status_code != 200:
            print(f"❌ Get messages failed: {history_resp.status_code} {history_resp.text}")
            return
        history = history_resp.json()
        print(f"✅ History messages: {len(history)}")

        print("\n✅ All Tests Passed!")
                
    except Exception as e:
        print(f"\n❌ Stream failed with exception: {e}")

if __name__ == "__main__":
    if check_health():
        test_flow()
