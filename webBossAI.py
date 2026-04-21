# -*- coding: utf-8 -*-
"""
BOSS直聘招聘助手 - API 驱动版 v2.1 (无限循环版)
核心逻辑：通过 Playwright 连接 Chrome，在浏览器上下文执行 fetch 请求 WAPI 接口。
功能：支持推荐/最新列表切换、自动翻页（1-50页循环）、AI 深度筛选、自动解析详情、自动收藏及打招呼。
"""

import json
import os
import sys
import argparse
import time
import re
import requests
import random  # 引入随机模块
import threading

# Windows 控制台按键监听（无需额外依赖）
try:
    import msvcrt  # type: ignore
except ImportError:
    msvcrt = None

try:
    import ctypes
except ImportError:
    ctypes = None

# 尝试导入 playwright
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("[错误] 未安装 Playwright，请运行: pip install playwright")
    sys.exit(1)

# API 配置 (智谱AI)
ZHIPU_API_KEY = "c1755aea8b864c31b5979c024e16aa85.rifwbYsklSUElGeD"
ZHIPU_API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

# 全局公司行业缓存
_company_industry_cache = {}

class RuntimeControl:
    """运行时控制：暂停/继续 + 统计展示（Windows 控制台友好）"""
    def __init__(self):
        self._paused = threading.Event()
        self._lock = threading.Lock()
        self.viewed = 0
        self.collected = 0
        self.skipped = 0
        self.filtered = 0

    def pause(self):
        self._paused.set()

    def resume(self):
        self._paused.clear()

    def is_paused(self) -> bool:
        return self._paused.is_set()

    def wait_if_paused(self):
        # 被暂停时，阻塞等待直到恢复
        while self._paused.is_set():
            time.sleep(0.1)

    def _set_console_title(self, text: str):
        if os.name == "nt" and ctypes is not None:
            try:
                ctypes.windll.kernel32.SetConsoleTitleW(text)
            except Exception:
                pass

    def show_stats(self):
        with self._lock:
            text = f"【查看 {self.viewed} | 已收藏 {self.collected} | 跳过 {self.skipped} | 列表过滤 {self.filtered}】"
        # 单独打印一行，避免与原有日志输出互相覆盖
        print(text)
        self._set_console_title(text)

def start_key_listener(ctrl: RuntimeControl):
    """后台监听键盘：P 暂停，S 继续（需要控制台窗口焦点）"""
    if msvcrt is None:
        print("[提示] 当前环境不支持 msvcrt，无法启用键盘暂停/继续。")
        return

    def _worker():
        while True:
            try:
                if msvcrt.kbhit():
                    ch = msvcrt.getch()
                    # 兼容字母大小写
                    if ch in (b"p", b"P"):
                        if not ctrl.is_paused():
                            ctrl.pause()
                            print("\n[已暂停] 按 S 继续运行。")
                        else:
                            print("\n[已暂停] 按 S 继续运行。")
                    elif ch in (b"s", b"S"):
                        if ctrl.is_paused():
                            ctrl.resume()
                            print("\n[已继续] 程序继续运行。")
                time.sleep(0.05)
            except Exception:
                # 避免监听线程导致主程序崩溃
                time.sleep(0.2)

    t = threading.Thread(target=_worker, daemon=True)
    t.start()

def sleep_interruptible(ctrl: RuntimeControl, seconds: float, step: float = 0.2):
    """可被暂停打断的 sleep（暂停期间不计时）"""
    end_at = time.time() + max(0.0, seconds)
    while True:
        ctrl.wait_if_paused()
        now = time.time()
        if now >= end_at:
            return
        time.sleep(min(step, end_at - now))

def clean_json(data):
    """递归删除 JSON 中的空值属性（None, "", [], {}）以减少内容"""
    if isinstance(data, dict):
        return {
            k: clean_json(v)
            for k, v in data.items()
            if v not in (None, "", [], {}) and clean_json(v) not in (None, "", [], {})
        }
    elif isinstance(data, list):
        return [
            clean_json(i)
            for i in data
            if i not in (None, "", [], {}) and clean_json(i) not in (None, "", [], {})
        ]
    return data

# --- 核心 AI 过滤函数 ---

def parse_age(age_text):
    m = re.search(r"\d+", str(age_text or ""))
    return int(m.group()) if m else None


def parse_work_year(work_text):
    """
    解析工作年限：统一将“不限/应届”等识别为 0.0，
    如果完全没有数字且不是不限，才返回 None。
    """
    text = str(work_text or "").strip()
    if not text:
        return None

    # 1. 统一全角数字
    text = text.translate(str.maketrans("０１２３４５６７８９", "0123456789"))

    # 2. 识别“不限”或“无经验”场景 -> 统一给 0.0，表示没有门槛
    if re.search(r"(不限|无经验|应届|在校|实习|学生|经验不限)", text):
        return 0.0

    # 3. 提取数字（解决“10年以上”、“3-5年”、“3年+”等）
    m = re.search(r"(\d+(?:\.\d+)?)", text)
    if m:
        return float(m.group(1))

    # 4. 中文数字转换（十年、五年等）
    cn_to_num = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
    cm = re.search(r"([零一二两三四五六七八九十]+)", text)
    if cm:
        cn = cm.group(1)
        if cn == "十": return 10.0
        if "十" in cn:
            parts = cn.split("十")
            tens = cn_to_num.get(parts[0], 1) if parts[0] else 1
            ones = cn_to_num.get(parts[1], 0) if len(parts) > 1 and parts[1] else 0
            return float(tens * 10 + ones)
        return float(cn_to_num.get(cn, 0))

    return None


def eval_age(max_age, candidate_age):
    if not max_age:
        return "不限", True
    if candidate_age is None:
        return "未知", False
    return f"{candidate_age}岁", candidate_age <= max_age


def eval_education(min_edu, candidate_edu):
    edu_priority = {"博士": 8, "硕士": 7, "研究生": 7, "本科": 6, "大专": 5, "高中": 4, "中专": 3}
    min_edu = (min_edu or "").strip()
    candidate_edu = (candidate_edu or "").strip()
    display_edu = candidate_edu or "未知"
    if not min_edu or min_edu == "不限":
        return display_edu, True
    return display_edu, edu_priority.get(candidate_edu, 0) >= edu_priority.get(min_edu, 0)


def eval_work_year(min_work_year, candidate_work_year):
    target_min = min_work_year if min_work_year is not None else 0

    # 场景 A：要求本身就不限 (0年)
    if target_min <= 0:
        return "不限", True

    # 场景 B：解析到了具体年限
    if candidate_work_year is not None:
        # 只要解析到数字，就按数字比
        is_ok = candidate_work_year >= target_min
        return f"{candidate_work_year}年", is_ok

    # 场景 C：完全没解析到年限 (candidate_work_year 为 None)
    # 此时不要直接给 False，给一个 "待定" 或者 "见简历"，交给 AI 深度分析
    return "见详情", True # 交给 AI 决定，不要在预过滤阶段拦死


def quick_filter(card_data, job_config):
    """根据列表摘要进行初步硬性过滤（不计入跳过，计入列表过滤）"""
    hard_req = job_config.get("硬性要求", {})

    age_val = parse_age(card_data.get("ageDesc", ""))
    age_display, age_ok = eval_age(hard_req.get("最大年龄"), age_val)
    if not age_ok:
        return False, f"年龄不符合（候选人：{age_display}）"

    edu_display, edu_ok = eval_education(hard_req.get("最低学历"), card_data.get("geekDegree", ""))
    if not edu_ok:
        return False, f"学历不符合（候选人：{edu_display}）"

    return True, ""
def format_geek_data_for_ai(raw_json, card_data):
    """
    仿照 UI 结构提取并整合数据，增加极强的防空保护，防止 NoneType 报错
    """
    # 基础防御：如果 raw_json 本身就是 None
    if not raw_json:
        return "简历详情数据为空"

    data = raw_json

    # --- 核心修复：确保即使字段为 null 也能获得空字典 ---
    # 使用 (obj.get("key") or {}) 替代 obj.get("key", {})
    detail_info = data.get("geekDetailInfo") or {}
    base = detail_info.get("geekBaseInfo") or {}

    # 1. 基本信息
    res = (
        f"【基本信息】\n"
        f"姓名：{base.get('name', '未知')} | 年龄：{base.get('ageDesc', '未知')} | "
        f"经验：{base.get('workYearDesc', '未知')} | 学历：{base.get('degreeCategory', '未知')} | "
        f"状态：{base.get('applyStatusDesc', '未知')}\n"
        f"自我评价：{base.get('userDescription', '无')}\n\n"
    )

    # 2. 工作经历
    work_list = detail_info.get("geekWorkExpList") or []
    res += "【工作经历】\n"
    if not work_list:
        res += "（未填写工作经历）\n"
    else:
        for w in work_list:
            if not isinstance(w, dict): continue
            is_practice = " (实习)" if w.get("showPractice") == 1 else ""
            res += (
                f"- {w.get('company', '未知公司')}{is_practice} | {w.get('positionName', '未知职位')} | "
                f"{w.get('startYearMonStr', '')}-{w.get('endYearMonStr', '')}\n"
                f"  职责描述：{w.get('responsibility', '未填写')}\n"
            )
    res += "\n"

    # 3. 教育经历
    edu_list = detail_info.get("geekEduExpList") or []
    res += "【教育经历】\n"
    if not edu_list:
        res += "（未填写教育经历）\n"
    else:
        for edu in edu_list:
            if not isinstance(edu, dict): continue
            res += f"- {edu.get('school', '未知学校')} | {edu.get('major', '未知专业')} | {edu.get('degreeName', '')} | {edu.get('startDateDesc', '')}-{edu.get('endDateDesc', '')}\n"
    res += "\n"

    # 4. 牛人分析指标
    competitive_data = data.get("jobCompetitive") or {}
    tips = competitive_data.get("tips") or []

    if tips:
        res += "【牛人分析指标】\n"
        for t in tips:
            if isinstance(t, dict):
                res += f"- {t.get('content', '')}\n"

    return res
def analyze_resume_ai(full_text, job_config, card_data=None):
    """调用 AI 进行深度简历分析 - 修正加分项逻辑版"""

    # 1. 提取配置
    hard_req = job_config.get("硬性要求", {})
    must_meet = job_config.get("必须满足", {})
    bonus = job_config.get("加分项", {})
    exclude = job_config.get("排除项", {})

    # 2. 构造硬性要求的实际值
    card_data = card_data or {}
    age_val = parse_age(card_data.get("ageDesc", ""))
    age_display, age_ok = eval_age(hard_req.get("最大年龄"), age_val)

    min_edu = hard_req.get("最低学历", "不限")
    edu_display, edu_ok = eval_education(min_edu, card_data.get("geekDegree", ""))

    work_year_val = parse_work_year(card_data.get("workYearDesc", ""))
    # 修正：如果解析不到数字，显示“见简历描述”，让AI自行根据经历判断
    work_display = f"{work_year_val}年" if work_year_val is not None else "见简历描述"
    work_ok = (work_year_val >= hard_req.get("最小工作年限", 0)) if work_year_val is not None else True

    # 3. 核心提示词（加分项改为可选）
    prompt = f"""你现在是一名极度严苛的首席猎头。请根据“逻辑闭环”对简历进行判定。

    ### 判定逻辑架构（必须严格遵守）：
    1. 【硬性要求 - 强制(AND)】：必须全部符合。有一项“不符合”即淘汰。
       - 最大年龄：≤{hard_req.get('最大年龄', '不限')}岁 (候选人：{age_display}) -> {'符合' if age_ok else '不符合'}
       - 最低学历：{min_edu} (候选人：{edu_display}) -> {'符合' if edu_ok else '不符合'}
       - 最少经验：≥{hard_req.get('最小工作年限', 0)}年 (候选人：{work_display}) -> {'符合' if work_ok else '不符合'}
    
    2. 【必须满足 - 强制(AND)】：核心门槛。每一项都必须在简历中找到明确支撑，缺一不可。
    {json.dumps(must_meet, ensure_ascii=False, indent=2)}
    
    3. 【排除项 - 强制(NOT)】：只要出现任何一项，立即淘汰。
    {json.dumps(exclude, ensure_ascii=False, indent=2)}
    
    4. 【加分项 - 可选(Bonus)】：非强制要求，仅作为提分依据。
       - 命中一项或多项：pass 为 true，score 应在 85-100 分。
       - 一项都没命中：只要上述 1, 2, 3 项符合，pass 仍为 true，但 score 应在 70-84 分。
    {json.dumps(bonus, ensure_ascii=False, indent=2)}
    
    ### 最终合格判定准则：
    只有当 (硬性要求全部通过) AND (必须满足全部命中) AND (排除项零命中) 时，最终结果判定为 pass: true。
    【加分项】不影响是否通过，仅影响最终评分。
    
    ### 当前候选人简历全文：
    {full_text}
    
    请严格按JSON格式输出（严禁任何多余解释）：
    {{
      "pass": true/false,
      "score": 0-100,
      "reason": "说明：1.硬性项匹配度；2.必须项是否全中；3.是否命中加分项（若无则注为无）。用一句话总结。"
    }}"""

    # --- 核心修改：按日期生成日志文件名 ---
    try:
        current_date = time.strftime("%Y-%m-%d") # 获取当前日期，如 2026-04-09
        log_file_path = f"ai_log_{current_date}.txt" # 动态文件名

        with open(log_file_path, "a", encoding="utf-8") as f:
            timestamp = time.strftime("%H:%M:%S") # 日志内只记录具体时间
            f.write(f"\n{'='*25} {timestamp} {'='*25}\n")
            f.write(f"请求参数详情:\n{prompt}\n")
            f.write(f"{'='*60}\n")
    except Exception as e:
        print(f"  [日志写入失败]: {e}")

    # 打印调试信息（可选，建议保留以便观察AI逻辑）
    print(f"\n[AI Decision]:\n")
    print(f"\n[AI Decision]:{prompt}")
    try:
        headers = {
            "Authorization": f"Bearer {ZHIPU_API_KEY}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "glm-4-flash",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1  # 降低随机性，让判断更严谨
        }
        response = requests.post(ZHIPU_API_URL, headers=headers, json=data, timeout=15)
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"]
        else:
            print(f"  [AI请求错误] 状态码: {response.status_code}")
            return None
    except Exception as e:
        print(f"  [AI请求异常]: {e}")
        return None

# --- 浏览器 Fetch 封装 ---

def browser_fetch(page, url):
    """在浏览器环境中执行 GET fetch，自动携带登录态并注入必要 Header"""
    # 关键：确保当前页面在 boss 域名下，否则 fetch 会跨域失败
    if "zhipin.com" not in page.url:
        page.goto("https://www.zhipin.com/web/boss/index")
        time.sleep(2)

    script = f"""
    (async () => {{
        try {{
            // 从 Cookie 动态提取 bst (即 zp_token)
            const bst = document.cookie.split('; ').find(row => row.trim().startsWith('bst='))?.split('=')[1] || '';
            
            const resp = await fetch('{url}', {{
                method: 'GET',
                headers: {{
                    'Accept': 'application/json, text/plain, */*',
                    'X-Requested-With': 'XMLHttpRequest',
                    'zp_token': decodeURIComponent(bst),
                    'Referer': 'https://www.zhipin.com/web/boss/index'
                }}
            }});
            
            if (resp.status === 403) return {{ code: 403, message: '被拦截，请在浏览器手动完成验证码' }};
            return await resp.json();
        }} catch (e) {{
            return {{ code: -1, message: e.message }};
        }}
    }})()
    """
    return page.evaluate(script)

def browser_post(page, url, data, job_id):
    """通用浏览器 POST，支持自定义 Payload 和 Referer"""
    data_str = json.dumps(data)
    # 默认 Referer 设置
    ref_url = f'https://www.zhipin.com/web/frame/recommend/?jobid={job_id}&version=9609'

    script = f"""
    (async () => {{
        try {{
            // 现场提取最新的 bst cookie 作为 zp_token
            const bst = document.cookie.split('; ').find(row => row.startsWith('bst='))?.split('=')[1] || '';
            
            const payload = {data_str};
            const params = new URLSearchParams();
            for (const key in payload) {{
                // 处理可能存在的 null 或 undefined 值，确保传参格式正确
                params.append(key, payload[key] === null || payload[key] === undefined ? '' : payload[key]);
            }}

            const resp = await fetch('{url}', {{
                method: 'POST',
                headers: {{
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'Accept': 'application/json, text/plain, */*',
                    'X-Requested-With': 'XMLHttpRequest',
                    'zp_token': decodeURIComponent(bst),
                    'Origin': 'https://www.zhipin.com',
                    'Referer': '{ref_url}'
                }},
                body: params
            }});

            const contentType = resp.headers.get('content-type') || '';
            if (contentType.includes('application/json')) {{
                return await resp.json();
            }} else {{
                return {{ code: -999, message: '触发了安全校验，请在浏览器中手动完成滑块' }};
            }}
        }} catch (e) {{
            return {{ code: -1, message: e.message }};
        }}
    }})()
    """
    return page.evaluate(script)

# --- 主程序 ---

def main():
    # --- 加载配置以获取默认岗位 ---
    if not os.path.exists("config.json"):
        print("错误: 找不到 config.json 配置文件")
        return

    with open("config.json", "r", encoding="utf-8") as f:
        config = json.load(f)

    default_job_from_config = config.get("default_job", "售后工程师")

    parser = argparse.ArgumentParser(description='BOSS直聘 WAPI 自动化助手')
    parser.add_argument('--job', type=str, default=default_job_from_config, help='岗位名称')
    parser.add_argument('--mode', type=str, default="rec", choices=['rec', 'new'], help='rec:推荐列表, new:最新列表')
    args = parser.parse_args()

    job_name = args.job
    if job_name not in config["jobs"]:
        print(f"未找到岗位配置: {job_name}")
        return

    job_config = config["jobs"][job_name]
    job_id = job_config["jobId"]
    detail_api_base = config["boss_api_resume_detail"]
    add_api_url = config.get("boss_api_resume_add") # 从配置读取收藏接口
    start_api_url = config.get("boss_api_resume_start")  # 打招呼接口

    with sync_playwright() as p:
        print(f"正在连接已打开的 Chrome (9222端口)...")
        try:
            browser = p.chromium.connect_over_cdp("http://localhost:9222")
            context = browser.contexts[0]
            page = context.pages[0]
        except Exception as e:
            print(f"无法连接浏览器: {e}")
            return

        # --- 核心修改：从线上接口动态匹配 JobId ---
        print(f"正在同步线上岗位列表...")
        job_list_url = "https://www.zhipin.com/wapi/zpjob/job/chatted/jobList"
        job_list_res = browser_fetch(page, job_list_url)
        print(job_list_res)

        found_job_id = None
        if job_list_res and job_list_res.get("code") == 0:
            online_jobs = job_list_res.get("zpData", [])
            # 优先寻找包含关键字且在线的岗位
            for job_item in online_jobs:
                on_name = job_item.get("jobName", "")
                if job_name in on_name and job_item.get("jobOnlineStatus") == 1:
                    found_job_id = job_item.get("encryptJobId")
                    print(f"✅ 匹配成功(在线): {on_name} -> ID: {found_job_id}")
                    break
            # 备份：寻找包含关键字的岗位(不论状态)
            if not found_job_id:
                for job_item in online_jobs:
                    on_name = job_item.get("jobName", "")
                    if job_name in on_name:
                        found_job_id = job_item.get("encryptJobId")
                        print(f"⚠️ 匹配到已关闭/异常岗位: {on_name} -> ID: {found_job_id}")
                        break

        if not found_job_id:
            available = [j.get("jobName") for j in job_list_res.get("zpData", [])]
            print(f"❌ 匹配失败：线上岗位中没有包含 '{job_name}' 的职位。")
            print(f"当前线上可用岗位：{available}")
            return

        job_id = found_job_id
        # --------------------------------------------

        print(f"开始执行: {job_name} | 模式: {'推荐' if args.mode=='rec' else '最新'}")
        ctrl = RuntimeControl()
        start_key_listener(ctrl)
        print("[键盘控制] 按 P 暂停，按 S 继续运行。")
        ctrl.show_stats()

        # 外层无限循环
        while True:
            ctrl.wait_if_paused()
            print(f"\n{'='*20} 开始新一轮全量扫描 (1-50页) {'='*20}")

            for page_num in range(1, 51):
                ctrl.wait_if_paused()
                print(f"\n--- 正在处理第 {page_num}/50 页 ---")

                # 构建列表请求 URL
                if args.mode == "rec":
                    list_url = f"https://www.zhipin.com/wapi/zpjob/rec/geek/list?age=16,-1&gender=0&activation=0&recentNotView=0&keyword1=-1&major=0&recentNotView=2301&exchangeResumeWithColleague=0&school=0&switchJobFrequency=0&degree=0&experience=0&intention=0&salary=0&jobId={job_id}&page={page_num}&coverScreenMemory=0&cardType=0"
                else:
                    list_url = f"https://www.zhipin.com/wapi/zprelation/interaction/bossGetGeek?age=16,-1&gender=0&activation=0&recentNotView=0&keyword1=-1&major=0&recentNotView=2301&exchangeResumeWithColleague=0&school=0&switchJobFrequency=0&degree=0&experience=0&intention=0&salary=0&jobid={job_id}&page={page_num}&tag=1&status=1&coverScreenMemory=0"

                # 执行 Fetch
                ctrl.wait_if_paused()
                resp_data = browser_fetch(page, list_url)

                if not resp_data or resp_data.get("code") != 0:
                    print(f"抓取列表失败: {resp_data.get('message', '未知错误')}")
                    break

                geek_list = resp_data.get("zpData", {}).get("geekList", [])
                if not geek_list:
                    print("本页无数据，本轮扫描提前结束。")
                    break

                for item in geek_list:
                    ctrl.wait_if_paused()
                    card = item.get("geekCard", {})
                    name = card.get("geekName", "未知")
                    lid = card.get("lid")
                    security_id = card.get("securityId")

                    # 1. 列表初步过滤
                    passed, reason = quick_filter(card, job_config)
                    if not passed:
                        print(f"  [列表过滤] {name}: {reason}")
                        ctrl.filtered += 1
                        ctrl.show_stats()
                        continue

                    # 2. 获取详情
                    ctrl.viewed += 1
                    ctrl.show_stats()
                    print(f"  [分析中] {name}...", end=" ", flush=True)
                    detail_url = f"{detail_api_base}?securityId={security_id}&lid={lid}"
                    ctrl.wait_if_paused()
                    detail_data = browser_fetch(page, detail_url)

                    if not detail_data or detail_data.get("code") != 0:
                        print(f"无法获取详情")
                        ctrl.show_stats()
                        continue

                    # 3. AI 深度筛选
                    zp_data = detail_data.get("zpData", {})
                    # cleaned_zp_data = clean_json(zp_data) # 去除 null 和空属性
                    # full_resume_text = json.dumps(cleaned_zp_data, ensure_ascii=False)
                    structured_text = format_geek_data_for_ai(zp_data, card)
                    ai_result_raw = analyze_resume_ai(structured_text, job_config, card)

                    # 解析 AI 结果并打印结论
                    try:
                        ai_json = json.loads(re.search(r'\{.*\}', ai_result_raw, re.S).group())
                        score = ai_json.get("score", 0)
                        pass_flag = ai_json.get("pass")

                        if pass_flag and score >= job_config.get("通过分数", 75):
                            print(f"✅ 通过 ({score}分)")

                            # --- 自动收藏功能 ---
                            if add_api_url:
                                geek_base_info = zp_data.get("geekDetailInfo", {}).get("geekBaseInfo", {})
                                encrypt_geek_id = geek_base_info.get("encryptGeekId")

                                if encrypt_geek_id:
                                    print(f"    正在自动收藏 {name}...")
                                    add_payload = {
                                        "markType": 5,
                                        "encryptMarkId": encrypt_geek_id,
                                        "securityId": security_id
                                    }
                                    add_res = browser_post(page, add_api_url, add_payload, job_id)
                                    if add_res.get("code") == 0:
                                        print(f"    ⭐️ 收藏成功")
                                        ctrl.collected += 1
                                        ctrl.show_stats()
                                    else:
                                        print(f"    ❌ 收藏失败: {add_res.get('message')}")

                            # --- 自动打招呼功能 ---
                            if start_api_url:
                                print(f"    正在自动向 {name} 打招呼...")
                                greet_payload = {
                                    "gid": card.get("encryptGeekId"),
                                    "suid": "",
                                    "jid": card.get("encryptJobId"),
                                    "expectId": card.get("expectId"),
                                    "lid": lid,
                                    "greet": "",
                                    "from": "",
                                    "securityId": security_id,
                                    "customGreetingGuide": -1
                                }
                                greet_res = browser_post(page, start_api_url, greet_payload, job_id)

                                if greet_res.get("code") == 0:
                                    print(f"    💬 打招呼成功！")
                                else:
                                    print(f"    ❌ 打招呼失败: {greet_res.get('message')}")

                        else:
                            print(f"❌ 拒绝 ({ai_json.get('reason', '不匹配')})")
                            ctrl.skipped += 1
                            ctrl.show_stats()
                    except Exception as e:
                        print(f"AI解析异常: {e}")
                        ctrl.show_stats()

                    # --- 修改为随机防频控等待 (1.0 - 3.0 秒) ---
                    sleep_interruptible(ctrl, random.uniform(1.0, 3.0))

            print("\n[循环重置] 已完成第 1-50 页扫描，等待 60 秒后重头开始...")
            sleep_interruptible(ctrl, 60)

if __name__ == "__main__":
    main()