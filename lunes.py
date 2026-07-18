#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import re
import requests
from seleniumbase import SB

# ========== 环境变量 ==========
EMAIL        = os.environ.get("LUNES_EMAIL") or ""
PASSWORD     = os.environ.get("LUNES_PASSWORD") or ""
TG_CHAT_ID   = os.environ.get("TG_CHAT_ID") or ""
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN") or ""
PROXY_URL    = os.environ.get("NODE_LINK") or os.environ.get("PROXY_URL") or ""

LOGIN_URL = "https://betadash.lunes.host/login?next=/"

# ========== Telegram 推送 ==========
def send_tg_message(status_icon, status_text, extra_text=""):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("ℹ️ 未配置 TG 凭证，跳过推送")
        return

    local_time = time.gmtime(time.time() + 8 * 3600)
    current_time_str = time.strftime("%Y-%m-%d %H:%M:%S", local_time)

    if '@' in EMAIL:
        name, domain = EMAIL.split('@', 1)
        masked = f"{name[:2]}****{name[-2:]}@{domain}" if len(name) > 4 else f"{name}@{domain}"
    else:
        masked = EMAIL[:2] + '****'

    text = (
        f"🇺🇸 Lunes 保活通知\n\n"
        f"{status_icon} {status_text}\n"
        f"👤 登录账户: {masked}\n"
        f"⏱️ 时间: {current_time_str}"
    )
    if extra_text:
        text += f"\n\n{extra_text}"

    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": TG_CHAT_ID, "text": text}, timeout=10)
        if r.status_code == 200:
            print("📩 Telegram 通知发送成功")
        else:
            print(f"⚠️ Telegram 发送失败: {r.text}")
    except Exception as e:
        print(f"⚠️ Telegram 异常: {e}")

# ========== Turnstile 处理（增强版） ==========
def handle_turnstile(sb) -> bool:
    # 检查是否存在 Turnstile 输入框
    exists_js = "return !!document.querySelector('input[name=\"cf-turnstile-response\"]');"
    if not sb.execute_script(exists_js):
        print("ℹ️ 未检测到 Turnstile，跳过")
        return True

    print("🔍 检测到 Turnstile，尝试自动通过...")

    # 先等待 Turnstile iframe 加载完成
    try:
        sb.wait_for_element('iframe[src*="challenges.cloudflare.com"]', timeout=15)
        print("✅ Turnstile iframe 已加载")
    except Exception:
        print("⚠️ Turnstile iframe 未在 15 秒内出现，可能已自动通过")
        # 若 iframe 未出现但输入框已填充，可能已通过
        if sb.execute_script("return document.querySelector('input[name=\"cf-turnstile-response\"]')?.value?.length > 20;"):
            return True
        # 否则继续尝试点击

    for attempt in range(4):
        try:
            # 滚动到 Turnstile 可见区域
            sb.execute_script("""
                var el = document.querySelector('iframe[src*="challenges.cloudflare.com"]');
                if (el) el.scrollIntoView({behavior: 'smooth', block: 'center'});
            """)
            time.sleep(1)

            # 使用 GUI 鼠标模拟点击（通过 CDP）
            sb.uc_gui_click_cf()
            # 等待验证完成（至少 5 秒）
            time.sleep(6)

            solved_js = "return document.querySelector('input[name=\"cf-turnstile-response\"]')?.value?.length > 20;"
            if sb.execute_script(solved_js):
                print(f"✅ Turnstile 通过（尝试 {attempt+1}）")
                return True
            else:
                print(f"  ⚠️ 第 {attempt+1} 次未完成，重试...")
        except Exception as e:
            print(f"  ⚠️ Turnstile 异常: {e}")

        # 如果失败，尝试直接点击 iframe（回退方案）
        try:
            iframe = sb.find_element('iframe[src*="challenges.cloudflare.com"]')
            sb.driver.execute_script("arguments[0].click();", iframe)  # JS 点击
            time.sleep(5)
            if sb.execute_script(solved_js):
                print(f"✅ Turnstile 通过（备用点击，尝试 {attempt+1}）")
                return True
        except Exception:
            pass

        time.sleep(2)

    print("❌ Turnstile 4 次尝试均失败")
    return False

# ========== 登录 ==========
def login(sb) -> bool:
    print(f"🌐 打开登录页面: {LOGIN_URL}")
    sb.uc_open_with_reconnect(LOGIN_URL, reconnect_time=5)
    time.sleep(3)

    try:
        sb.wait_for_element('input[type="email"], input[name="email"], input[id="email"]', timeout=20)
    except Exception:
        sb.save_screenshot("login_form_not_found.png")
        with open("login_page_source.html", "w", encoding="utf-8") as f:
            f.write(sb.get_page_source())
        print("❌ 登录表单未加载")
        return False

    try:
        for btn in sb.find_elements("button"):
            if "Accept" in (btn.text or ""):
                btn.click()
                time.sleep(0.5)
                break
    except Exception:
        pass

    sb.fill('input[type="email"], input[name="email"], input[id="email"]', EMAIL)
    sb.fill('input[type="password"], input[name="password"], input[id="password"]', PASSWORD)
    time.sleep(1)

    if not handle_turnstile(sb):
        sb.save_screenshot("turnstile_failed.png")
        return False

    sb.press_keys('input[type="password"], input[name="password"]', '\n')
    time.sleep(2)

    try:
        sb.wait_for_element('a[href="/account"], .user-menu, .dashboard', timeout=20)
        print("✅ 登录成功")
        return True
    except Exception:
        sb.save_screenshot("login_failed.png")
        print(f"❌ 登录失败，当前 URL: {sb.get_current_url()}")
        return False

# ========== 访问服务器 ==========
def visit_server(sb) -> (bool, dict):
    print("🔍 正在查找服务器卡片...")
    try:
        sb.wait_for_element('a.server-card', timeout=15)
    except Exception:
        return False, {"error": "未找到服务器卡片"}

    cards = sb.find_elements('a.server-card')
    if not cards:
        return False, {"error": "服务器卡片列表为空"}

    card = cards[0]
    href = card.get_attribute('href')
    if not href:
        return False, {"error": "卡片缺少 href"}

    match = re.search(r'/servers/(\d+)', href)
    if not match:
        return False, {"error": f"无法解析 ID: {href}"}
    server_id = match.group(1)

    print(f"🖱️ 点击服务器卡片 (ID: {server_id})")
    card.click()
    time.sleep(3)

    expected = f"https://betadash.lunes.host/servers/{server_id}"
    for _ in range(10):
        cur = sb.get_current_url().split('?')[0]
        if cur == expected:
            break
        time.sleep(1)
    else:
        return False, {"server_id": server_id, "error": f"跳转后 URL 不匹配"}

    page_title = sb.get_title() or ""
    server_name = page_title.split("Server ", 1)[-1].strip() if "Server " in page_title else f"ID {server_id}"

    print(f"✅ 成功访问服务器: {server_name} (ID: {server_id})")
    return True, {"server_id": server_id, "server_name": server_name}

# ========== 主流程 ==========
def main():
    print("#" * 25)
    print("   Lunes 自动登录续期")
    print("#" * 25)

    # Chrome 选项，用于容器环境稳定运行
    chrome_options = {
        "arguments": [
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--window-size=1920,1080",
        ]
    }

    sb_kwargs = {
        "uc": True,
        "headless": False,
        "options": chrome_options,   # 传入额外参数
    }
    if PROXY_URL:
        print(f"🔗 使用代理: {PROXY_URL}")
        sb_kwargs["proxy"] = PROXY_URL
    else:
        print("🌐 直连访问")

    import seleniumbase
    print(f"📦 SeleniumBase 版本: {seleniumbase.__version__}")

    with SB(**sb_kwargs) as sb:
        print("✅ 浏览器已启动")
        try:
            sb.open("https://api.ip.sb/ip")
            ip = sb.get_text("body")
            print(f"🌐 当前出口 IP: {ip}")
        except Exception:
            pass

        if login(sb):
            print("\n✅ 登录成功，正在处理服务器续期...")
            success, info = visit_server(sb)
            if success:
                extra = f"服务器: {info['server_name']}\nID: {info['server_id']}"
                send_tg_message("✅", "续期成功", extra)
            else:
                err = info.get('error', '未知错误')
                extra = f"错误: {err}"
                if 'server_id' in info:
                    extra += f"\n服务器ID: {info['server_id']}"
                send_tg_message("❌", "续期失败", extra)
        else:
            print("\n❌ 登录失败，终止后续操作")
            send_tg_message("❌", "登录失败", "")

if __name__ == "__main__":
    main()
