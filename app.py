import streamlit as st
import database
import json

st.set_page_config(page_title="AI招聘专家系统", layout="wide")

st.title("基于“画像对齐-证据审计”的双闭环 AI 招聘专家系统")

# 初始化数据库
database.init_db()

# --- 阶段 1：选择/输入职位名称 ---
st.header("阶段 1：选择待招聘的线上职位")
st.info("说明：由于我们需要绑定真实的线上职位进行抓取，所以这里必须从 Boss 账号下的已有职位中进行选择。\n\n**如何拉取职位？** 请在终端运行 `start.sh` 或 `python webBossAI.py`，爬虫启动时会自动同步您账号下的在线职位到此列表中。")

if st.button("刷新在线职位列表"):
    st.rerun()

online_jobs = database.get_online_jobs()
if not online_jobs:
    st.warning("暂未获取到线上职位信息，请先确保后台爬虫进程运行过一次以同步职位列表。")
    st.stop()

job_names = [job['job_name'] for job in online_jobs]
job_name_input = st.selectbox("请选择要进行画像校准的职位：", job_names)

# --- 阶段 2：JD 录入与 AI 深度转译 ---
st.header("阶段 2：输入 JD 进行画像初建")

default_jd = """岗位要求：
1. 本科及以上学历，机械、自动化相关专业；
2. 5年以上大B端设备销售经验，有绳锯机、石材机械销售经验者优先；
3. 具备极强的狼性和抗压能力；
4. 沟通能力强，适应长期出差。"""

jd_text = st.text_area("输入原始 JD", value=default_jd, height=200)

if 'profile' not in st.session_state:
    st.session_state.profile = None

if st.button("AI 深度转译 (生成画像初稿)"):
    if not job_name_input:
        st.error("请先在上面输入职位名称！")
        st.stop()
    st.info("正在调用 AI 分析 JD...")
    import requests
    import re
    import os
    import json

    # 从 config.json 中读取 ZHIPU_API_KEY
    ZHIPU_API_KEY = ""
    try:
        with open("config.json", "r", encoding="utf-8") as f:
            config_data = json.load(f)
            ZHIPU_API_KEY = config_data.get("ZHIPU_API_KEY", "")
    except Exception as e:
        st.error(f"读取 config.json 失败: {e}")
        st.stop()

    if not ZHIPU_API_KEY:
        st.error("未在 config.json 中配置 ZHIPU_API_KEY。")
        st.stop()

    ZHIPU_API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

    prompt = f"""
    请作为首席招聘官，将以下口语化的 JD 转译为严谨的“胜任力逻辑模型”。
    请严格按以下 JSON 格式输出，不要有其他废话：
    {{
        "岗位角色": "例如：工业设备销售",
        "显性要求": {{
            "最低学历": "例如：本科",
            "专业要求": ["例如：机械", "自动化"],
            "最小工作年限": 5
        }},
        "隐性要求": {{
            "特质要求1": "详细说明，如 狼性/抗压",
            "特质要求2": "如 大B端能力"
        }},
        "加分经验": ["经验1", "经验2"],
        "核心关注点权重": {{
            "学历": 10,
            "经验": 40,
            "特质要求1": 30,
            "特质要求2": 20
        }}
    }}

    原始 JD：
    {jd_text}
    """

    headers = {
        "Authorization": f"Bearer {ZHIPU_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "glm-4-flash",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1
    }
    try:
        response = requests.post(ZHIPU_API_URL, headers=headers, json=data, timeout=15)
        if response.status_code == 200:
            content = response.json()["choices"][0]["message"]["content"]
            # 提取 JSON
            json_match = re.search(r'\{.*\}', content, re.S)
            if json_match:
                ai_result = json.loads(json_match.group())
                st.session_state.profile = ai_result
                st.success("画像生成完毕！")
            else:
                st.error("AI 格式解析失败。返回内容：" + content)
        else:
            st.error(f"AI 调用失败：状态码 {response.status_code}")
    except Exception as e:
         st.error(f"AI 调用异常：{e}")

# --- 阶段 2：画像对齐与人工校准 ---
if st.session_state.profile is not None:
    st.header("阶段 2：画像对齐与人工校准")

    st.subheader("当前《岗位画像初稿》")
    st.json(st.session_state.profile)

    st.markdown("---")
    st.subheader("意图修改框：调整与补充")

    # 修改权重 (Mock 形式)
    st.write("调整特征权重：")
    col1, col2, col3, col4 = st.columns(4)
    weights = st.session_state.profile.get("核心关注点权重", {})

    new_weights = {}
    with col1:
        new_weights["学历"] = st.slider("学历 权重", 0, 100, weights.get("学历", 10))
    with col2:
        new_weights["经验"] = st.slider("经验 权重", 0, 100, weights.get("经验", 40))
    with col3:
        new_weights["狼性/抗压"] = st.slider("狼性/抗压 权重", 0, 100, weights.get("狼性/抗压", 30))
    with col4:
        new_weights["大B端能力"] = st.slider("大B端能力 权重", 0, 100, weights.get("大B端能力", 20))

    feedback_text = st.text_input("附加纠偏指令 (如：放宽学历要求，只要能力强就行)")

    if st.button("重新生成《最终执行画像》"):
        # Mock 再次调用 AI 处理反馈后的画像
        st.session_state.profile["核心关注点权重"] = new_weights
        if feedback_text:
             st.session_state.profile["用户附加指令"] = feedback_text
        st.success("更新成功！最终执行画像已锁定。")

        # 将最新的画像保存到 DB
        database.save_job_profile(job_name_input, st.session_state.profile)
        st.info(f"[{job_name_input}] 画像已保存到数据库 (JobProfile)，扫描引擎将按此标准执行。")

# --- 阶段 3 & 4：简历评审墙与人工复核闭环 ---
st.header("阶段 3 & 4：简历评审与证据审计闭环")

if st.button("刷新简历池"):
    st.rerun()

resumes = database.get_all_resumes()

if not resumes:
    st.info("当前简历库为空，请先运行后台抓取引擎。")
else:
    # 简单的统计
    s_count = sum(1 for r in resumes if r['status'] == 'S')
    a_count = sum(1 for r in resumes if r['status'] == 'A')
    r_count = sum(1 for r in resumes if r['status'] == 'REJECTED')

    st.write(f"**统计：** S级: {s_count} | A级: {a_count} | 淘汰: {r_count} | 总计: {len(resumes)}")

    # 状态过滤
    filter_status = st.selectbox("筛选状态", ["全部", "S", "A", "REJECTED"])

    for r in resumes:
        if filter_status != "全部" and r['status'] != filter_status:
            continue

        with st.expander(f"[{r['status']}] {r['name']} - 评分: {r['score']}"):
            st.markdown(f"**AI 评分:** {r['score']}")
            st.markdown(f"**系统分级状态:** {r['status']}")

            st.markdown("**证据清单 (Evidence List):**")
            if r['evidence_list']:
                for ev in r['evidence_list']:
                    st.write(f"- {ev}")
            else:
                st.write("暂无证据清单提取。")

            col1, col2 = st.columns(2)
            with col1:
                if st.button(f"手动发起打招呼", key=f"greet_{r['id']}"):
                    database.add_manual_action(r['id'], "greet")
                    st.success(f"已将向 {r['name']} 发起打招呼的任务加入后台队列！")
            with col2:
                if st.button(f"手动收藏", key=f"collect_{r['id']}"):
                    database.add_manual_action(r['id'], "collect")
                    st.success(f"已将收藏 {r['name']} 的任务加入后台队列！")

            st.markdown("---")
            st.markdown("**负反馈与纠偏学习**")
            reason = st.text_input(f"如果判断不准，请给出拒绝理由 (针对 {r['name']})", key=f"reason_{r['id']}")
            if st.button("提交反馈并更新画像标准", key=f"btn_reason_{r['id']}"):
                st.warning(f"接收到反馈: '{reason}'。系统将自动提取负面特征，更新到 JobProfile 供下一次扫描使用！")

                # Mock 反馈更新过程
                if st.session_state.profile:
                     st.session_state.profile["负面教训"] = st.session_state.profile.get("负面教训", []) + [reason]
                     database.save_job_profile(job_name_input, st.session_state.profile)
                     st.info("已记录反馈并生成新的画像标准，下一轮抓取直接生效！")
