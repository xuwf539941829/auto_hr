from fastapi.testclient import TestClient
from webBossAI import app
import database

# Use TestClient to test the FastAPI app endpoints
client = TestClient(app)

print("1. 测试数据库连通性...")
database.init_db()

print("2. 测试 GET /api/jobs ...")
# 预置假数据
database.save_online_jobs([{"encryptJobId": "test_1", "jobName": "FastAPI_Job", "jobOnlineStatus": 1}])
response = client.get("/api/jobs")
if response.status_code == 200 and any(j["job_name"] == "FastAPI_Job" for j in response.json().get("data", [])):
    print("✅ /api/jobs 返回正常")
else:
    print("❌ /api/jobs 返回异常")

print("3. 测试 GET /api/resumes ...")
evidence = ["第一份工作的业绩：2023年完成指标150%", "沟通能力强"]
database.save_resume_audit("FastAPI_Candidate", 95, evidence, "S", {"学历": "本科"})
response = client.get("/api/resumes")
if response.status_code == 200 and any(r["name"] == "FastAPI_Candidate" for r in response.json().get("data", [])):
     print("✅ /api/resumes 返回正常")
else:
     print("❌ /api/resumes 返回异常")

print("4. 测试 POST /api/action ...")
# 先获取刚才插入的简历 ID
resumes = database.get_all_resumes()
test_id = next(r["id"] for r in resumes if r["name"] == "FastAPI_Candidate")
response = client.post("/api/action", json={"resume_id": test_id, "action_type": "greet"})
if response.status_code == 200 and response.json().get("code") == 0:
    # 验证是否存入了 ManualActionQueue
    pending = database.get_pending_actions()
    if any(a["resume_id"] == test_id and a["action_type"] == "greet" for a in pending):
        print("✅ /api/action 处理与队列下发正常")
    else:
        print("❌ /api/action 写入队列失败")
else:
    print("❌ /api/action 返回异常")

print("测试完成。")