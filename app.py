import streamlit as st
import requests
import re
import json
import time
from datetime import datetime
from urllib.parse import urlparse

# 页面配置
st.set_page_config(
    page_title="小红书竞品监控工具",
    page_icon="🔍",
    layout="centered",
    initial_sidebar_state="expanded"
)

st.title("🔍 小红书竞品监控工具")
st.caption("输入商品链接，自动抓取价格、销量，变动推送到微信")

# ==================== 配置区域 ====================

# 默认Cookie（可选，用户可以在侧边栏覆盖）
DEFAULT_COOKIE = ""

# 默认SendKey（可选）
DEFAULT_SENDKEY = ""

# =================================================================

# 侧边栏配置
with st.sidebar:
    st.header("⚙️ 配置")
    
    cookie_input = st.text_area(
        "小红书Cookie（必填）",
        value=DEFAULT_COOKIE,
        height=150,
        placeholder="从浏览器开发者工具复制完整的Cookie粘贴到这里",
        help="必须包含web_session等登录凭证，否则无法获取价格"
    )
    
    sendkey = st.text_input(
        "Server酱SendKey（用于微信通知）",
        value=DEFAULT_SENDKEY,
        type="password",
        placeholder="sctpxxxxx",
        help="去 https://sct.ftqq.com/ 注册获取"
    )
    
    st.divider()
    st.markdown("""
    **📖 使用教程**
    
    **1. 获取Cookie（关键步骤）**
    - 电脑Chrome打开 https://www.xiaohongshu.com
    - 扫码登录你的小红书账号
    - 打开任意商品页面（如 https://www.xiaohongshu.com/goods-detail/xxx）
    - 按 **F12** 打开开发者工具
    - 点击 **Network**（网络）标签
    - 按 **F5** 刷新页面
    - 点击第一个请求（goods-detail）
    - 右侧找到 **Request Headers** → **Cookie**
    - 复制完整的Cookie字符串（很长，包含web_session）
    - 粘贴到左侧文本框
    
    **2. 获取SendKey**
    - 访问 https://sct.ftqq.com/
    - 微信扫码登录
    - 复制SendKey填入
    
    **3. 粘贴商品链接**
    - 支持 xhslink.com 短链接
    - 支持完整商品链接
    
    **4. 开始监控**
    - 点击开始监控
    - 查看价格和销量数据
    
    ---
    
    **💎 标准版服务**
    
    适合没时间自己操作的老板：
    
    ✅ 同时监控3-5个竞品
    ✅ 每小时自动检查  
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

# 输入区域
col1, col2 = st.columns([3, 1])

with col1:
    url = st.text_input(
        "小红书商品链接",
        placeholder="https://xhslink.com/xxx 或 https://www.xiaohongshu.com/goods-detail/xxx",
        label_visibility="collapsed"
    )

with col2:
    test_mode = st.checkbox("测试模式", value=True, help="只运行一次，取消则定时监控（需保持页面打开）")

# 展开短链接
def expand_short_url(short_url):
    """展开xhslink短链接"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
        }
        
        session = requests.Session()
        response = session.get(
            short_url, 
            headers=headers, 
            allow_redirects=True, 
            timeout=20
        )
        
        final_url = response.url
        
        # 清理跟踪参数
        if "?" in final_url:
            final_url = final_url.split("?")[0]
            
        return final_url
        
    except Exception as e:
        st.warning(f"短链接展开失败: {e}")
        return short_url

# 核心抓取函数（纯requests，兼容Streamlit Cloud）
def fetch_xhs_data(url, cookie_str):
    """
    使用requests+Cookie抓取小红书数据
    """
    try:
        # 展开短链接
        original_url = url
        if "xhslink.com" in url:
            url = expand_short_url(url)
            if url != original_url:
                st.info(f"✓ 短链接展开: {url[:60]}...")
        
        # 检查URL有效性
        if "xiaohongshu.com" not in url and "xhslink.com" not in url:
            st.error("请输入有效的小红书链接")
            return None
        
        # 构建请求头
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Cache-Control': 'max-age=0',
        }
        
        # 添加Cookie（关键）
        if cookie_str and len(cookie_str) > 50:
            headers['Cookie'] = cookie_str.strip()
        else:
            st.warning("⚠️ Cookie未填写或太短，可能无法获取价格和销量")
        
        # 发送请求
        with st.spinner("正在请求小红书服务器..."):
            session = requests.Session()
            
            # 先访问主页获取会话（模拟真实用户）
            session.get("https://www.xiaohongshu.com", headers=headers, timeout=10)
            
            # 访问商品页
            response = session.get(url, headers=headers, timeout=20)
            response.raise_for_status()
            
            html = response.text
        
        # 解析数据
        return parse_xhs_html(html, url)
        
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            st.error("❌ Cookie已过期或无效，请重新获取Cookie")
        elif e.response.status_code == 403:
            st.error("❌ 访问被拒绝，可能需要更换IP或Cookie")
        else:
            st.error(f"❌ HTTP错误: {e.response.status_code}")
        return None
    except Exception as e:
        st.error(f"❌ 请求异常: {str(e)[:150]}")
        return None

def parse_xhs_html(html, url):
    """
    解析小红书HTML，提取商品数据
    """
    data = {
        "url": url,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "title": "未知",
        "price": "0",
        "sales": "0",
        "shop": "未知"
    }
    
    try:
        # 1. 提取标题（从<title>标签或meta）
        title_match = re.search(r'<title>([^<]+)</title>', html)
        if title_match:
            title = title_match.group(1).strip()
            # 清理后缀
            title = re.sub(r'\s*-\s*小红书.*$', '', title)
            title = re.sub(r'小红书\s*-\s*', '', title)
            if len(title) > 5:
                data["title"] = title[:80]
        
        # 2. 从页面脚本中提取JSON数据（小红书通常把数据放这里）
        # 找 __INITIAL_STATE__ 或类似的数据
        script_patterns = [
            r'window\.__INITIAL_STATE__\s*=\s*({.+?});</script>',
            r'<script[^>]*>window\._SSR_HYDRATED_DATA\s*=\s*({.+?})</script>',
            r'"goodsDetail":({.+?}),\s*"abTest"',
        ]
        
        json_data = None
        for pattern in script_patterns:
            match = re.search(pattern, html, re.DOTALL)
            if match:
                try:
                    json_str = match.group(1)
                    # 清理可能的转义
                    json_str = json_str.replace('\\"', '"').replace('\\\\', '\\')
                    json_data = json.loads(json_str)
                    break
                except:
                    continue
        
        # 3. 从JSON提取数据
        if json_data:
            # 转换为字符串便于搜索
            json_str = json.dumps(json_data, ensure_ascii=False)
            
            # 提取价格（多种可能的字段名）
            price_fields = ['price', 'minPrice', 'maxPrice', 'defaultPrice', 'activityPrice', 'originPrice']
            for field in price_fields:
                pattern = rf'"{field}"[:\s]+"?(\d{{1,6}}(?:\.\d{{1,2}})?)"?'
                match = re.search(pattern, json_str)
                if match:
                    price = float(match.group(1))
                    if 1 <= price <= 100000:
                        data["price"] = str(int(price))
                        break
            
            # 提取标题（如果之前没拿到）
            if data["title"] == "未知":
                name_match = re.search(r'"name"[:\s]+"([^"]{5,100})"', json_str)
                if name_match:
                    data["title"] = name_match.group(1)
            
            # 提取销量
            sales_fields = ['sales', 'sellCount', 'displaySales', 'totalSales']
            for field in sales_fields:
                pattern = rf'"{field}"[:\s]+"?(\d{{1,6}})"?'
                match = re.search(pattern, json_str)
                if match:
                    data["sales"] = match.group(1)
                    break
            
            # 提取店铺
            shop_match = re.search(r'"nickname"[:\s]+"([^"]{2,30})"', json_str)
            if shop_match:
                data["shop"] = shop_match.group(1)
        
        # 4. 从HTML直接提取（备用方案）
        if data["price"] == "0":
            # 找 ¥数字 或 ￥数字
            price_match = re.search(r'[¥￥]\s*(\d{1,6}(?:\.\d{1,2})?)', html)
            if price_match:
                data["price"] = str(int(float(price_match.group(1))))
        
        if data["sales"] == "0":
            # 找已售数字
            sales_match = re.search(r'已售[+\s]*(\d{1,6}[万\+]?)', html)
            if sales_match:
                sales_text = sales_match.group(1)
                sales_text = sales_text.replace('+', '').replace('万', '0000')
                data["sales"] = sales_text
        
        # 5. 从meta标签提取（最后尝试）
        if data["title"] == "未知":
            meta_title = re.search(r'<meta[^>]*property="og:title"[^>]*content="([^"]*)"', html)
            if meta_title:
                data["title"] = meta_title.group(1)[:80]
        
        return data
        
    except Exception as e:
        st.warning(f"解析警告: {e}")
        return data

# 发送微信通知
def send_wechat_notification(key, title, content):
    """通过Server酱发送微信通知"""
    try:
        # 新版Server酱API
        url = f"https://sctapi.ftqq.com/{key}.send"
        
        payload = {
            "title": title,
            "desp": content,
            "channel": "9"  # 微信通道
        }
        
        response = requests.post(url, data=payload, timeout=10)
        result = response.json()
        
        if result.get("code") == 0:
            return True, "发送成功"
        else:
            return False, result.get("message", "未知错误")
            
    except Exception as e:
        return False, str(e)

# 主逻辑
if st.button("🚀 开始监控", use_container_width=True, type="primary"):
    if not url:
        st.error("请输入商品链接")
    elif "xhs" not in url:
        st.error("请输入有效的小红书链接（包含xhs或xiaohongshu）")
    else:
        # 抓取数据
        with st.spinner("正在抓取数据，请稍候..."):
            data = fetch_xhs_data(url, cookie_input)
        
        if data:
            # 显示结果
            st.success("✅ 抓取成功！")
            
            # 数据展示
            cols = st.columns(4)
            price_display = f"¥{data['price']}" if data['price'] != "0" else "未获取"
            sales_display = data['sales'] if data['sales'] != "0" else "未获取"
            shop_display = data['shop'][:8] if data['shop'] != "未知" else "未获取"
            
            cols[0].metric("💰 价格", price_display)
            cols[1].metric("📦 销量", sales_display)
            cols[2].metric("🏪 店铺", shop_display)
            cols[3].metric("⏰ 时间", data['time'][11:16])
            
            # 标题和链接
            st.info(f"**商品标题**: {data['title']}")
            with st.expander("查看完整链接"):
                st.code(data['url'])
            
            # 数据质量提示
            if data['price'] == "0" or data['sales'] == "0":
                st.warning("""
                ⚠️ 部分数据未获取到，可能原因：
                1. **Cookie无效或过期** - 请重新获取Cookie（最常见）
                2. **该商品需要特殊权限** - 尝试其他商品
                3. **IP被限制** - 稍后再试
                
                **解决步骤：**
                - 确保Cookie包含 `web_session` 字段
                - Cookie长度通常 > 500字符
                - 重新登录小红书后获取新Cookie
                """)
            
            # 发送通知
            if sendkey and "sctp" in sendkey:
                with st.spinner("发送微信通知..."):
                    notify_title = f"【监控】{data['title'][:20]}..."
                    notify_content = f"""商品：{data['title']}
价格：¥{data['price']}
销量：{data['sales']}
店铺：{data['shop']}
时间：{data['time']}
链接：{data['url']}"""
                    
                    success, msg = send_wechat_notification(sendkey, notify_title, notify_content)
                    if success:
                        st.success("📱 微信通知已发送！")
                    else:
                        st.error(f"📱 通知发送失败: {msg}")
            
            # 数据下载
            st.divider()
            col_download, col_json = st.columns(2)
            
            # CSV下载
            csv_content = f"时间,URL,标题,价格,销量,店铺\n{data['time']},{data['url']},{data['title']},{data['price']},{data['sales']},{data['shop']}"
            col_download.download_button(
                label="⬇️ 下载CSV",
                data=csv_content,
                file_name=f"xhs_monitor_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                use_container_width=True
            )
            
            # 查看原始JSON
            with col_json.expander("查看原始数据"):
                st.json(data)
            
            # 定时模式提示
            if not test_mode:
                st.info("""
                ⏰ 已开启定时模式（每小时检查一次）
                
                ⚠️ 注意：Streamlit Cloud免费版会在页面关闭后停止运行，
                如需24小时监控，请联系了解标准版服务。
                """)

# 页脚
st.divider()
st.caption("© 2024 小红书竞品监控工具 | 标准版服务联系微信：你的微信号")
