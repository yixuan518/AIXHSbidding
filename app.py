#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小红书商品竞品监控工具 v2 - 网页版（Streamlit）
基于你修复后的原版代码，只新增，不修改原有逻辑
"""

import os
import csv
import json
import re
import time
import schedule
import requests
from datetime import datetime, timezone, timedelta
import streamlit as st

# ==================== 原版代码全部保留（你修复后的版本） ====================
def get_beijing_time():
    utc = datetime.now(timezone.utc)
    beijing = utc + timedelta(hours=8)
    return beijing.strftime("%Y-%m-%d %H:%M:%S")

def fetch_data(url):
    print(f"[{get_beijing_time()}] 正在抓取: {url[:60]}...")
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15",
                viewport={"width": 390, "height": 844},
            )
            page = context.new_page()
            page.route("**/*.{png,jpg,jpeg,webp,gif}", lambda r: r.abort())
            page.goto(url, wait_until="networkidle", timeout=30000)
            time.sleep(4)
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
        print(f"  ✗ 抓取异常: {str(e)[:100]}")
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
            all_prices = re.findall(r'[¥￥](\d+\.?\d*)', all_text)
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
                all_prices = re.findall(r'[¥￥](\d+\.?\d*)', all_text)
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
                    # 你修复的清理代码 ↓↓↓ 完全保留
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
    if not SERVERCHAN_KEY:
        return False

    try:
        api_url = f"https://sctapi.ftqq.com/{SERVERCHAN_KEY}.send"
        data = {"title": title, "desp": content}
        resp = requests.post(api_url, data=data, timeout=10)
        result = resp.json()
        return result.get("code") == 0
    except:
        return False

def monitor_single(SERVERCHAN_KEY, item):
    name = item.get("name", "商品")
    url = item["url"]
    data = fetch_data(url)
    if not data:
        return None

    save_data(data)
    change_info, old_values = check_change(data, url)
    return data, change_info, old_values

# ==================== 以下是新增的网页版功能 ====================
st.set_page_config(page_title="小红书竞品监控", layout="wide")
st.title("📱 小红书商品竞品监控工具")

# 说明
st.markdown("""
### 📌 使用说明
1. 填写微信推送 **SendKey**
2. 粘贴小红书商品链接（一行一个）
3. 点击开始监控
4. 降价/涨价自动微信提醒
""")

# SendKey 设置
st.subheader("🔔 微信推送设置")
SERVERCHAN_KEY = st.text_input("ServerChan SendKey", placeholder="sctpxxxxxxxxxxxx")
with st.expander("📖 如何获取 SendKey？"):
    st.markdown("""
1. 打开官网：https://sc3.ft07.com/
2. 微信扫码登录
3. 复制 **SendKey**
4. 粘贴到上方输入框即可使用
""")

# 商品链接输入
st.subheader("🛒 添加监控商品")
links_input = st.text_area("粘贴小红书商品链接（一行一个）", height=120, placeholder="https://xhslink.com/xxxx\nhttps://xhslink.com/yyyy")

# 监控间隔
check_interval = st.number_input("⏱ 监控间隔（分钟）", min_value=1, value=5)

# 历史记录
st.subheader("📊 实时监控结果")
log_area = st.empty()

# 开始监控
if st.button("▶ 开始监控"):
    if not SERVERCHAN_KEY:
        st.warning("请先填写 SendKey")
    elif not links_input.strip():
        st.warning("请至少输入一个商品链接")
    else:
        links = [l.strip() for l in links_input.split("\n") if l.strip()]
        monitor_list = [{"name": f"商品{i+1}", "url": l} for i, l in enumerate(links)]
        st.success(f"已加载 {len(monitor_list)} 个商品，开始监控...")

        last_results = []

        def run_web_monitor():
            logs = []
            for item in monitor_list:
                res = monitor_single(SERVERCHAN_KEY, item)
                if res:
                    data, change, old = res
                    logs.append(f"✅ {data['title'][:25]} | 💰{data['final_price']}元 | 🏪{data['shop']}")
                    if change:
                        send_notify(SERVERCHAN_KEY, f"【{change}】{data['title'][:15]}", f"商品：{data['title']}\n价格：{old[0]} → {data['final_price']}")
                time.sleep(2)

            log_area.markdown("\n".join(logs))

        # 首次执行
        run_web_monitor()

        # 定时
        schedule.every(check_interval).minutes.do(run_web_monitor)

        while True:
            schedule.run_pending()
            time.sleep(1)
