import os
import requests
from flask import Flask, request, abort, render_template_string
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
    FollowEvent, PostbackEvent,
    TemplateSendMessage, ButtonsTemplate,
    PostbackTemplateAction
)
from apscheduler.schedulers.background import BackgroundScheduler
import database as db

app = Flask(__name__)

CHANNEL_SECRET = os.environ.get("CHANNEL_SECRET", "")
CHANNEL_ACCESS_TOKEN = os.environ.get("CHANNEL_ACCESS_TOKEN", "")
PHARMACIST_LINE_ID = os.environ.get("PHARMACIST_LINE_ID", "")
DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "osocare2026")

line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

db.init_db()

# ─────────────────────────── RICH MENU SETUP ────────────────────────────

def setup_rich_menu():
    """สร้าง Rich Menu 6 ปุ่มอัตโนมัติตอน startup"""
    if not CHANNEL_ACCESS_TOKEN:
        return

    headers_json = {
        "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    headers_auth = {
        "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"
    }

    # ลบ menu เก่าทั้งหมดก่อน
    try:
        r = requests.get("https://api.line.me/v2/bot/richmenu/list", headers=headers_auth)
        for m in r.json().get("richmenus", []):
            requests.delete(f"https://api.line.me/v2/bot/richmenu/{m['richMenuId']}", headers=headers_auth)
    except Exception as e:
        print(f"Rich Menu cleanup error: {e}")

    # สร้าง Rich Menu structure
    menu_body = {
        "size": {"width": 2500, "height": 1686},
        "selected": True,
        "name": "Oso-Care Main Menu",
        "chatBarText": "Oso-Care Menu",
        "areas": [
            {
                "bounds": {"x": 0,    "y": 0,   "width": 833, "height": 843},
                "action": {"type": "postback", "data": "action=taken",   "displayText": "✅ กินยาแล้ว"}
            },
            {
                "bounds": {"x": 833,  "y": 0,   "width": 834, "height": 843},
                "action": {"type": "postback", "data": "action=skipped", "displayText": "⏰ ยังไม่ได้กิน"}
            },
            {
                "bounds": {"x": 1667, "y": 0,   "width": 833, "height": 843},
                "action": {"type": "postback", "data": "action=adr",     "displayText": "⚠️ มีอาการผิดปกติ"}
            },
            {
                "bounds": {"x": 0,    "y": 843, "width": 833, "height": 843},
                "action": {"type": "message", "text": "แต้มของฉัน"}
            },
            {
                "bounds": {"x": 833,  "y": 843, "width": 834, "height": 843},
                "action": {"type": "message", "text": "เปลี่ยนยา"}
            },
            {
                "bounds": {"x": 1667, "y": 843, "width": 833, "height": 843},
                "action": {"type": "message", "text": "ฉุกเฉิน"}
            },
        ]
    }

    try:
        r = requests.post("https://api.line.me/v2/bot/richmenu", headers=headers_json, json=menu_body)
        menu_id = r.json().get("richMenuId")
        if not menu_id:
            print(f"Rich Menu create failed: {r.text}")
            return

        # Upload รูปภาพ (สร้างจาก Pillow)
        img_bytes = generate_rich_menu_image()
        requests.post(
            f"https://api-data.line.me/v2/bot/richmenu/{menu_id}/content",
            headers={"Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}", "Content-Type": "image/png"},
            data=img_bytes
        )

        # ตั้งเป็น default
        requests.post(
            f"https://api.line.me/v2/bot/user/all/richmenu/{menu_id}",
            headers=headers_auth
        )
        print(f"✅ Rich Menu ready: {menu_id}")

    except Exception as e:
        print(f"Rich Menu setup error: {e}")


def generate_rich_menu_image():
    """Generate Rich Menu image 2500x1686 using English only — works on Railway"""
    from PIL import Image, ImageDraw, ImageFont
    import io

    W, H = 2500, 1686
    BW, BH = W // 3, H // 2
    PAD = 22

    CARDS = [
        {"line1": "TOOK MED",   "line2": "Record medicine", "bg": "#1e8449", "top": "#2ecc71"},
        {"line1": "SKIP",       "line2": "Remind me later", "bg": "#2c3e50", "top": "#7f8c8d"},
        {"line1": "SYMPTOMS",   "line2": "Alert pharmacist","bg": "#c0392b", "top": "#e74c3c"},
        {"line1": "MY POINTS",  "line2": "Redeem discount", "bg": "#b7950b", "top": "#f39c12"},
        {"line1": "CHANGE MED", "line2": "Update medicine", "bg": "#16a085", "top": "#1abc9c"},
        {"line1": "EMERGENCY",  "line2": "Call pharmacist", "bg": "#922b21", "top": "#e74c3c"},
    ]

    def hex2rgb(h):
        h = h.lstrip("#")
        return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

    def get_font(size):
        for p in [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        ]:
            if os.path.exists(p):
                try:
                    return ImageFont.truetype(p, size)
                except:
                    pass
        return ImageFont.load_default()

    def get_font_regular(size):
        for p in [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        ]:
            if os.path.exists(p):
                try:
                    return ImageFont.truetype(p, size)
                except:
                    pass
        return ImageFont.load_default()

    img = Image.new("RGB", (W, H), hex2rgb("#1a3a2a"))
    draw = ImageDraw.Draw(img)
    f_big  = get_font(88)
    f_sub  = get_font_regular(50)

    for i, card in enumerate(CARDS):
        c, r = i % 3, i // 3
        x1 = c * BW + PAD
        y1 = r * BH + PAD
        x2 = x1 + BW - PAD * 2
        y2 = y1 + BH - PAD * 2
        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2

        # Card background
        draw.rounded_rectangle([x1, y1, x2, y2], radius=44,
                                fill=hex2rgb(card["bg"]))

        # Top accent bar
        draw.rounded_rectangle([x1+32, y1, x2-32, y1+56],
                                radius=18, fill=hex2rgb(card["top"]))
        draw.rectangle([x1+32, y1+28, x2-32, y1+56],
                       fill=hex2rgb(card["top"]))

        # Main label (big bold English)
        try:
            lw = int(draw.textlength(card["line1"], font=f_big))
        except:
            lw = len(card["line1"]) * 50
        draw.text((cx - lw // 2, cy - 80), card["line1"],
                  font=f_big, fill=(255, 255, 255))

        # Divider
        draw.line([(cx - 90, cy + 24), (cx + 90, cy + 24)],
                  fill=hex2rgb(card["top"]), width=4)

        # Sub label
        try:
            sw = int(draw.textlength(card["line2"], font=f_sub))
        except:
            sw = len(card["line2"]) * 28
        draw.text((cx - sw // 2, cy + 36), card["line2"],
                  font=f_sub, fill=(210, 240, 220))

    # Grid dividers
    for i in [1, 2]:
        draw.line([(i * BW, 0), (i * BW, H)], fill=(255,255,255,15), width=2)
    draw.line([(0, H // 2), (W, H // 2)], fill=(255,255,255,15), width=2)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


setup_rich_menu()


# ─────────────────────────── WEBHOOK ────────────────────────────

@app.route("/webhook", methods=["POST"])
def webhook():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK"

# ─────────────────────────── FOLLOW ─────────────────────────────

@handler.add(FollowEvent)
def handle_follow(event):
    user_id = event.source.user_id
    db.save_user(user_id)
    line_bot_api.reply_message(
        event.reply_token,
        [
            TextSendMessage(text="สวัสดีค่ะ 👋 ยินดีต้อนรับสู่ Oso-Care\nระบบดูแลสุขภาพจากโอสถศาลา 💊"),
            TextSendMessage(text="กรุณาพิมพ์ชื่อ-นามสกุลของคุณเพื่อลงทะเบียนนะคะ\nเช่น: สมชาย มีสุข")
        ]
    )

# ─────────────────────────── MESSAGE ────────────────────────────

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    text = event.message.text.strip()
    user = db.get_user(user_id)

    # ── Step 1: ลงทะเบียนชื่อ ──
    if user and not user["name"]:
        db.update_user_name(user_id, text)
        db.set_awaiting_med(user_id, 1)
        line_bot_api.reply_message(
            event.reply_token,
            [
                TextSendMessage(text=f"ขอบคุณค่ะ คุณ{text} 🙏\nลงทะเบียนชื่อเรียบร้อยแล้ว!"),
                TextSendMessage(text="💊 กรุณาพิมพ์ชื่อยาที่คุณใช้อยู่นะคะ\nเช่น: Amlodipine 5mg, Metformin, ยาความดัน")
            ]
        )
        return

    # ── Step 2: ลงทะเบียนยา ──
    if user and user.get("awaiting_med"):
        db.update_user_med(user_id, text)
        name = user["name"]
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(
                text=f"เยี่ยมเลยค่ะ! 🎉\nบันทึกยา '{text}' เรียบร้อยแล้ว\n\nตอนนี้คุณ{name} พร้อมใช้งาน Oso-Care แล้วค่ะ ✅\n\nพิมพ์ได้เลยนะคะ:\n💊 'ทดสอบแจ้งเตือน' — ทดสอบปุ่มกินยา\n📋 'ทดสอบเช็กอิน' — เช็กอินสัปดาห์\n⭐ 'แต้มของฉัน' — ดูและแลก Health Points\n🔴 'ฉุกเฉิน' — แจ้งเภสัชกรทันที"
            )
        )
        return

    # ── ADR Mode: รับคำอธิบายอาการ ──
    if user and user.get("adr_mode"):
        db.set_adr_mode(user_id, 0)
        db.save_alert(user_id, "warning", "ผู้ป่วยรายงานอาการผิดปกติ", adr_description=text)
        notify_pharmacist(user_id, f"🟡 ADR Report", adr_text=text)
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(
                text=f"รับทราบค่ะ ✅\nบันทึกอาการของคุณแล้ว:\n\n📝 \"{text}\"\n\nเภสัชกรจะตรวจสอบและติดต่อกลับเร็วๆ นี้นะคะ 📞"
            )
        )
        return

    # ── ทดสอบแจ้งเตือนกินยา ──
    if text == "ทดสอบแจ้งเตือน":
        send_med_reminder_to(user_id, event.reply_token)
        return

    # ── ทดสอบ weekly check-in ──
    if text == "ทดสอบเช็กอิน":
        name = user["name"] if user else "คุณ"
        line_bot_api.reply_message(
            event.reply_token,
            TemplateSendMessage(
                alt_text="ทดสอบเช็กอินประจำสัปดาห์",
                template=ButtonsTemplate(
                    title=f"💙 ครบ 7 วันแล้วนะคะ คุณ{name}!",
                    text="ช่วงสัปดาห์ที่ผ่านมาเป็นยังไงบ้างคะ?",
                    actions=[
                        PostbackTemplateAction(label="😊 ปกติดี ไม่มีอะไร", data="action=checkin_ok"),
                        PostbackTemplateAction(label="⚠️ มีอาการผิดปกติ", data="action=adr")
                    ]
                )
            )
        )
        return

    # ── แต้มของฉัน ──
    if text in ["แต้มของฉัน", "แต้ม", "points"]:
        points = db.get_points(user_id)
        name = user["name"] if user else "คุณ"
        discount = (points // 100) * 10  # 100 แต้ม = 10 บาท
        line_bot_api.reply_message(
            event.reply_token,
            TemplateSendMessage(
                alt_text="Health Points ของคุณ",
                template=ButtonsTemplate(
                    title=f"⭐ Health Points ของคุณ{name}",
                    text=f"สะสมแล้ว {points} แต้ม\nแลกได้สูงสุด {discount} บาท\n(100 แต้ม = ส่วนลด 10 บาท)",
                    actions=[
                        PostbackTemplateAction(
                            label=f"🎁 แลก {discount} บาท" if discount > 0 else "⭐ สะสมต่อไป",
                            data=f"action=redeem&pts={min(points, (points//100)*100)}&discount={discount}"
                        ),
                        PostbackTemplateAction(label="📊 ดูประวัติการแลก", data="action=redeem_history")
                    ]
                )
            )
        )
        return

    # ── เปลี่ยนยา ──
    if text in ["เปลี่ยนยา", "แก้ไขยา", "อัพเดทยา"]:
        db.set_awaiting_med(user_id, 1)
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="💊 พิมพ์ชื่อยาใหม่ของคุณได้เลยค่ะ\nเช่น: Amlodipine 5mg, Metformin 500mg")
        )
        return

    # ── คำฉุกเฉิน ──
    urgent_words = ["ฉุกเฉิน", "ใจสั่น", "เจ็บหน้าอก", "หายใจไม่ออก", "หน้ามืด"]
    if any(w in text for w in urgent_words):
        db.save_alert(user_id, "urgent", text)
        notify_pharmacist(user_id, f"🔴 URGENT: {text}")
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(
                text="⚠️ รับทราบค่ะ! กำลังแจ้งเภสัชกรทันทีเลยค่ะ\nรอสักครู่นะคะ เภสัชกรจะติดต่อกลับโดยเร็วที่สุดค่ะ 🏃‍♀️"
            )
        )
        return

    # ── เมนูช่วยเหลือ ──
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(
            text="พิมพ์ได้เลยนะคะ 😊\n\n💊 'ทดสอบแจ้งเตือน' — ทดสอบปุ่มกินยา\n📋 'ทดสอบเช็กอิน' — เช็กอินสัปดาห์\n⭐ 'แต้มของฉัน' — ดูและแลก Health Points\n💊 'เปลี่ยนยา' — อัพเดทชื่อยา\n🔴 'ฉุกเฉิน' — แจ้งเภสัชกรทันที"
        )
    )

# ─────────────────────────── POSTBACK ───────────────────────────

@handler.add(PostbackEvent)
def handle_postback(event):
    data = dict(x.split("=") for x in event.postback.data.split("&"))
    action = data.get("action", "")
    user_id = event.source.user_id
    user = db.get_user(user_id)
    name = user["name"] if user else "คุณ"

    if action == "taken":
        db.log_medication(user_id, "taken")
        db.add_points(user_id, 10)
        points = db.get_points(user_id)
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(
                text=f"เยี่ยมมากเลยค่ะ คุณ{name}! 🎉\nได้รับ +10 Health Points\nสะสมแล้ว {points} แต้มค่ะ ✨"
            )
        )

    elif action == "skipped":
        db.log_medication(user_id, "skipped")
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="ไม่เป็นไรนะคะ 💙\nอย่าลืมกินยาในมื้อถัดไปด้วยนะคะ")
        )

    elif action == "adr":
        # เปิด ADR mode — รอรับข้อความอธิบายอาการ
        db.set_adr_mode(user_id, 1)
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(
                text="📝 กรุณาพิมพ์อธิบายอาการที่ผิดปกติของคุณนะคะ\n\nเช่น: ปวดหัว มึนงง คลื่นไส้ ผื่นขึ้น หรืออาการอื่นๆ\n\nเภสัชกรจะรับทราบทันทีค่ะ 💙"
            )
        )

    elif action == "checkin_ok":
        db.log_medication(user_id, "checkin_ok")
        db.add_points(user_id, 20)
        points = db.get_points(user_id)
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(
                text=f"ดีมากเลยค่ะ คุณ{name}! 🌟\nได้รับ +20 Health Points\nสะสมแล้ว {points} แต้มค่ะ"
            )
        )

    elif action == "redeem":
        pts = int(data.get("pts", 0))
        discount = int(data.get("discount", 0))
        if pts <= 0 or discount <= 0:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="⭐ ยังไม่มีแต้มพอสำหรับแลกนะคะ\nกินยาครบทุกวันเพื่อสะสมแต้มค่ะ 💊")
            )
            return
        db.redeem_points(user_id, pts, discount)
        remaining = db.get_points(user_id)
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(
                text=f"🎁 แลกส่วนลดสำเร็จค่ะ!\n\nใช้ {pts} แต้ม → ส่วนลด {discount} บาท\nแต้มคงเหลือ: {remaining} แต้ม\n\nแสดง message นี้ให้เภสัชกรที่ร้านยาเพื่อรับส่วนลดได้เลยค่ะ 🏪"
            )
        )

    elif action == "redeem_history":
        history = db.get_redemption_history(user_id)
        if not history:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="📊 ยังไม่มีประวัติการแลกแต้มค่ะ")
            )
        else:
            lines = ["📊 ประวัติการแลกแต้ม 5 ครั้งล่าสุด\n"]
            for h in history:
                date = h["redeemed_at"][:10]
                lines.append(f"• {date}: {h['points_used']} แต้ม → -{h['discount_thb']} บาท")
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="\n".join(lines))
            )

# ─────────────────────────── HELPERS ────────────────────────────

def send_med_reminder_to(user_id, reply_token=None):
    user = db.get_user(user_id)
    name = user["name"] if user else "คุณ"
    med = user["med_name"] if user else "ยาตามใบสั่ง"
    msg = TemplateSendMessage(
        alt_text="แจ้งเตือนกินยา",
        template=ButtonsTemplate(
            title=f"สวัสดีตอนเช้า คุณ{name} 🌅",
            text=f"ถึงเวลากิน {med} แล้วนะคะ 💊",
            actions=[
                PostbackTemplateAction(label="✅ กินแล้ว", data="action=taken"),
                PostbackTemplateAction(label="⏰ ยังไม่ได้กิน", data="action=skipped"),
                PostbackTemplateAction(label="⚠️ มีอาการผิดปกติ", data="action=adr")
            ]
        )
    )
    if reply_token:
        line_bot_api.reply_message(reply_token, msg)
    else:
        line_bot_api.push_message(user_id, msg)

def notify_pharmacist(patient_id, reason, adr_text=None):
    if not PHARMACIST_LINE_ID:
        return
    patient = db.get_user(patient_id)
    name = patient["name"] if patient else "ไม่ระบุ"
    med = patient["med_name"] if patient else "ไม่ระบุ"
    points = db.get_points(patient_id)
    adr_line = f"\nอาการ: {adr_text}" if adr_text else ""
    line_bot_api.push_message(
        PHARMACIST_LINE_ID,
        TextSendMessage(
            text=f"🚨 แจ้งเตือนจาก Oso-Care\n━━━━━━━━━━━━━━━\nผู้ป่วย: {name}\nเหตุผล: {reason}{adr_line}\nยา: {med}\nHealth Points: {points} แต้ม\n━━━━━━━━━━━━━━━\nกรุณาติดต่อกลับโดยด่วนค่ะ"
        )
    )

# ─────────────────────────── SCHEDULER ──────────────────────────

def send_daily_reminder():
    users = db.get_all_active_users()
    for user in users:
        if not user["name"]:
            continue
        try:
            send_med_reminder_to(user["line_id"])
        except Exception as e:
            print(f"Reminder error {user['line_id']}: {e}")

def send_weekly_checkin():
    users = db.get_all_active_users()
    for user in users:
        name = user["name"] or "คุณ"
        try:
            line_bot_api.push_message(
                user["line_id"],
                TemplateSendMessage(
                    alt_text="เช็กอินประจำสัปดาห์",
                    template=ButtonsTemplate(
                        title=f"💙 ครบ 7 วันแล้วนะคะ คุณ{name}!",
                        text="ช่วงสัปดาห์ที่ผ่านมาเป็นยังไงบ้างคะ?",
                        actions=[
                            PostbackTemplateAction(label="😊 ปกติดี ไม่มีอะไร", data="action=checkin_ok"),
                            PostbackTemplateAction(label="⚠️ มีอาการผิดปกติ", data="action=adr")
                        ]
                    )
                )
            )
        except Exception as e:
            print(f"Checkin error {user['line_id']}: {e}")

scheduler = BackgroundScheduler(timezone="Asia/Bangkok")
scheduler.add_job(send_daily_reminder, "cron", hour=8, minute=0)
scheduler.add_job(send_weekly_checkin, "cron", day_of_week="sun", hour=9, minute=0)
scheduler.start()

# ─────────────────────────── DASHBOARD ──────────────────────────

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="th">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Oso-Care Dashboard</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Segoe UI', sans-serif; background: #f0f4f8; color: #333; }
  .header { background: linear-gradient(135deg, #2d7a4f, #5aab75); color: white; padding: 20px 30px; }
  .header h1 { font-size: 1.5rem; }
  .header p { opacity: 0.85; font-size: 0.9rem; margin-top: 4px; }
  .container { max-width: 1100px; margin: 0 auto; padding: 24px 16px; }
  .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; margin-bottom: 28px; }
  .stat-card { background: white; border-radius: 12px; padding: 20px; text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.07); }
  .stat-card .num { font-size: 2rem; font-weight: 700; color: #2d7a4f; }
  .stat-card .label { font-size: 0.85rem; color: #666; margin-top: 4px; }
  .section { background: white; border-radius: 12px; padding: 20px; margin-bottom: 24px; box-shadow: 0 2px 8px rgba(0,0,0,0.07); }
  .section h2 { font-size: 1.1rem; margin-bottom: 16px; color: #2d7a4f; }
  table { width: 100%; border-collapse: collapse; font-size: 0.88rem; }
  th { background: #f7faf8; padding: 10px 12px; text-align: left; font-weight: 600; color: #444; border-bottom: 2px solid #e8f0eb; }
  td { padding: 10px 12px; border-bottom: 1px solid #f0f0f0; }
  tr:hover td { background: #f9fdfb; }
  .badge { display: inline-block; padding: 3px 10px; border-radius: 20px; font-size: 0.78rem; font-weight: 600; }
  .badge-ok { background: #d4edda; color: #1a6b2f; }
  .badge-warn { background: #fff3cd; color: #856404; }
  .badge-urgent { background: #f8d7da; color: #721c24; }
  .adherence-bar { background: #e8f0eb; border-radius: 4px; height: 8px; width: 100%; }
  .adherence-fill { background: #2d7a4f; border-radius: 4px; height: 8px; }
  .alert-desc { font-size: 0.82rem; color: #888; margin-top: 2px; }
</style>
</head>
<body>
<div class="header">
  <h1>🏥 Oso-Care Dashboard</h1>
  <p>ระบบติดตามผู้ป่วย — โอสถศาลา</p>
</div>
<div class="container">

  <!-- Stats -->
  <div class="stats">
    <div class="stat-card">
      <div class="num">{{ total_users }}</div>
      <div class="label">ผู้ป่วยทั้งหมด</div>
    </div>
    <div class="stat-card">
      <div class="num">{{ avg_adherence }}%</div>
      <div class="label">Adherence เฉลี่ย</div>
    </div>
    <div class="stat-card">
      <div class="num">{{ alert_count }}</div>
      <div class="label">แจ้งเตือนล่าสุด</div>
    </div>
    <div class="stat-card">
      <div class="num">{{ total_points }}</div>
      <div class="label">แต้มรวมทั้งหมด</div>
    </div>
  </div>

  <!-- Alerts -->
  <div class="section">
    <h2>🚨 แจ้งเตือนล่าสุด</h2>
    <table>
      <thead>
        <tr><th>ผู้ป่วย</th><th>ระดับ</th><th>รายละเอียด</th><th>เวลา</th></tr>
      </thead>
      <tbody>
        {% for a in alerts %}
        <tr>
          <td>{{ a.name }}</td>
          <td>
            {% if a.level == 'urgent' %}
              <span class="badge badge-urgent">🔴 ฉุกเฉิน</span>
            {% else %}
              <span class="badge badge-warn">🟡 ผิดปกติ</span>
            {% endif %}
          </td>
          <td>
            {{ a.message }}
            {% if a.adr_description %}
              <div class="alert-desc">📝 {{ a.adr_description }}</div>
            {% endif %}
          </td>
          <td>{{ a.created_at[:16] }}</td>
        </tr>
        {% endfor %}
        {% if not alerts %}
        <tr><td colspan="4" style="text-align:center;color:#aaa;padding:20px;">ยังไม่มีการแจ้งเตือนค่ะ ✅</td></tr>
        {% endif %}
      </tbody>
    </table>
  </div>

  <!-- Patients -->
  <div class="section">
    <h2>👥 รายชื่อผู้ป่วยทั้งหมด</h2>
    <table>
      <thead>
        <tr><th>ชื่อ</th><th>ยา</th><th>Adherence</th><th>กินแล้ว</th><th>ข้าม</th><th>แต้ม</th><th>ลงทะเบียน</th></tr>
      </thead>
      <tbody>
        {% for u in users %}
        <tr>
          <td>{{ u.name }}</td>
          <td>{{ u.med_name }}</td>
          <td>
            <div style="display:flex;align-items:center;gap:8px;">
              <div class="adherence-bar">
                <div class="adherence-fill" style="width:{{ u.adherence }}%"></div>
              </div>
              <span style="font-size:0.82rem;color:#555;">{{ u.adherence }}%</span>
            </div>
          </td>
          <td style="color:#2d7a4f;font-weight:600;">{{ u.taken_count }}</td>
          <td style="color:#c0392b;">{{ u.skipped_count }}</td>
          <td>⭐ {{ u.points }}</td>
          <td style="color:#888;font-size:0.82rem;">{{ u.registered_at[:10] if u.registered_at else '-' }}</td>
        </tr>
        {% endfor %}
        {% if not users %}
        <tr><td colspan="7" style="text-align:center;color:#aaa;padding:20px;">ยังไม่มีผู้ป่วยลงทะเบียนค่ะ</td></tr>
        {% endif %}
      </tbody>
    </table>
  </div>

</div>
</body>
</html>
"""

@app.route("/dashboard")
def dashboard():
    pw = request.args.get("pw", "")
    if pw != DASHBOARD_PASSWORD:
        return "<h3 style='font-family:sans-serif;padding:40px;color:#c0392b;'>❌ กรุณาใส่ password ที่ถูกต้องค่ะ<br><small>เช่น /dashboard?pw=osocare2026</small></h3>", 403

    users = db.get_all_users_detail()
    alerts = db.get_recent_alerts(20)
    total_users = len(users)
    avg_adherence = round(sum(u["adherence"] for u in users) / total_users) if total_users else 0
    total_points = sum(u["points"] for u in users)

    return render_template_string(
        DASHBOARD_HTML,
        users=users,
        alerts=alerts,
        total_users=total_users,
        avg_adherence=avg_adherence,
        alert_count=len(alerts),
        total_points=total_points
    )

# ─────────────────────────── ROOT ───────────────────────────────

@app.route("/", methods=["GET"])
def index():
    return "Oso-Care Bot is running! 💊"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
