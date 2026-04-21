import database

print("1. 测试数据库连通性...")
database.init_db()

print("2. 测试保存和读取 JobProfile...")
profile_mock = {
    "测试项": "测试数据",
    "负面教训": ["太远了", "不要没有工作经验的"]
}
database.save_job_profile("测试岗位", profile_mock)

latest = database.get_latest_job_profile("测试岗位")
if latest and latest.get("测试项") == "测试数据":
    print("✅ JobProfile 读写正常")
else:
    print("❌ JobProfile 读写失败")

print("3. 测试保存和读取 OnlineJob...")
mock_jobs = [
    {"encryptJobId": "mock_id_123", "jobName": "测试高级工程师", "jobOnlineStatus": 1},
    {"encryptJobId": "mock_id_456", "jobName": "测试产品经理", "jobOnlineStatus": 0}
]
database.save_online_jobs(mock_jobs)
online_jobs = database.get_online_jobs()
if len(online_jobs) >= 2 and any(j['job_name'] == "测试高级工程师" for j in online_jobs):
    print("✅ OnlineJob 读写正常")
else:
    print("❌ OnlineJob 读写失败")

print("4. 测试保存和读取 ResumeAudit...")
evidence = ["第一份工作的业绩：2023年完成指标150%", "沟通能力强"]
database.save_resume_audit("张三", 95, evidence, "S", {"学历": "本科"})

resumes = database.get_all_resumes()
found = False
for r in resumes:
    if r['name'] == "张三" and r['score'] == 95 and r['status'] == "S":
        found = True
        break

if found:
     print("✅ ResumeAudit 读写正常")
else:
     print("❌ ResumeAudit 读写失败")

print("测试完成。")