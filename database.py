import sqlite3
import os
import json
from datetime import datetime

DB_NAME = 'app.db'

def get_connection():
    return sqlite3.connect(DB_NAME)

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # 创建 JobProfile 表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS JobProfile (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_name TEXT NOT NULL,
            profile_json TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 创建 ResumeAudit 表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ResumeAudit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            score INTEGER,
            evidence_list TEXT,
            status TEXT,
            raw_data TEXT
        )
    ''')

    # 创建 ManualActionQueue 表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ManualActionQueue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            resume_id INTEGER,
            action_type TEXT NOT NULL, -- 'greet' or 'collect'
            status TEXT DEFAULT 'pending', -- 'pending', 'processing', 'completed', 'failed'
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 创建 OnlineJob 表以缓存线上的招聘职位
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS OnlineJob (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL UNIQUE,
            job_name TEXT NOT NULL,
            status INTEGER,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    conn.commit()
    conn.close()

def save_job_profile(job_name, profile_dict):
    conn = get_connection()
    cursor = conn.cursor()
    profile_json = json.dumps(profile_dict, ensure_ascii=False)

    cursor.execute('''
        INSERT INTO JobProfile (job_name, profile_json, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
    ''', (job_name, profile_json))

    conn.commit()
    conn.close()

def get_latest_job_profile(job_name):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT profile_json FROM JobProfile
        WHERE job_name = ?
        ORDER BY updated_at DESC LIMIT 1
    ''', (job_name,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return json.loads(row[0])
    return None

def save_resume_audit(name, score, evidence_list, status, raw_data):
    conn = get_connection()
    cursor = conn.cursor()

    evidence_json = json.dumps(evidence_list, ensure_ascii=False) if evidence_list else "[]"
    raw_data_json = json.dumps(raw_data, ensure_ascii=False) if raw_data else "{}"

    cursor.execute('''
        INSERT INTO ResumeAudit (name, score, evidence_list, status, raw_data)
        VALUES (?, ?, ?, ?, ?)
    ''', (name, score, evidence_json, status, raw_data_json))

    conn.commit()
    conn.close()

def get_all_resumes():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, name, score, evidence_list, status, raw_data
        FROM ResumeAudit
        ORDER BY id DESC
    ''')
    rows = cursor.fetchall()
    conn.close()

    resumes = []
    for row in rows:
        resumes.append({
            'id': row[0],
            'name': row[1],
            'score': row[2],
            'evidence_list': json.loads(row[3]) if row[3] else [],
            'status': row[4],
            'raw_data': json.loads(row[5]) if row[5] else {}
        })
    return resumes

def add_manual_action(resume_id, action_type):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO ManualActionQueue (resume_id, action_type)
        VALUES (?, ?)
    ''', (resume_id, action_type))
    conn.commit()
    conn.close()

def get_pending_actions():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT m.id, m.resume_id, m.action_type, r.raw_data
        FROM ManualActionQueue m
        JOIN ResumeAudit r ON m.resume_id = r.id
        WHERE m.status = 'pending'
    ''')
    rows = cursor.fetchall()
    conn.close()

    actions = []
    for row in rows:
        actions.append({
            'action_id': row[0],
            'resume_id': row[1],
            'action_type': row[2],
            'raw_data': json.loads(row[3]) if row[3] else {}
        })
    return actions

def mark_action_completed(action_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE ManualActionQueue SET status = 'completed' WHERE id = ?
    ''', (action_id,))
    conn.commit()
    conn.close()

def save_online_jobs(jobs_list):
    """
    保存或更新从 Boss 接口拉取到的线上职位列表。
    jobs_list 结构类似于: [{"encryptJobId": "...", "jobName": "...", "jobOnlineStatus": 1}, ...]
    """
    conn = get_connection()
    cursor = conn.cursor()
    for job in jobs_list:
        jid = job.get("encryptJobId")
        jname = job.get("jobName", "未知职位")
        jstatus = job.get("jobOnlineStatus", 0)
        if not jid:
            continue
        cursor.execute('''
            INSERT INTO OnlineJob (job_id, job_name, status, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(job_id) DO UPDATE SET
                job_name=excluded.job_name,
                status=excluded.status,
                updated_at=CURRENT_TIMESTAMP
        ''', (jid, jname, jstatus))
    conn.commit()
    conn.close()

def get_online_jobs():
    """获取所有线上职位列表，返回 dict 列表"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT job_id, job_name, status FROM OnlineJob ORDER BY updated_at DESC
    ''')
    rows = cursor.fetchall()
    conn.close()

    jobs = []
    for row in rows:
        jobs.append({
            "job_id": row[0],
            "job_name": row[1],
            "status": row[2]
        })
    return jobs

def mark_action_failed(action_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE ManualActionQueue SET status = 'failed' WHERE id = ?
    ''', (action_id,))
    conn.commit()
    conn.close()
