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

print("5. 测试 POST /api/merge_resume ...")
# 需要预先有一个画像，我们先调用 profile 创建一个 mock 或者前面步骤可能已经创建了
database.save_job_profile("FastAPI_Job", {"隐性能力挖掘": ["大客户攻坚"]})
merge_res = client.post("/api/merge_resume", json={
    "job_name": "FastAPI_Job",
    "resume_text": "我在上家公司主要负责海外市场的设备渠道建设，一年内发展了20家代理商。"
})
if merge_res.status_code == 200 and merge_res.json().get("code") == 0:
    print("✅ /api/merge_resume 返回正常")
else:
    print("❌ /api/merge_resume 返回异常")

print("6. 测试 POST /api/start_scan ...")
response = client.post("/api/start_scan", json={"job_name": "FastAPI_Job"})
if response.status_code == 200 and response.json().get("code") == 0:
    print("✅ /api/start_scan 控制状态机正常下发指令")

    # 验证是否能够根据传入的名称加载画像
    import webBossAI
    if webBossAI._current_scan_job_name == "FastAPI_Job":
        print("✅ 后台状态机成功锁定前端选定的职位")
    else:
        print("❌ 后台状态机未能锁定职位")
else:
    print("❌ /api/start_scan 返回异常")

print("测试完成。")