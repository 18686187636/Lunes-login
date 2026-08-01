#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import subprocess
import requests
import re
from seleniumbase import SB

# ========== 环境变量配置 ==========
EMAIL        = os.environ.get("LUNES_EMAIL") or ""     
PASSWORD     = os.environ.get("LUNES_PASSWORD") or ""  
TG_CHAT_ID   = os.environ.get("TG_CHAT_ID") or ""      
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN") or ""    

LOGIN_URL = "https://betadash.lunes.host/login?next=/"

# ========== Telegram 推送 ==========
def send_tg_message(status_icon, status_text, extra_text=""):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("ℹ️ 未配置 TG_BOT_TOKEN 或 TG_CHAT_ID，跳过 Telegram 推送。")
        return

    current_time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

    if '@' in EMAIL:
        name, domain = EMAIL.split('@', 1)
        if len(name) > 4:
            masked_email = f"{name[:2]}****{name[-2:]}@{domain}"
        else:
            masked_email = f"{name}@{domain}"
    else:
        masked_email = EMAIL[:2] + '****'

    text = (
        f"🇺🇸 Lunes 保活通知\n\n"
        f"{status_icon} {status_text}\n"
        f"👤 登录账户: {masked_email}\n"
        f"⏱️ 登录时间: {current_time_str}"
    )
    if extra_text:
        text += f"\n\n{extra_text}"

    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TG_CHAT_ID, "text": text}
    
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 200:
            print("📩 Telegram 通知发送成功！")
        else:
            print(f"  ⚠️ Telegram 通知发送失败: {r.text}")
    except Exception as e:
        print(f"  ⚠️ Telegram 通知发送异常: {e}")

# ========== Turnstile 处理相关 JS ==========
_EXPAND_JS = """
(function() {
    var ts = document.querySelector('input[name="cf-turnstile-response"]');
    if (!ts) return 'no-turnstile';
    var el = ts;
    for (var i = 0; i < 20; i++) {
        el = el.parentElement;
        if (!el) break;
        var s = window.getComputedStyle(el);
        if (s.overflow === 'hidden' || s.overflowX === 'hidden' || s.overflowY === 'hidden')
            el.style.overflow = 'visible';
        el.style.minWidth = 'max-content';
    }
    document.querySelectorAll('iframe').forEach(function(f){
        if (f.src && f.src.includes('challenges.cloudflare.com')) {
            f.style.width = '300px'; f.style.height = '65px';
            f.style.minWidth = '300px';
            f.style.visibility = 'visible'; f.style.opacity = '1';
        }
    });
    return 'done';
})()
"""

_EXISTS_JS = """
(function(){
    return document.querySelector('input[name="cf-turnstile-response"]') !== null;
})()
"""

_SOLVED_JS = """
(function(){
    var i = document.querySelector('input[name="cf-turnstile-response"]');
    return !!(i && i.value && i.value.length > 20);
})()
"""

_COORDS_JS = """
(function(){
    var iframes = document.querySelectorAll('iframe');
    for (var i = 0; i < iframes.length; i++) {
        var src = iframes[i].src || '';
        if (src.includes('cloudflare') || src.includes('turnstile') || src.includes('challenges')) {
            var r = iframes[i].getBoundingClientRect();
            if (r.width > 0 && r.height > 0)
                return {cx: Math.round(r.x + 30), cy: Math.round(r.y + r.height / 2)};
        }
    }
    var inp = document.querySelector('input[name="cf-turnstile-response"]');
    if (inp) {
        var p = inp.parentElement;
        for (var j = 0; j < 5; j++) {
            if (!p) break;
            var r = p.getBoundingClientRect();
            if (r.width > 100 && r.height > 30)
                return {cx: Math.round(r.x + 30), cy: Math.round(r.y + r.height / 2)};
            p = p.parentElement;
        }
    }
    return null;
})()
"""

_WININFO_JS = """
(function(){
    return {
        sx: window.screenX || 0,
        sy: window.screenY || 0,
        oh: window.outerHeight,
        ih: window.innerHeight
    };
})()
"""

def js_fill_input(sb, selector: str, text: str):
    safe_text = text.replace('\\', '\\\\').replace('"', '\\"')
    sb.execute_script(f"""
    (function(){{
        var el = document.querySelector('{selector}');
        if (!el) return;
        var nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
        if (nativeInputValueSetter) {{
            nativeInputValueSetter.call(el, "{safe_text}");
        }} else {{
            el.value = "{safe_text}";
        }}
        el.dispatchEvent(new Event('input', {{ bubbles: true }}));
        el.dispatchEvent(new Event('change', {{ bubbles: true }}));
    }})()
    """)

# ========== xdotool 辅助 ==========
def _activate_window():
    for cls in ["chrome", "chromium", "Chromium", "Chrome", "google-chrome"]:
        try:
            r = subprocess.run(["xdotool", "search", "--onlyvisible", "--class", cls], capture_output=True, text=True, timeout=3)
            wids = [w for w in r.stdout.strip().split("\n") if w.strip()]
            if wids:
                subprocess.run(["xdotool", "windowactivate", "--sync", wids[0]], timeout=3, stderr=subprocess.DEVNULL)
                time.sleep(0.2)
                return
        except Exception:
            pass
    try:
        subprocess.run(["xdotool", "getactivewindow", "windowactivate"], timeout=3, stderr=subprocess.DEVNULL)
    except Exception:
        pass

def _xdotool_click(x: int, y: int):
    _activate_window()
    try:
        subprocess.run(["xdotool", "mousemove", "--sync", str(x), str(y)], timeout=3, stderr=subprocess.DEVNULL)
        time.sleep(0.15)
        subprocess.run(["xdotool", "click", "1"], timeout=2, stderr=subprocess.DEVNULL)
    except Exception:
        os.system(f"xdotool mousemove {x} {y} click 1 2>/dev/null")

def _click_turnstile(sb):
    try:
        coords = sb.execute_script(_COORDS_JS)
    except Exception as e:
        print(f"⚠️ 获取 Turnstile 坐标失败: {e}")
        return
    if not coords:
        print("⚠️ 无法定位 Turnstile 坐标")
        return
    try:
        wi = sb.execute_script(_WININFO_JS)
    except Exception:
        wi = {"sx": 0, "sy": 0, "oh": 800, "ih": 768}
        
    bar = wi["oh"] - wi["ih"]
    ax  = coords["cx"] + wi["sx"]
    ay  = coords["cy"] + wi["sy"] + bar
    print(f"🖱️ 尝试点击 Turnstile ({ax}, {ay})")
    _xdotool_click(ax, ay)

def handle_turnstile(sb) -> bool:
    print("🔍 处理 Cloudflare Turnstile 验证...")
    time.sleep(2)
    
    if sb.execute_script(_SOLVED_JS):
        print("✅ 已静默通过")
        return True

    try:
        if sb.find_elements("iframe[src*='challenges.cloudflare.com']"):
            print("  尝试使用 SeleniumBase UC 自动点击...")
            sb.uc_gui_click_captcha()
            time.sleep(3)
            if sb.execute_script(_SOLVED_JS):
                print("✅ Turnstile 通过（UC 模式）")
                return True
    except Exception:
        pass

    for _ in range(3):
        try: sb.execute_script(_EXPAND_JS)
        except Exception: pass
        time.sleep(0.5)

    for attempt in range(6):
        if sb.execute_script(_SOLVED_JS):
            print(f"✅ Turnstile 通过（第 {attempt + 1} 次尝试）")
            return True
        try: sb.execute_script(_EXPAND_JS)
        except Exception: pass
        time.sleep(0.3)
        
        _click_turnstile(sb)
        
        for _ in range(8):
            time.sleep(0.5)
            if sb.execute_script(_SOLVED_JS):
                print(f"✅ Turnstile 通过（第 {attempt + 1} 次尝试）")
                return True
        print(f"  ⚠️ 第 {attempt + 1} 次未通过，重试...")

    print("  ❌ Turnstile 6 次均失败")
    return False

# ========== 登录函数 ==========
def login(sb) -> bool:
    print(f"🌐 打开登录页面: {LOGIN_URL}")
    sb.uc_open_with_reconnect(LOGIN_URL, reconnect_time=5)
    time.sleep(6)

    print("⏳ 等待 Cloudflare 验证通过...")
    cf_passed = False
    for i in range(30):
        page_src = sb.get_page_source() or ""
        if 'input[name="email"]' in page_src.lower() or 'name="email"' in page_src.lower():
            cf_passed = True
            print(f"✅ Cloudflare 验证已通过（{i+1}s）")
            break
        time.sleep(1)
    if not cf_passed:
        print("⚠️ Cloudflare 验证可能未通过，继续尝试...")

    try:
        sb.wait_for_element('input[name="email"]', timeout=15)
    except Exception:
        try:
            sb.wait_for_element('input[name="Email"]', timeout=5)
        except Exception:
            print("❌ 页面未加载出登录表单")
            cur_url = sb.get_current_url()
            page_title = sb.get_title() or ""
            print(f"  当前 URL: {cur_url}")
            print(f"  当前标题: {page_title}")
            sb.save_screenshot("login_load_fail.png")
            return False

    print("🍪 关闭可能的 Cookie 弹窗...")
    try:
        for btn in sb.find_elements("button"):
            if "Accept" in (btn.text or ""):
                btn.click()
                time.sleep(0.5)
                break
    except Exception:
        pass

    print(f"📧 填写邮箱...")
    js_fill_input(sb, 'input[name="email"]', EMAIL)
    time.sleep(0.3)
    
    print("🔑 填写密码...")
    js_fill_input(sb, 'input[name="password"]', PASSWORD)
    time.sleep(1)

    if sb.execute_script(_EXISTS_JS):
        if not handle_turnstile(sb):
            print("❌ 登录界面的 Turnstile 验证失败")
            sb.save_screenshot("login_turnstile_fail.png")
            return False
    else:
        print("ℹ️ 未检测到 Turnstile")

    print("🖱️ 提交登录...")
    sb.press_keys('input[name="password"]', '\n')
    time.sleep(2)

    error_selectors = [".alert-danger", ".error", ".invalid-feedback", ".text-danger", ".alert"]
    for sel in error_selectors:
        err_elements = sb.find_elements(sel)
        for err in err_elements:
            if err.is_displayed() and err.text.strip():
                print(f"❌ 登录失败，服务端返回错误: {err.text.strip()}")
                sb.save_screenshot("login_error.png")
                return False

    print("⏳ 等待页面重定向或仪表板加载...")
    start_time = time.time()
    redirect_occurred = False
    while time.time() - start_time < 20:
        current_url = sb.get_current_url().split('?')[0].lower()
        if "/login" not in current_url:
            print(f"✅ 页面已重定向到 {current_url}")
            redirect_occurred = True
            break

        for sel in error_selectors:
            err_elements = sb.find_elements(sel)
            for err in err_elements:
                if err.is_displayed() and err.text.strip():
                    print(f"❌ 登录失败，服务端返回错误: {err.text.strip()}")
                    sb.save_screenshot("login_error.png")
                    return False

        try:
            if sb.find_elements('a.server-card'):
                print("✅ 检测到服务器卡片，登录成功！")
                return True
        except Exception:
            pass

        time.sleep(1)
    else:
        print("❌ 登录后超过 20 秒仍未重定向，仍停留在登录页")
        sb.save_screenshot("login_no_redirect.png")
        return False

    if redirect_occurred:
        print("⏳ 等待仪表板元素完全加载...")
        try:
            sb.wait_for_element_visible('a.server-card', timeout=15)
            print("✅ 检测到服务器卡片，登录成功！")
            return True
        except Exception:
            print("⚠️ 未找到服务器卡片，但已成功重定向，视为登录成功")
            return True

    return False

# ========== 访问服务器（修正点击） ==========
def visit_server(sb) -> (bool, dict):
    print("🔍 正在查找服务器卡片...")
    try:
        sb.wait_for_element_visible('a.server-card', timeout=20)
    except Exception:
        print("  首次未找到卡片，刷新页面重试...")
        sb.refresh()
        time.sleep(3)
        try:
            sb.wait_for_element_visible('a.server-card', timeout=15)
        except Exception:
            print("❌ 刷新后仍未找到服务器卡片")
            return False, {"error": "未找到服务器卡片，可能账户无服务器"}

    cards = sb.find_elements('a.server-card')
    if not cards:
        return False, {"error": "未找到服务器卡片"}

    card = cards[0]
    href = card.get_attribute('href')
    if not href:
        inner_link = card.find_element('a') if card.find_elements('a') else None
        if inner_link:
            href = inner_link.get_attribute('href')
    if not href:
        return False, {"error": "卡片缺少 href 属性"}

    match = re.search(r'/servers/(\d+)', href)
    if not match:
        return False, {"error": f"无法从 href 解析服务器 ID: {href}"}
    server_id = match.group(1)

    print(f"🖱️ 点击服务器卡片 (ID: {server_id})")
    # 使用原生 click，避免 CDP 下 arguments 未定义
    try:
        card.click()
    except Exception as e:
        print(f"原生点击失败: {e}，尝试用 JavaScript 点击")
        try:
            # 某些版本可能仍支持，但若失败则放弃
            sb.execute_script("arguments[0].click();", card)
        except Exception:
            print("JavaScript 点击也失败，使用 sb.click()")
            sb.click(card)
    time.sleep(3)

    expected_url_prefix = f"https://betadash.lunes.host/servers/{server_id}"
    for _ in range(10):
        cur_url = sb.get_current_url().split('?')[0]
        if cur_url == expected_url_prefix:
            break
        time.sleep(1)
    else:
        return False, {"server_id": server_id, "error": f"跳转后 URL 不匹配，当前: {sb.get_current_url()}"}

    page_title = sb.get_title() or ""
    server_name = ""
    if "Server " in page_title:
        server_name = page_title.split("Server ", 1)[-1].strip()
    else:
        server_name = f"ID {server_id}"

    print(f"✅ 成功访问服务器: {server_name} (ID: {server_id})")
    return True, {"server_id": server_id, "server_name": server_name}

# ========== 主函数 ==========
def main():
    print("#" * 25)
    print("   Lunes 自动登录续期")
    print("#" * 25)
    
    if not EMAIL or not PASSWORD:
        print("❌ 请设置环境变量 LUNES_EMAIL 和 LUNES_PASSWORD")
        return

    is_proxy = os.environ.get("IS_PROXY", "false").lower() == "true"
    sb_kwargs = {"uc": True, "headless": False}
    
    if is_proxy:
        proxy_str = "http://127.0.0.1:1081"
        print(f"🔗 挂载sing-box代理: {proxy_str}")
        sb_kwargs["proxy"] = proxy_str
    else:
        print("🌐 未使用代理，直连访问")
    
    with SB(**sb_kwargs) as sb:
        print("✅ 浏览器已启动")
        try:
            sb.open("https://api.ip.sb/ip")
            print(f"🌐 当前出口真实 IP: {sb.get_text('body')}")
        except Exception:
            pass

        if login(sb):
            print("\n✅ 登录成功，正在处理服务器续期...")
            success, info = visit_server(sb)
            if success:
                extra = f"服务器: {info['server_name']}\nID: {info['server_id']}"
                send_tg_message("✅", "续期成功", extra)
            else:
                error_msg = info.get('error', '未知错误')
                print(f"❌ 访问服务器失败: {error_msg}")
                extra = f"错误: {error_msg}"
                if 'server_id' in info:
                    extra += f"\n服务器ID: {info['server_id']}"
                send_tg_message("❌", "续期失败", extra)
        else:
            print("\n❌ 登录失败，终止后续续期操作。")
            send_tg_message("❌", "登录失败", "")

if __name__ == "__main__":
    main()
