import pandas as pd
from datetime import datetime
from db import (
    db_get_latest_nav,
    db_get_all_members,
    db_get_member_by_name,
    db_add_member,
    db_get_member_by_name_exclude_id,
    db_update_member_name,
    db_insert_assets_and_nav,
    db_insert_asset_details,
    db_get_latest_asset_details,
    db_process_invest,
    db_get_nav_history_all,
    db_get_latest_assets_allocation,
    db_rollback_last_action
)

def get_latest_nav():
    """获取最新的一条净值记录"""
    return db_get_latest_nav()

def get_members_summary():
    """获取各个成员的汇总展示信息（基于最新净值）"""
    nav_record = get_latest_nav()
    if not nav_record:
        return []

    latest_nav = float(nav_record['nav'])
    
    # 从数据库获取成员
    members_list = db_get_all_members()
    
    summary = []
    for member in members_list:
        shares = round(float(member['total_shares']), 4)
        principal = round(float(member['invested_principal']), 4)
        current_value = round(shares * latest_nav, 4)
        return_rate = round((current_value - principal) / principal * 100, 4) if principal > 0 else 0.0

        summary.append({
            'ID': member['id'],
            '成 员': member['name'],
            '累 计 本 金': principal,
            '持 有 份 额': shares,
            '当 前 市 值': current_value,
            '收 益 率 (%)': return_rate
        })
    return summary

def add_member(name):
    """V3 扩展：新增一条空资产成员"""
    name = name.strip()
    if not name:
        return False, "成员姓名不能为空"
        
    exist = db_get_member_by_name(name)
    if exist:
        return False, "该成员名称已存在"
        
    return db_add_member(name)

def update_member_name(member_id, new_name):
    """V3 扩展：修改成员名字"""
    new_name = new_name.strip()
    if not new_name:
        return False, "新姓名不能为空"
        
    exist = db_get_member_by_name_exclude_id(new_name, member_id)
    if exist:
        return False, "该名字已被其他成员占用"
        
    return db_update_member_name(member_id, new_name)

def update_assets_and_nav(hk, us, div, hr, asset_details=None):
    """
    资产录入更新逻辑
    1. 计算系统当前总市值
    2. 获取系统总份额
    3. 重新计算最新净值并入库记录
    4. 如提供 asset_details 列表则一并入库
    """
    nav_record = get_latest_nav()
    if not nav_record:
        return False, "缺失初始净值记录，无法更新"

    current_total_shares = float(nav_record['total_shares'])
    hk, us, div, hr = float(hk), float(us), float(div), float(hr)
    new_total_assets = round(hk + us + div + hr, 4)

    if current_total_shares <= 0:
        return False, "系统总份额错误，无法计算净值"

    new_nav = round(new_total_assets / current_total_shares, 4)

    ok, msg, snapshot_id = db_insert_assets_and_nav(hk, us, div, hr, new_total_assets, current_total_shares, new_nav)
    if ok and snapshot_id and asset_details:
        db_insert_asset_details(snapshot_id, asset_details)
    return ok, msg

def process_invest(member_id, amount):
    """
    定投核心逻辑：
    强制：必须先根据`最新单位净值`折算新增份额。
    更新：该人员份额，累积本金；并更新系统的总份额，连带提高系统的总资产池总量；产生一条transaction。
    """
    amount = float(amount)
    if amount <= 0:
        return False, "定投金额必须大于0"

    nav_record = get_latest_nav()
    if not nav_record:
        return False, "必须存在初始净值才能进行定投操作"

    latest_nav = float(nav_record['nav'])
    current_sys_assets = float(nav_record['total_assets'])
    current_sys_shares = float(nav_record['total_shares'])

    # 核心计算：新增份额 = 新增投入金额 / 最新单位净值
    new_shares = round(amount / latest_nav, 4)

    # 当人员注入资金，这笔钱作为“未分配现金”，使系统总资产等额放大。系统的当前净值保持不变
    new_sys_assets = round(current_sys_assets + amount, 4)
    new_sys_shares = round(current_sys_shares + new_shares, 4)

    return db_process_invest(member_id, amount, new_shares, new_sys_assets, new_sys_shares, latest_nav)

def get_nav_history_df():
    """读取历史净值构建 Pandas DataFrame，供图表绘制"""
    records = db_get_nav_history_all()
    if not records:
        return pd.DataFrame()
        
    df = pd.DataFrame(records)
    # 将 Supabase 返回的 UTC timestamp 转换为带时区的 pandas datetime
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    return df

def get_latest_assets_allocation():
    """获取最新一期填报的四大类资产配置，供饼图"""
    record = db_get_latest_assets_allocation()
    if record:
        return {
            "港股": float(record.get('hk', 0)),
            "美股": float(record.get('us', 0)),
            "红利": float(record.get('dividend', 0)),
            "高风险": float(record.get('high_risk', 0))
        }
    return {}

def get_latest_asset_details():
    """获取最近一次快照的所有持仓明细，供数据总览展示"""
    return db_get_latest_asset_details()

def rollback_last_action():
    """
    撤销系统的最后一笔业务操作
    """
    return db_rollback_last_action()
