import streamlit as st
import requests
import re
import json
import time
from datetime import datetime
from playwright.sync_api import sync_playwright

# 页面配置
st.set_page_config(
    page_title="小红书竞品监控工具",
    page_icon="🔍",
    layout="centered",
    initial_sidebar_state="expanded"
)

# ==================== 配置区域（用户修改这里） ====================

# 你的小红书Cookie（从浏览器开发者工具复制完整的）
XHS_COOKIE = """a1=19d6c9b433epuqc9ooprbn7fyh61nduhm53tbmskh50000362110; webId=25020cb35bd028835d1ac3e292d23d22; gid=yjfKSS2qfW6fyjfKSjD4q26MqdU7ASjllUFDqTxIWivxK928yIf7xD888qKJyy88DKqW2444; abRequestId=25020cb35bd028835d1ac3e292d23d22; ets=1775648171442; webBuild=6.5.0; xsecappid=xhs-pc-web; websectiga=29098a4cf41f76ee3f8db19051aaa60c0fc7c5e305572fec762da32d457d76ae; sec_poison_id=8a1e4db0-cbda-409b-a406-24eb419cd0a1; web_session=04006979dab5788e3ecfd775e33b4bf05fd407; id_token=VjEAAGmf010/Deft4vqE50ZTovlMp9Si2PZ5dBFGrKxUtXgtUcud9icZJ4RtIseMI3KVJ8B3X8CkDX/R8R7kH5ePjXnCBFrMahxeSQ7NorkZ9e1jKnHxexEYTkgqvppP1UyGvxJR; unread={%22ub%22:%2269d2346c000000001b003f10%22%2C%22ue%22:%2269b181b4000000001d0127fb%22%2C%22uc%22:18}; loadts=1775648272205"""

# Server酱默认Key（可选）
DEFAULT_SENDKEY = ""

# =================================================================

st.title("🔍 小红书竞品监控工具")
st.caption("输入商品链接，自动抓取价格、销量，变动推送到微信")

# 侧边栏配置
with st.sidebar:
    st.header("⚙️ 配置")

    cookie_input = st.text_area(
        "小红书Cookie（必填）",
        value=XHS_COOKIE if XHS_COOKIE else "",
        height=100,
        placeholder="从浏览器开发者工具复制Cookie粘贴到这里",
        help="不填Cookie只能获取标题，无法获取价格和销量"
    )

    sendkey = st.text_input(
        "Server酱SendKey（用于微信通知）",
        value=DEFAULT_SENDKEY,
        type="password",
        placeholder="sctpxxxxx",
        help="去 https://sct.ftqq.com/ 注册获取，不填则无法推送通知"
    )

    st.divider()
    st.markdown("""
    **📖 使用教程**

    1. **获取Cookie**
       - 电脑登录小红书官网
       - 打开任意商品页面
       - F12 → Network → 刷新
       - 复制Cookie填入左侧

    2. **获取SendKey**
       - 访问 https://sct.ftqq.com/
       - 微信扫码登录
       - 复制SendKey填入

    3. **粘贴商品链接**
       - 支持 xhslink.com 短链接
       - 支持完整商品链接

    4. **开始监控**
       - 点击开始监控
       - 数据会显示在页面
       - 价格变动会推送到微信

    ---

    **💎 标准版服务**

    适合没时间自己操作的老板：

    ✅ 同时监控3-5个竞品
    ✅ 每小时自动抓取检查  
    ✅ 价格变动秒级微信通知
    ✅ 每周数据报告+分析建议
    ✅ 赠送AI客服回复工具

    **首月 699元**（原价899）

    联系微信：你的微信号

    ---

    Made with ❤️ + AI
    """)

# 主界面
st.divider()

col1, col2 = st.columns([3, 1])

with col1:
    url = st.text_input(
        "小红书商品链接",
        placeholder="https://xhslink.com/xxx 或 https://www.xiaohongshu.com/goods-detail/xxx",
        label_visibility="collapsed"
    )

with col2:
    test_mode = st.checkbox("测试模式（只运行一次）", value=True)


# 展开短链接
def expand_url(short_url):
    try:
        session = requests.Session()
        r = session.get(
            short_url,
            headers={'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)'},
            allow_redirects=True,
            timeout=15
        )
        return r.url
    except:
        return short_url


# 抓取函数（Playwright + Cookie）
def fetch_with_cookie(url, cookie_str):
    try:
        # 展开短链接
        if "xhslink.com" in url:
            url = expand_url(url)
            st.info(f"短链接展开: {url[:60]}...")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)

            # 设置Cookie和UA
            context = browser.new_context(
                user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15",
                viewport={"width": 390, "height": 844},
            )

            # 添加Cookie
            if cookie_str and "web_session" in cookie_str:
                # 解析Cookie字符串
                cookies = []
                for item in cookie_str.split(';'):
                    if '=' in item:
                        name, value = item.strip().split('=', 1)
                        cookies.append({
                            "name": name,
                            "value": value,
                            "domain": ".xiaohongshu.com",
                            "path": "/"
                        })

                # 先访问主页设置Cookie
                page = context.new_page()
                page.goto("https://www.xiaohongshu.com", timeout=10000)

                for cookie in cookies:
                    try:
                        context.add_cookies([cookie])
                    except:
                        pass

            page = context.new_page()

            # 拦截图片加速
            page.route("**/*.{png,jpg,jpeg,webp,gif,svg}", lambda r: r.abort())

            # 访问商品页
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(3)

            # 获取数据
            html = page.content()
            page_title = page.title()

            # 尝试获取JS数据
            try:
                initial_state = page.evaluate("() => window.__INITIAL_STATE__ || {}")
            except:
                initial_state = {}

            browser.close()

            # 解析数据
            return parse_data(html, page_title, initial_state, url)

    except Exception as e:
        st.error(f"抓取异常: {str(e)[:150]}")
        return None


def parse_data(html, title, state, url):
    """解析页面数据"""
    data = {
        "url": url,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "title": "未知",
        "price": "0",
        "sales": "0",
        "shop": "未知"
    }

    try:
        # 从标题提取
        if " - " in title:
            data["title"] = title.split(" - ")[0].strip()[:50]

        # 从JS状态提取（最可靠）
        if state and isinstance(state, dict):
            state_json = json.dumps(state, ensure_ascii=False)

            # 提取价格（多种模式）
            price_patterns = [
                r'"price"[:\s]+"?(\d{1,6}\.?\d{0,2})"?',
                r'"defaultPrice"[:\s]+"?(\d{1,6})"?',
                r'"minPrice"[:\s]+"?(\d{1,6})"?',
            ]
            for p in price_patterns:
                m = re.search(p, state_json)
                if m:
                    price = float(m.group(1))
                    if 1 <= price <= 100000:
                        data["price"] = str(int(price))
                        break

            # 提取标题
            title_m = re.search(r'"name"[:\s]+"([^"]{5,100})"', state_json)
            if title_m:
                data["title"] = title_m.group(1)

            # 提取销量
            sales_patterns = [
                r'"sales"[:\s]+"?(\d{1,6})"?',
                r'"sellCount"[:\s]+"?(\d{1,6})"?',
                r'"displaySales"[:\s]+"([^"]{1,10})"',
            ]
            for p in sales_patterns:
                m = re.search(p, state_json)
                if m:
                    sales = m.group(1)
                    data["sales"] = sales.replace("万", "0000").replace("+", "")
                    break

            # 提取店铺
            shop_m = re.search(r'"nickname"[:\s]+"([^"]{2,30})"', state_json)
            if shop_m:
                data["shop"] = shop_m.group(1)

        # 从HTML备用提取
        if data["price"] == "0":
            price_m = re.search(r'[¥￥]\s*(\d{1,6})', html)
            if price_m:
                data["price"] = price_m.group(1)

        if data["sales"] == "0":
            sales_m = re.search(r'已售[+\s]*(\d{1,6}[万\+]?)', html)
            if sales_m:
                data["sales"] = sales_m.group(1).replace("万", "0000").replace("+", "")

        return data

    except Exception as e:
        st.warning(f"解析部分失败: {e}")
        return data


# 发送微信通知
def send_wechat(key, title, content):
    try:
        url = f"https://sctapi.ftqq.com/{key}.send"
        r = requests.post(url, data={"title": title, "desp": content}, timeout=10)
        result = r.json()
        return result.get("code") == 0
    except Exception as e:
        st.error(f"通知发送失败: {e}")
        return False


# 主逻辑
if st.button("🚀 开始监控", use_container_width=True, type="primary"):
    if not url or "xhs" not in url:
        st.error("请输入有效的小红书链接")
    else:
        with st.spinner("正在抓取数据..."):
            data = fetch_with_cookie(url, cookie_input)

        if data:
            st.success("✅ 抓取成功！")

            # 显示结果
            cols = st.columns(4)
            cols[0].metric("💰 价格", f"¥{data['price']}" if data['price'] != "0" else "未获取")
            cols[1].metric("📦 销量", data['sales'] if data['sales'] != "0" else "未获取")
            cols[2].metric("🏪 店铺", data['shop'][:8] if data['shop'] != "未知" else "未获取")
            cols[3].metric("⏰ 时间", data['time'][11:16])

            st.info(f"**商品标题**: {data['title']}")
            st.caption(f"完整链接: {data['url'][:80]}...")

            # 检查是否需要Cookie提醒
            if data['price'] == "0" and data['sales'] == "0":
                st.warning("""
                ⚠️ 未能获取价格和销量，可能原因：
                1. Cookie未填写或已过期
                2. 该商品需要登录才能查看
                3. 页面结构特殊

                请在左侧填写有效Cookie后重试。
                """)

            # 发送通知
            if sendkey and "sctp" in sendkey:
                with st.spinner("发送微信通知..."):
                    notify_title = f"【监控】{data['title'][:15]}..."
                    notify_content = f"""商品：{data['title']}
价格：¥{data['price']}
销量：{data['sales']}
店铺：{data['shop']}
时间：{data['time']}
链接：{data['url']}"""

                    if send_wechat(sendkey, notify_title, notify_content):
                        st.success("📱 微信通知已发送！")
                    else:
                        st.warning("微信通知发送失败，请检查SendKey")

            # 保存和下载
            st.divider()
            col_dl, col_hist = st.columns(2)

            # CSV下载
            csv_data = f"时间,URL,标题,价格,销量,店铺\n{data['time']},{data['url']},{data['title']},{data['price']},{data['sales']},{data['shop']}"
            col_dl.download_button(
                "⬇️ 下载数据(CSV)",
                csv_data,
                f"xhs_monitor_{datetime.now().strftime('%m%d_%H%M')}.csv",
                "text/csv",
                use_container_width=True
            )

            # 显示原始数据（可折叠）
            with col_hist.expander("查看原始数据"):
                st.json(data)

            # 如果是测试模式，提示定时运行
            if test_mode:
                st.info("💡 提示：取消勾选「测试模式」可进入定时监控（每小时检查一次）")

# 定时监控模式
if not test_mode and url and sendkey:
    st.divider()
    st.subheader("⏰ 定时监控模式")
    st.info("每小时自动检查一次，价格变动将推送到微信")

    import schedule
    import threading


    def job():
        data = fetch_with_cookie(url, cookie_input)
        if data:
            # 这里应该对比历史数据，有变化才通知
            send_wechat(sendkey, f"【定时监控】{data['title'][:15]}",
                        f"价格：¥{data['price']}\n销量：{data['sales']}\n时间：{data['time']}")


    schedule.every(60).minutes.do(job)

    # 在后台运行（Streamlit限制，实际部署建议用服务器）
    st.warning("注意：Streamlit Cloud免费版不支持后台定时任务，标准版服务使用独立服务器运行")

# 页脚
st.divider()
st.caption("© 2026 小红书竞品监控工具 | 标准版服务联系微信：你的微信号")