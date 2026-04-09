#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小红书商品竞品监控工具 v2 - 最终稳定版（本地+云端双通）
完全基于用户修复后的原版代码，仅新增适配，不修改原有核心逻辑
"""

import os
import csv
import json
import re
import time
import requests
from datetime import datetime, timezone, timedelta
import streamlit as st

# ==================== 自动刷新兼容处理 ====================
try:
    from streamlit_autorefresh import st_autorefresh
    AUTOREFRESH_AVAILABLE = True
except ImportError:
    AUTOREFRESH_AVAILABLE = False
    st_autorefresh = None

# ==================== 原版核心代码（100%保留，仅优化抓取逻辑） ====================
def get_beijing_time():
    utc = datetime.now(timezone.utc)
    beijing = utc + timedelta(hours=8)
    return beijing.strftime("%Y-%m-%d %H:%M:%S")

# 🔧 优化版fetch_data：解决抓取失败、反爬、云端运行问题
def fetch_data(url):
    print(f"[{get_beijing_time()}] 正在抓取: {url[:60]}...")
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            # 云端兼容启动参数
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--no-zygote"
                ]
            )
            # 强化UA，绕过反爬
            context = browser.new_context(
                user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
                viewport={"width": 390, "height": 844},
                locale="zh-CN",
                timezone_id="Asia/Shanghai"
            )
            page = context.new_page()
            # 拦截图片，加速加载
            page.route("**/*.{png,jpg,jpeg,webp,gif,svg,ico}", lambda r: r.abort())
            # 增加超时，处理短链接跳转
            page.goto(url, wait_until="networkidle", timeout=60000)
            # 延长等待，确保数据加载完成
            time.sleep(6)
            
            # 重试机制：如果页面未加载，等待后重试
            try:
                page.wait_for_selector("body", timeout=10000)
            except:
                time.sleep(3)
                page.wait_for_selector("body", timeout=10000)

            html = page.content()
            try:
                js_data = page.evaluate("""() => {
                    return {
                        initial: window.__INITIAL_STATE__ || {},
                        ssr: window._SSR_HYDRATED_DATA || {},
                        goods: window.goodsDetail || {},
                        data: window.__data || {}
                    };
                }""")
            except:
                js_data = {}
            try:
                visible_text = page.evaluate("() => document.body.innerText")
            except:
                visible_text = ""
            browser.close()
            return parse_data_v2(html, js_data, visible_text, url)
    except Exception as e:
        print(f"  ✗ 抓取异常: {str(e)[:200]}")
        return None

def parse_data_v2(html, js_data, visible_text, url):
    result = {
        "url": url,
        "fetch_time": get_beijing_time(),
        "title": "未知",
        "price": "0",
        "original_price": "0",
        "sales": "0",
        "sales_display": "",
        "shop": "未知",
        "coupon": "0",
        "final_price": "0"
    }
    try:
        all_text = html + visible_text
        for source in js_data.values():
            if isinstance(source, dict):
                try:
                    all_text += json.dumps(source, ensure_ascii=False)
                except:
                    pass

        deal_match = re.search(r'到手价[¥￥\s]*(\d+\.?\d*)', all_text)
        if deal_match:
            result["price"] = deal_match.group(1)
            print(f"  💰 到手价: ¥{result['price']}")

        if result["price"] == "0":
            deal_api = re.search(r'"dealPrice"[^{}]*"price"[:\s]*(\d+\.?\d*)', all_text)
            if deal_api:
                price = float(deal_api.group(1))
                if price > 100 and price == int(price):
                    price /= 100
                result["price"] = str(price)
                print(f"  💰 到手价(API): ¥{result['price']}")

        if result["price"] == "0":
            highlight = re.search(r'"highlightPrice"[:\s]*(\d+\.?\d*)', all_text)
            if highlight:
                val = float(highlight.group(1))
                if val > 100:
                    val /= 100
                result["original_price"] = str(val)
            all_prices = re.findall(r'[¥￥](sslocal://flow/file_open?url=%5Cd%2B%5C.%3F%5Cd%2A&flow_extra=eyJsaW5rX3R5cGUiOiJjb2RlX2ludGVycHJldGVyIn0=)', all_text)
            valid_prices = []
            for p in all_prices:
                try:
                    val = float(p)
                    if 1 <= val <= 10000:
                        valid_prices.append(val)
                except:
                    pass
            if valid_prices:
                min_price = min(valid_prices)
                result["price"] = str(min_price)
                print(f"  💰 到手价(最小候选): ¥{result['price']}")

        if result["original_price"] == "0":
            highlight = re.search(r'"highlightPrice"[:\s]*(\d+\.?\d*)', all_text)
            if highlight:
                val = float(highlight.group(1))
                if val > 100:
                    val /= 100
                result["original_price"] = str(val)
            else:
                try:
                    current = float(result["price"])
                except:
                    current = 0
                all_prices = re.findall(r'[¥￥](sslocal://flow/file_open?url=%5Cd%2B%5C.%3F%5Cd%2A&flow_extra=eyJsaW5rX3R5cGUiOiJjb2RlX2ludGVycHJldGVyIn0=)', all_text)
                for p in all_prices:
                    try:
                        val = float(p)
                        if val > current:
                            result["original_price"] = str(val)
                            break
                    except:
                        pass

        desc_match = re.search(r'"descriptionH5"[^{}]*"name"[:\s]*"([^"]{10,200})"', all_text)
        if desc_match:
            result["title"] = desc_match.group(1)
            print(f"  📌 标题(desc): {result['title'][:40]}...")
        else:
            main_match = re.search(r'"descriptionMain"[^{}]*"name"[:\s]*"([^"]{10,200})"', all_text)
            if main_match:
                result["title"] = main_match.group(1)
                print(f"  📌 标题(main): {result['title'][:40]}...")
            else:
                title_tag = re.search(r'<title>([^<]{10,200})</title>', html)
                if title_tag:
                    title = title_tag.group(1)
                    title = re.sub(r'\s*-\s*小红书$', '', title)
                    result["title"] = title
                    print(f"  📌 标题(tag): {result['title'][:40]}...")
                else:
                    lines = [l.strip() for l in visible_text.split('\n') if len(l.strip()) > 20]
                    if lines:
                        result["title"] = max(lines, key=len)[:100]
                        print(f"  📌 标题(text): {result['title'][:40]}...")

        seller_match = re.search(r'"sellerH5"[^{}]*"name"[:\s]*"([^"]{2,80})"', all_text)
        if seller_match:
            shop = seller_match.group(1)
            promo_words = ['满', '减', '折', '券', '包邮', '赠', '元', '到手', '立减']
            if not any(w in shop for w in promo_words):
                result["shop"] = shop
                print(f"  🏪 店铺(seller): {result['shop']}")
        if result["shop"] == "未知":
            patterns = [
                r'"shopName"[:\s]*"([^"]{2,80})"',
                r'"storeName"[:\s]*"([^"]{2,80})"',
                r'"nickname"[:\s]*"([^"]{2,80})"',
                r'([^\s<]{2,30}(?:店|旗舰店|专营店|官旗))'
            ]
            for p in patterns:
                m = re.search(p, all_text)
                if m:
                    shop = m.group(1)
                    # 用户修复的清理代码 ↓↓↓ 完全保留
                    shop = re.sub(r'data-v-[a-f0-9]+="">', '', shop)
                    shop = re.sub(r'data-v-[a-f0-9]+', '', shop)
                    shop = shop.strip('">= ')
                    promo_words = ['满', '减', '折', '券', '包邮', '今日', '限时']
                    if not any(w in shop for w in promo_words) and len(shop) >= 2:
                        result["shop"] = shop
                        print(f"  🏪 店铺(pattern): {result['shop']}")
                        break

        sales_match = re.search(r'已售[+\s]*(\d+\.?\d*[万\+]?)', all_text)
        if sales_match:
            sales_str = sales_match.group(1)
            result["sales_display"] = sales_str
            num_match = re.search(r'(\d+\.?\d*)', sales_str)
            if num_match:
                num = float(num_match.group(1))
                if '万' in sales_str:
                    num *= 10000
                result["sales"] = str(int(num))
                print(f"  📊 销量: {sales_str} ({result['sales']})")

        coupon_amount = 0.0
        c1 = re.search(r'"coupon"[^{}]*"amount"[:\s]*(\d+\.?\d*)', all_text)
        if c1:
            try:
                coupon_amount = float(c1.group(1))
            except:
                coupon_amount = 0.0
        if coupon_amount == 0:
            m = re.search(r'(?:立减|立省|减|优惠券|券|抵扣)[^\d\n]{0,6}([¥￥]?)(\d+\.?\d*)', all_text)
            if m:
                try:
                    coupon_amount = float(m.group(2))
                except:
                    coupon_amount = 0.0
        if coupon_amount == 0:
            mm = re.search(r'满\s*\d+\s*减\s*(\d+\.?\d*)', all_text)
            if mm:
                try:
                    coupon_amount = float(mm.group(1))
                except:
                    coupon_amount = 0.0
        if coupon_amount == 0:
            m2 = re.search(r'券[:：\s]*[¥￥]?\s*(\d+\.?\d*)', all_text)
            if m2:
                try:
                    coupon_amount = float(m2.group(2))
                except:
                    coupon_amount = 0.0

        result["coupon"] = str(coupon_amount)

        try:
            base_price = float(result["price"])
        except:
            base_price = 0.0
        final = base_price
        if coupon_amount > 0:
            final = base_price - coupon_amount
        else:
            final = base_price - 8.8
        if final < 0:
            final = 0.0
        result["final_price"] = f"{final:.2f}"

        if base_price == 0:
            print(f"  ⚠️ 未能获取有效到手价")
            return None

        print(f"  ✅ 成功: {result['title'][:30]}... 到手价:{result['price']} 券:{result['coupon']} 最终:{result['final_price']}")
        return result

    except Exception as e:
        print(f"  ✗ 解析异常: {str(e)[:200]}")
        return None

def save_data(data):
    try:
        exists = os.path.exists("price_history.csv")
        with open("price_history.csv", "a", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            if not exists:
                writer.writerow(["时间", "URL", "标题", "到手价", "原价", "券", "最终价", "销量", "销量显示", "店铺"])
            writer.writerow([
                data["fetch_time"], data["url"], data["title"],
                data.get("price", "0"), data.get("original_price", "0"),
                data.get("coupon", "0"), data.get("final_price", "0"),
                data.get("sales", "0"), data.get("sales_display", ""),
                data.get("shop", "未知")
            ])
        return True
    except Exception as e:
        print(f"  ✗ 保存失败: {e}")
        return False

def check_change(data, url):
    if not os.path.exists("price_history.csv"):
        return None, None

    try:
        last_record = None
        with open("price_history.csv", "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row["URL"] == url:
                    last_record = row

        if not last_record:
            return None, None

        changes = []
        old_price = 0.0
        old_sales = 0

        try:
            current_price = float(data.get("final_price", data.get("price", "0")))
            last_price = float(last_record.get("最终价", last_record.get("到手价", "0")))
            old_price = last_price
            if abs(current_price - last_price) >= 0.01:
                diff = current_price - last_price
                if diff < 0:
                    changes.append(f"降价{abs(diff):.2f}元")
                else:
                    changes.append(f"涨价{diff:.2f}元")
        except:
            pass

        try:
            current_sales = int(data.get("sales", "0"))
            last_sales = int(last_record.get("销量", "0"))
            old_sales = last_sales
            if current_sales != last_sales:
                diff = current_sales - last_sales
                if diff > 0:
                    changes.append(f"销量+{diff}")
                else:
                    changes.append(f"销量{diff}")
        except:
            pass

        change_str = "，".join(changes) if changes else None
        return change_str, (old_price, old_sales)

    except Exception as e:
        print(f"  ✗ 对比失败: {e}")
        return None, None

def send_notify(SERVERCHAN_KEY, title, content):
    if not SERVERCHAN_KEY or len(SERVERCHAN_KEY) < 20:
        print("  ⚠️ SendKey无效或未配置")
        return False

    try:
        api_url = f"https://sc3.ft07.com/send/{SERVERCHAN_KEY}.send"
        data = {"title": title, "desp": content}
        resp = requests.post(api_url, data=data, timeout=10)
        result = resp.json()
        return result.get("code") == 0
    except Exception as e:
        print(f"  ❌ 通知异常：{str(e)[:80]}")
        return False

def monitor_single(SERVERCHAN_KEY, item):
    name = item.get("name", "商品")
    url = item["url"]
    data = fetch_data(url)
    if not data:
        return None, f"❌ {name} 抓取失败", None, None

    save_data(data)
    change_info, old_values = check_change(data, url)

    if change_info:
        title = f"【{change_info}】{data['title'][:15]}..."
        content = f"""📦 商品：{data['title']}
💰 价格变动：{old_values[0]}元 → {data['final_price']}元
（到手价：{data.get('price','0')}元，券：{data.get('coupon','0')}元）
📊 销量：{data.get('sales_display', data['sales'])}
🏪 店铺：{data['shop']}
⏰ 时间：{data['fetch_time']}"""
        send_notify(SERVERCHAN_KEY, title, content)
        msg = f"✅ {data['title'][:25]} | 💰{data['final_price']}元 | {change_info}"
    elif old_values is None:
        title = f"【监控启动】{data['title'][:20]}..."
        content = f"""📦 开始监控：{data['title']}
💰 最终价：{data['final_price']}元
（到手价：{data.get('price','0')}元，券：{data.get('coupon','0')}元）
🏷️ 原价：{data.get('original_price','无')}
📊 销量：{data.get('sales_display', data['sales'])}
🏪 店铺：{data['shop']}
⏰ {data['fetch_time']}"""
        send_notify(SERVERCHAN_KEY, title, content)
        msg = f"✅ {data['title'][:25]} | 💰{data['final_price']}元 | 监控已启动"
    else:
        msg = f"✅ {data['title'][:25]} | 💰{data['final_price']}元 | 无变化"

    return data, msg, change_info, old_values

# ==================== Streamlit 网页层（仅新增，不修改原逻辑） ====================
st.set_page_config(page_title="小红书竞品监控", layout="wide", initial_sidebar_state="collapsed")
st.title("📱 小红书商品竞品监控工具 v2")

if "monitor_list" not in st.session_state:
    st.session_state.monitor_list = []
if "last_run_time" not in st.session_state:
    st.session_state.last_run_time = "未执行"
if "monitor_logs" not in st.session_state:
    st.session_state.monitor_logs = []

st.subheader("🔔 微信推送设置（ServerChan）")
serverchan_key = st.text_input(
    "请输入你的ServerChan SendKey",
    placeholder="sct-xxxxxxxxxxxxxxxxxxxxxxxx",
    type="password"
)
with st.expander("📖 如何获取SendKey？（点击展开）"):
    st.markdown("""
1.  打开官网：[https://sc3.ft07.com/](sslocal://flow/file_open?url=https%3A%2F%2Fsc3.ft07.com%2F&flow_extra=eyJsaW5rX3R5cGUiOiJjb2RlX2ludGVycHJldGVyIn0=)
2.  微信扫码登录，关注「Server酱」公众号
3.  进入「SendKey」页面，复制你的专属SendKey
4.  粘贴到上方输入框，即可开启微信降价通知
    """)

st.subheader("🛒 添加监控商品")
links_input = st.text_area(
    "粘贴小红书商品链接（一行一个，自动补全https）",
    height=120,
    placeholder="https://xhslink.com/xxxx\nhttps://xhslink.com/yyyy"
)
check_interval = st.number_input("⏱ 监控间隔（分钟）", min_value=1, max_value=60, value=5, step=1)

if st.button("📥 加载商品列表"):
    if not links_input.strip():
        st.warning("⚠️ 请至少输入一个商品链接")
    else:
        links = []
        for line in links_input.split("\n"):
            line = line.strip()
            if not line:
                continue
            if not line.startswith("http"):
                line = "https://" + line
            elif line.startswith("http://"):
                line = line.replace("http://", "https://")
            links.append(line)

        links = list(dict.fromkeys(links))
        st.session_state.monitor_list = [{"name": f"商品{i+1}", "url": l} for i, l in enumerate(links)]
        st.success(f"✅ 已加载 {len(st.session_state.monitor_list)} 个商品")

if st.session_state.monitor_list:
    st.info(f"当前监控商品数：{len(st.session_state.monitor_list)}")
    with st.expander("查看商品列表"):
        for item in st.session_state.monitor_list:
            st.write(f"- {item['name']}：{item['url']}")

st.subheader("📊 实时监控结果")
log_container = st.empty()
status_container = st.empty()

if AUTOREFRESH_AVAILABLE:
    st_autorefresh(interval=30 * 1000, key="monitor_refresh", limit=None)
else:
    st.info("ℹ️ 自动刷新组件未安装，页面不会自动刷新，请手动点击「立即执行一次监控」或刷新页面")

def run_monitor_task():
    if not st.session_state.monitor_list:
        return
    if not serverchan_key:
        st.warning("⚠️ 请先填写SendKey，否则无法发送通知")
        return

    logs = []
    for item in st.session_state.monitor_list:
        data, msg, change, old = monitor_single(serverchan_key, item)
        logs.append(msg)
        time.sleep(3)

    st.session_state.monitor_logs = logs
    st.session_state.last_run_time = get_beijing_time()

if st.button("▶ 立即执行一次监控"):
    run_monitor_task()

if AUTOREFRESH_AVAILABLE and st.session_state.last_run_time != "未执行":
    try:
        last_run = datetime.strptime(st.session_state.last_run_time, "%Y-%m-%d %H:%M:%S")
        now = datetime.strptime(get_beijing_time(), "%Y-%m-%d %H:%M:%S")
        diff_minutes = (now - last_run).total_seconds() / 60
        if diff_minutes >= check_interval:
            run_monitor_task()
    except:
        pass

if st.session_state.monitor_logs:
    log_container.markdown("\n".join([f"- {log}" for log in st.session_state.monitor_logs]))
    status_container.success(f"✅ 上次执行时间：{st.session_state.last_run_time} | 下次执行：{check_interval}分钟后")
else:
    log_container.info("ℹ️ 等待首次监控执行...")

st.subheader("📜 历史价格记录")
if os.path.exists("price_history.csv"):
    import pandas as pd
    df = pd.read_csv("price_history.csv", encoding="utf-8-sig")
    st.dataframe(df, use_container_width=True)
else:
    st.info("ℹ️ 暂无历史数据，执行一次监控后生成")
