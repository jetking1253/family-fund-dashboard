import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from fund_logic import (
    get_latest_nav, 
    get_members_summary, 
    update_assets_and_nav, 
    process_invest,
    get_nav_history_df,
    get_latest_assets_allocation,
    rollback_last_action,  # V2新增回滚支持
    add_member,            # V3新增扩口
    update_member_name     # V3改名扩口
)
from db import init_db, verify_user, change_password, add_user
import ai_parser

# --------- 页面配置 ---------
st.set_page_config(
    page_title="家庭基金管理系统 V4",
    page_icon="📈",
    layout="wide"
)

# 初始化数据库(安全调用，如已存在则跳过)
init_db()

# --------- V4: 全局登录拦截墙 ---------
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
if 'current_user' not in st.session_state:
    st.session_state['current_user'] = ""

if not st.session_state['logged_in']:
    st.markdown("<h1 style='text-align: center;'>🔐 家庭基金管理系统 - 安全访问凭证</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: gray;'>V4 引入了公网访问级别的本地隔离阻断体系，保护数据隐私不泄露。</p>", unsafe_allow_html=True)
    
    col_l, col_m, col_r = st.columns([1, 1, 1])
    with col_m:
        with st.form("login_form"):
            user_input = st.text_input("分配账号", placeholder="例如 defaults：admin")
            pass_input = st.text_input("安全密码", type="password")
            submitted = st.form_submit_button("登录验证", type="primary", use_container_width=True)
            
            if submitted:
                try:
                    is_valid = verify_user(user_input, pass_input)
                    if is_valid:
                        st.session_state['logged_in'] = True
                        st.session_state['current_user'] = user_input
                        st.success("身份验证成功！正在进入安全网关...")
                        import time
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("❌ 抱歉，账号或密码错误。如果您是初次部署，默认超管为 admin 与 admin123")
                except Exception as e:
                    import traceback
                    st.error(f"⚠️ [核心崩溃报告] 鉴权过程中发生了底层异常：{e}")
                    st.code(traceback.format_exc())
    
    # 未登录状态下，强行阻断所有下文渲染
    st.stop()
    
# 如果执行到这里，说明鉴权通过
with st.sidebar:
    st.success(f"👋 欢迎登录回来：**{st.session_state['current_user']}**")
    if st.button("🚪 锁定并退出", use_container_width=True):
        st.session_state['logged_in'] = False
        st.session_state['current_user'] = ""
        st.rerun()
    st.markdown("---")

# --------- V3: 侧边栏 API Key 及自定义模型配置 ---------
with st.sidebar:
    st.header("⚙️ AI 视觉配置 (V3自定义版)")
    st.markdown("支持任何提供 OpenAI 兼容 `chat/completions` Vision 接口的大语言模型。")
    
    api_key_input = st.text_input("填入 API Key (如 sk-...)", type="password", help="在此处填入用于请求模型的认证秘钥。如果已配置系统环境变量 OPENAI_API_KEY 可留空。")
    base_url_input = st.text_input("填入 Base URL (选填)", placeholder="如 https://api.deepseek.com/v1", help="如果不填，默认请求官方 https://api.openai.com/v1")
    model_name_input = st.text_input("填入模型名称 (选填)", placeholder="如 gpt-4o, qwen-vl-max...", help="如果不知道，默认将以 gpt-4o 请求远端")
    
    # 动态覆写配置
    if api_key_input:
        ai_parser.API_KEY = api_key_input
    if base_url_input:
        ai_parser.BASE_URL = base_url_input
    if model_name_input:
        ai_parser.MODEL_NAME = model_name_input
    
    st.markdown("---")
    st.info("智能 OCR 防呆提示：所有通过图片解析出的金额只会填入输入框，**需要您人工核对无误后点击红色的提交按钮才会真实入库**。")

# --------- 数据获取 ---------
nav_data = get_latest_nav()
if not nav_data:
    st.error("无法获取净值数据，请检查数据库配置。")
    st.stop()

latest_nav = round(nav_data['nav'], 4)
total_assets = round(nav_data['total_assets'], 4)

st.title("📈 家庭基金管理综合看板 V4")

# --------- V4 标签页划分 ---------
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["📊 数据总览", "💰 智能定投录入", "📝 智能资产快照", "📜 历史与回滚", "👥 家庭成员管理中心", "🔐 账号安全配置"])

# ================= TAB 1: 数据总览 =================
with tab1:
    col1, col2 = st.columns(2)
    with col1:
        st.metric("基金当前总规模", f"¥ {total_assets:,.2f}")
    with col2:
        st.metric("最新单位净值 (NAV)", f"{latest_nav:.4f}")
        
    st.markdown("---")
    st.subheader("👥 成员资产清单")
    
    members_data = get_members_summary()
    if members_data:
        df_members = pd.DataFrame(members_data)
        st.dataframe(df_members.style.format({
            "累 计 本 金": "{:,.2f}",
            "当 前 市 值": "{:,.2f}",
            "持 有 份 额": "{:.4f}",
            "收 益 率 (%)": "{:.2f}%"
        }), use_container_width=True)
        
    st.markdown("---")
    col_chart1, col_chart2 = st.columns(2)
    with col_chart1:
        st.subheader("📈 历史净值走势")
        df_history = get_nav_history_df()
        if not df_history.empty:
            fig_nav = px.line(df_history, x='timestamp', y='nav', markers=True)
            fig_nav.add_trace(go.Scatter(
                x=[df_history['timestamp'].min(), df_history['timestamp'].max()],
                y=[1.0, 1.0], mode="lines", name="基准线 (1.0)",
                line=dict(color="red", dash="dash")
            ))
            fig_nav.update_layout(xaxis_title="日期", yaxis_title="单位净值", template="plotly_white")
            st.plotly_chart(fig_nav, use_container_width=True)
    with col_chart2:
         st.subheader("🥧 当前资产仓位占比")
         allocation = get_latest_assets_allocation()
         if allocation and sum(allocation.values()) > 0:
             color_map = {"港股": "#1f77b4", "美股": "#2ca02c", "红利": "#ff7f0e", "高风险": "#d62728"}
             fig_pie = px.pie(
                 names=list(allocation.keys()), 
                 values=list(allocation.values()),
                 color=list(allocation.keys()),
                 color_discrete_map=color_map,
                 hole=0.4
             )
             fig_pie.update_layout(template="plotly_white")
             st.plotly_chart(fig_pie, use_container_width=True)

# ================= TAB 2: 智能定投录入 =================
with tab2:
    st.subheader("➕ 智能定投录入")
    st.info(f"净值锁定： {latest_nav:.4f}")
    
    # AI 识别区
    with st.expander("📸 上传定投转账截图自动识别金额", expanded=True):
        inv_img = st.file_uploader("上传转账凭证", type=['png', 'jpg', 'jpeg'], key="inv_upload")
        if inv_img is not None:
            if st.button("🤖 AI 提取定投金额"):
                with st.spinner("Gemini 视觉分析中..."):
                    succ, val = ai_parser.parse_investment_amount(inv_img)
                    if succ:
                        st.session_state['auto_invest_val'] = float(val)
                        st.success(f"识别成功：建议金额为 {val}")
                    else:
                        st.error(val)

    # 用 session_state 回填
    default_inv = st.session_state.get('auto_invest_val', 0.0)

    if not members_data:
        st.warning("⚠️ 当前没有任何家庭成员，请先到『👥 家庭成员管理中心』添加成员后再进行定投。")
    else:
        with st.form("invest_form"):
            col_m1, col_m2 = st.columns(2)
            with col_m1:
                member_names = {m['ID']: m['成 员'] for m in members_data}
                selected_member_name = st.selectbox("选择定投成员", list(member_names.values()))
                selected_id = list(member_names.keys())[list(member_names.values()).index(selected_member_name)]
            with col_m2:
                # 数据回填支持
                invest_amount = st.number_input("在此核对最终定投金额 (元)", min_value=0.0, value=default_inv, step=100.0)
                
            submitted_invest = st.form_submit_button("确认录入定投", type="primary")
            if submitted_invest:
                if invest_amount > 0:
                    success, msg = process_invest(selected_id, invest_amount)
                    if success:
                        st.toast("✅ 定投处理并更新成功")
                        # 提交成功后清除残余 AI 缓存
                        if 'auto_invest_val' in st.session_state:
                             del st.session_state['auto_invest_val']
                        st.rerun()
                    else:
                        st.error(f"录入失败: {msg}")
                else:
                     st.warning("金额需要大于0")

# ================= TAB 3: 智能资产快照 =================
with tab3:
    st.subheader("📝 智能资产快照评估")
    
    with st.expander("📸 批量上传券商持仓截图智能填表"):
         st.markdown("您可以为各大资产仓位分布上传手机截图（交由AI解析后，将自动回填下方数字供您最终核对）。")
         col_upl1, col_upl2, col_upl3, col_upl4 = st.columns(4)
         with col_upl1:
              hk_img = st.file_uploader("港股截图", type=['png', 'jpg', 'jpeg'], key="hk_up")
         with col_upl2:
              us_img = st.file_uploader("美股截图", type=['png', 'jpg', 'jpeg'], key="us_up")
         with col_upl3:
              div_img = st.file_uploader("红利截图", type=['png', 'jpg', 'jpeg'], key="div_up")
         with col_upl4:
              hr_img = st.file_uploader("高风险截图", type=['png', 'jpg', 'jpeg'], key="hr_up")
              
         if st.button("🤖 开始批量识别市值"):
              with st.spinner("Gemini 多模态并发分析中..."):
                   if hk_img:
                       s, v = ai_parser.parse_asset_snapshot(hk_img)
                       if s: st.session_state['hk_val'] = float(v)
                   if us_img:
                       s, v = ai_parser.parse_asset_snapshot(us_img)
                       if s: st.session_state['us_val'] = float(v)
                   if div_img:
                       s, v = ai_parser.parse_asset_snapshot(div_img)
                       if s: st.session_state['div_val'] = float(v)
                   if hr_img:
                       s, v = ai_parser.parse_asset_snapshot(hr_img)
                       if s: st.session_state['hr_val'] = float(v)
              st.success("解析完成，请在下方核实回填的数据。")

    # 回填
    def_hk = st.session_state.get('hk_val', 0.0)
    def_us = st.session_state.get('us_val', 0.0)
    def_div = st.session_state.get('div_val', 0.0)
    def_hr = st.session_state.get('hr_val', 0.0)

    with st.form("asset_form"):
        col_a1, col_a2 = st.columns(2)
        with col_a1:
            hk_val = st.number_input("📝 港股市值", min_value=0.0, value=def_hk, step=1000.0)
            us_val = st.number_input("📝 美股市值", min_value=0.0, value=def_us, step=1000.0)
        with col_a2:
            div_val = st.number_input("📝 低波红利股市值", min_value=0.0, value=def_div, step=1000.0)
            hr_val = st.number_input("📝 高风险股市值", min_value=0.0, value=def_hr, step=1000.0)
            
        submitted_assets = st.form_submit_button("计算最新净值并归档", type="primary")
        
        if submitted_assets:
            total_input = hk_val + us_val + div_val + hr_val
            if total_input == 0:
                 st.warning("所有资产市值总和不能为0，请确认您的输入。")
            else:
                 success, msg = update_assets_and_nav(hk_val, us_val, div_val, hr_val)
                 if success:
                     st.toast("✅ 新净值生成与重估成功")
                     # 成功后清除缓存
                     for k in ['hk_val', 'us_val', 'div_val', 'hr_val']:
                         if k in st.session_state: del st.session_state[k]
                     st.rerun()
                 else:
                     st.error(f"净值更新失败: {msg}")

# ================= TAB 4: 历史与回滚 (V2) =================
with tab4:
    st.subheader("📜 容错中心：撤销记录")
    st.markdown("⚠️ **高危操作**：如果您在上面“填错数字”并按下了确认导致目前净值或大盘状态出局，您可以在此撤销系统的最后一笔业务数据（无论是定投流水，还是新的资产重新快照）。")
    st.info("💡 回滚将原子级物理删除最后一笔错误的资产快照及与之关联的交易，扣减错误折算的人员本金与份额，将系统强制时空旅行退回上一状态。**支持多次连续撤销**。")
    
    if st.button("⚠️ 确认：撤回系统的最后一笔操作", type="primary"):
        with st.spinner("执行事务级安全回滚..."):
             resp_success, resp_msg = rollback_last_action()
             if resp_success:
                 st.success(f"✅ 执行成功：{resp_msg}")
                 st.toast("时间倒流成功")
                 # 给点反应时间让用户看清字再重绘
                 import time
                 time.sleep(2)
                 st.rerun()
             else:
                 st.error(resp_msg)
                 
st.markdown("<br><hr>", unsafe_allow_html=True)
# ================= TAB 5: V3 新增成员管理 =================
with tab5:
    st.subheader("👥 家庭成员管理中心")
    st.markdown("为了保证净值与财务系统的对账一致性，此处**仅允许新增成员**或**修改成员称呼**。如果您需要修改某位成员的资产资金，请统一使用『💰 智能定投录入』进行冲改（支持输入负数进行资金抽取）。")
    
    col_mem1, col_mem2 = st.columns(2)
    with col_mem1:
        st.markdown("#### ✨ 新增家庭成员")
        with st.form("add_member_form"):
            new_mem_name = st.text_input("新成员姓名 / 昵称")
            if st.form_submit_button("确认创建成员", type="primary"):
                succ, msg = add_member(new_mem_name)
                if succ:
                     st.success(msg)
                     import time
                     time.sleep(1)
                     st.rerun()
                else:
                     st.error(msg)
                     
    with col_mem2:
        st.markdown("#### ✏️ 修改现有成员信息")
        if not members_data:
            st.info("暂无成员数据，请先在左侧新增成员。")
        else:
            with st.form("update_member_form"):
                member_names = {m['ID']: m['成 员'] for m in members_data}
                selected_upd_name = st.selectbox("选择要修改的现有成员", list(member_names.values()), key="upd_sel")
                selected_upd_id = list(member_names.keys())[list(member_names.values()).index(selected_upd_name)]
                
                new_edit_name = st.text_input("更新为您期望的新姓名", value=selected_upd_name)
                if st.form_submit_button("保存修改", type="primary"):
                     succ, msg = update_member_name(selected_upd_id, new_edit_name)
                     if succ:
                         st.success(msg)
                         import time
                         time.sleep(1)
                         st.rerun()
                     else:
                         st.error(msg)

st.markdown("<br><hr>", unsafe_allow_html=True)
# ================= TAB 6: V4 安全中心 =================
with tab6:
    st.subheader("🔐 账号安全配置中心")
    st.markdown("系统处于公网安全保护模式。当前操作员拥有修改自身密码和向其他家庭成员分配系统账号的权限。")
    
    col_s1, col_s2 = st.columns(2)
    with col_s1:
        st.markdown("#### 🔑 修改我的密码")
        with st.form("pwd_change_form"):
            current_logged = st.session_state['current_user']
            st.text_input("当前登录账号", value=current_logged, disabled=True)
            new_pwd = st.text_input("设为新密码", type="password")
            new_pwd_confirm = st.text_input("确认新密码", type="password")
            
            if st.form_submit_button("立即修改", type="primary"):
                if not new_pwd:
                    st.error("密码不能为空")
                elif new_pwd != new_pwd_confirm:
                    st.error("两次输入的密码不匹配！")
                else:
                    s_pwd, m_pwd = change_password(current_logged, new_pwd)
                    if s_pwd:
                         st.success("密码已成功修改！为了安全起见，您的状态已被注销，请用新密码重新登录系统。")
                         import time
                         time.sleep(2)
                         st.session_state['logged_in'] = False
                         st.session_state['current_user'] = ""
                         st.rerun()
                    else:
                         st.error(m_pwd)
                         
    with col_s2:
        st.markdown("#### ➕ 增开后台新席位")
        with st.form("new_user_form"):
             st.info("💡 为其他负责家庭财务录入的成员配置独立的登录账号保护层。")
             create_username = st.text_input("期望分配的用户名 (如 mom, dad)")
             create_pwd = st.text_input("初始登录密码", type="password")
             if st.form_submit_button("确认开通", type="primary"):
                 if not create_username or not create_pwd:
                     st.error("新用户名和密码各项均不可为空白。")
                 else:
                     s_usr, m_usr = add_user(create_username, create_pwd)
                     if s_usr:
                         st.success(f"🎊 {m_usr}！您可以通过这套账户再次登入管理平台了。")
                     else:
                         st.error(m_usr)

st.markdown("<br><hr>", unsafe_allow_html=True)
st.caption("Family Fund Manager V4 © 2026 | Powered by Streamlit, Supabase & OpenAPI")
