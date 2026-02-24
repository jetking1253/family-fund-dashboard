import os
import streamlit as st
import hashlib
from supabase import create_client, Client

@st.cache_resource
def get_supabase() -> Client:
    """初始化并缓存 Supabase 客户端"""
    url: str = st.secrets["SUPABASE_URL"]
    key: str = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

def init_db():
    """云端数据库通过 SQL 脚本初始化，这里只需验证连接即可"""
    pass

# --------- 账号鉴权控制接口 ---------
def verify_user(username, password_plaintext):
    """核对用户名和密码，返回 (是否通过, 角色字符串)"""
    try:
        supabase = get_supabase()
        response = supabase.table("app_users").select("password_hash, role").eq("username", username).execute()
        
        if not response.data:
            return False, None
        
        stored_hash = response.data[0]['password_hash']
        input_hash = hashlib.sha256(password_plaintext.encode()).hexdigest()
        if input_hash == stored_hash:
            return True, response.data[0].get('role', 'viewer')
        return False, None
    except Exception as e:
        print(f"验证用户失败: {e}")
        return False, None

def change_password(username, new_password_plaintext):
    """修改指定账户密码并落盘"""
    try:
        supabase = get_supabase()
        new_hash = hashlib.sha256(new_password_plaintext.encode()).hexdigest()
        response = supabase.table("app_users").update({"password_hash": new_hash}).eq("username", username).execute()
        
        if not response.data:
            return False, "用户不存在"
        return True, "密码修改成功"
    except Exception as e:
        return False, f"修改失败: {e}"

def add_user(username, password_plaintext):
    """新增额外的系统访问账号（默认 viewer 只读角色）"""
    try:
        supabase = get_supabase()
        # 检查是否已被占用
        existing = supabase.table("app_users").select("id").eq("username", username).execute()
        if existing.data:
            return False, "用户名已被占用"
            
        new_hash = hashlib.sha256(password_plaintext.encode()).hexdigest()
        supabase.table("app_users").insert({
            "username": username,
            "password_hash": new_hash,
            "role": "viewer"
        }).execute()
        return True, "账号创建成功（只读权限）"
    except Exception as e:
        return False, f"创建失败: {e}"

# --------- 数据层抽象接口 (Data Access Layer) ---------
def db_get_latest_nav():
    """获取最新的一条净值记录"""
    try:
        supabase = get_supabase()
        response = supabase.table("nav_history").select("*").order("id", desc=True).limit(1).execute()
        return response.data[0] if response.data else None
    except Exception as e:
        print(f"查询最新净值失败: {e}")
        return None

def db_get_all_members():
    """获取所有成员列表"""
    try:
        supabase = get_supabase()
        response = supabase.table("members").select("*").order("id").execute()
        return response.data
    except Exception as e:
        print(f"查询成员失败: {e}")
        return []

def db_get_member_by_name(name):
    try:
        supabase = get_supabase()
        response = supabase.table("members").select("id").eq("name", name).execute()
        return response.data[0] if response.data else None
    except Exception:
        return None

def db_add_member(name):
    try:
        supabase = get_supabase()
        supabase.table("members").insert({"name": name, "invested_principal": 0.0, "total_shares": 0.0}).execute()
        return True, f"成功新增家庭成员：{name}"
    except Exception as e:
        return False, f"添加成员失败: {e}"

def db_get_member_by_name_exclude_id(name, exclude_id):
    try:
        supabase = get_supabase()
        response = supabase.table("members").select("id").eq("name", name).neq("id", exclude_id).execute()
        return response.data[0] if response.data else None
    except Exception:
        return None

def db_update_member_name(member_id, new_name):
    try:
        supabase = get_supabase()
        supabase.table("members").update({"name": new_name}).eq("id", member_id).execute()
        return True, "成员姓名修改成功"
    except Exception as e:
        return False, f"修改成员姓名失败: {e}"

def db_insert_assets_and_nav(hk, us, div, hr, new_total_assets, current_total_shares, new_nav):
    try:
        supabase = get_supabase()
        # 1. 插入资产快照
        supabase.table("assets_history").insert({
            "hk": hk, "us": us, "dividend": div, "high_risk": hr
        }).execute()
        
        # 2. 插入净值快照
        supabase.table("nav_history").insert({
            "total_assets": new_total_assets,
            "total_shares": current_total_shares,
            "nav": new_nav
        }).execute()
        return True, "资产与净值更新成功！"
    except Exception as e:
        return False, str(e)

def db_process_invest(member_id, amount, new_shares, new_sys_assets, new_sys_shares, latest_nav):
    """处理定投的数据库操作"""
    try:
        supabase = get_supabase()
        
        # 1. 插入新净值历史
        supabase.table("nav_history").insert({
            "total_assets": new_sys_assets,
            "total_shares": new_sys_shares,
            "nav": latest_nav
        }).execute()
        
        # 2. 更新个人总份额和投入本金
        member_resp = supabase.table("members").select("invested_principal, total_shares").eq("id", member_id).execute()
        if not member_resp.data:
            return False, "找不到该成员"
            
        cur_principal = member_resp.data[0]['invested_principal']
        cur_shares = member_resp.data[0]['total_shares']
        
        supabase.table("members").update({
            "invested_principal": cur_principal + amount,
            "total_shares": cur_shares + new_shares
        }).eq("id", member_id).execute()
        
        # 3. 记录流水
        supabase.table("transactions").insert({
            "member_id": member_id,
            "type": "INVEST",
            "amount": amount,
            "nav": latest_nav,
            "shares": new_shares
        }).execute()
        
        return True, f"成功新增定投。按最新净值 {latest_nav} 折算获得份额 {new_shares} 份。"
    except Exception as e:
        return False, str(e)

def db_get_nav_history_all():
    """获取所有净值历史"""
    try:
        supabase = get_supabase()
        response = supabase.table("nav_history").select("id, timestamp, nav, total_assets").order("id", desc=False).execute()
        return response.data
    except Exception as e:
        print(f"获取净值历史失败: {e}")
        return []

def db_get_latest_assets_allocation():
    try:
        supabase = get_supabase()
        response = supabase.table("assets_history").select("hk, us, dividend, high_risk").order("id", desc=True).limit(1).execute()
        return response.data[0] if response.data else {}
    except Exception:
        return {}

def db_rollback_last_action():
    try:
        supabase = get_supabase()
        
        # 获取最近的一笔非 INIT 交易
        txn_resp = supabase.table("transactions").select("*").neq("type", "INIT").order("id", desc=True).limit(1).execute()
        last_txn = txn_resp.data[0] if txn_resp.data else None
        
        nav_count_resp = supabase.table("nav_history").select("id", count="exact").execute()
        nav_count = nav_count_resp.count
        
        if nav_count <= 1:
            return False, "当前系统已经是初始状态，无法继续撤销！"
            
        nav_resp = supabase.table("nav_history").select("*").order("id", desc=True).limit(1).execute()
        last_nav = nav_resp.data[0] if nav_resp.data else None
        
        is_last_txn = False
        if last_txn and last_nav and (last_txn['timestamp'] >= last_nav['timestamp']):
            is_last_txn = True
            
        if is_last_txn:
            amount = last_txn['amount']
            shares = last_txn['shares']
            member_id = last_txn['member_id']
            
            # 扣减成员资产
            mem_resp = supabase.table("members").select("invested_principal, total_shares").eq("id", member_id).execute()
            if mem_resp.data:
                cur_p = mem_resp.data[0]['invested_principal']
                cur_s = mem_resp.data[0]['total_shares']
                supabase.table("members").update({
                    "invested_principal": float(cur_p) - float(amount),
                    "total_shares": float(cur_s) - float(shares)
                }).eq("id", member_id).execute()
            
            # 删除记录
            supabase.table("transactions").delete().eq("id", last_txn['id']).execute()
            supabase.table("nav_history").delete().eq("id", last_nav['id']).execute()
            
            action_msg = f"撤销了最后一笔定投金额 {amount} 元，并回退了相关份额。"
        else:
            supabase.table("nav_history").delete().eq("id", last_nav['id']).execute()
            
            # 删除最后一条 assets_history
            asset_resp = supabase.table("assets_history").select("id").order("id", desc=True).limit(1).execute()
            if asset_resp.data:
                supabase.table("assets_history").delete().eq("id", asset_resp.data[0]['id']).execute()
                
            action_msg = "撤销了最后一次填报的四大资产市值快照评估。"
            
        return True, action_msg
    except Exception as e:
        return False, f"撤销失败: {e}"
