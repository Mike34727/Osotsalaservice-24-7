import os
import base64
import requests
from datetime import datetime, timedelta
import pytz

BANGKOK = pytz.timezone('Asia/Bangkok')
def now_bkk():
    return datetime.now(BANGKOK)
from flask import Flask, request, abort, render_template_string
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
    FollowEvent, PostbackEvent,
    TemplateSendMessage, ButtonsTemplate,
    PostbackTemplateAction, FlexSendMessage
)
from apscheduler.schedulers.background import BackgroundScheduler
import database as db

app = Flask(__name__)

CHANNEL_SECRET        = os.environ.get("CHANNEL_SECRET", "")
CHANNEL_ACCESS_TOKEN  = os.environ.get("CHANNEL_ACCESS_TOKEN", "")
PHARMACIST_LINE_ID    = os.environ.get("PHARMACIST_LINE_ID", "")
DASHBOARD_PASSWORD    = os.environ.get("DASHBOARD_PASSWORD", "osocare2026")

line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler      = WebhookHandler(CHANNEL_SECRET)

db.init_db()

# ─────────────────────── RICH MENU IMAGE (embedded) ─────────────────────────
RICH_MENU_B64 = open(os.path.join(os.path.dirname(__file__), "richmenu_b64.txt")).read() \
    if os.path.exists(os.path.join(os.path.dirname(__file__), "richmenu_b64.txt")) else ""

# ─────────────────────────── RICH MENU SETUP ────────────────────────────────

def setup_rich_menu():
    if not CHANNEL_ACCESS_TOKEN:
        return

    headers_json = {"Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}",
                    "Content-Type": "application/json"}
    headers_auth = {"Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"}

    # ลบ menu เก่า
    try:
        r = requests.get("https://api.line.me/v2/bot/richmenu/list", headers=headers_auth)
        for m in r.json().get("richmenus", []):
            requests.delete(f"https://api.line.me/v2/bot/richmenu/{m['richMenuId']}",
                            headers=headers_auth)
    except Exception as e:
        print(f"Rich Menu cleanup error: {e}")

    menu_body = {
        "size": {"width": 2500, "height": 1686},
        "selected": True,
        "name": "Oso-Care Menu",
        "chatBarText": "Oso-Care Menu",
        "areas": [
            # แถวบน
            {"bounds": {"x": 0,    "y": 0,   "width": 833, "height": 843},
             "action": {"type": "message", "text": "ตารางทานยา"}},
            {"bounds": {"x": 833,  "y": 0,   "width": 834, "height": 843},
             "action": {"type": "postback", "data": "action=adr",
                        "displayText": "แจ้งอาการผิดปกติ"}},
            {"bounds": {"x": 1667, "y": 0,   "width": 833, "height": 843},
             "action": {"type": "message", "text": "บันทึกสุขภาพ"}},
            # แถวล่าง
            {"bounds": {"x": 0,    "y": 843, "width": 833, "height": 843},
             "action": {"type": "message", "text": "สถานะกล่องยา"}},
            {"bounds": {"x": 833,  "y": 843, "width": 834, "height": 843},
             "action": {"type": "message", "text": "แต้มของฉัน"}},
            {"bounds": {"x": 1667, "y": 843, "width": 833, "height": 843},
             "action": {"type": "message", "text": "ปรึกษาเภสัชกร"}},
        ]
    }

    try:
        r = requests.post("https://api.line.me/v2/bot/richmenu",
                          headers=headers_json, json=menu_body)
        menu_id = r.json().get("richMenuId")
        if not menu_id:
            print(f"Rich Menu create failed: {r.text}")
            return

        # Upload รูป
        if RICH_MENU_B64:
            img_bytes = base64.b64decode(RICH_MENU_B64)
            requests.post(
                f"https://api-data.line.me/v2/bot/richmenu/{menu_id}/content",
                headers={"Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}",
                         "Content-Type": "image/jpeg"},
                data=img_bytes
            )

        # Set default
        requests.post(f"https://api.line.me/v2/bot/user/all/richmenu/{menu_id}",
                      headers=headers_auth)
        print(f"Rich Menu ready: {menu_id}")

    except Exception as e:
        print(f"Rich Menu setup error: {e}")


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
    text    = event.message.text.strip()
    user    = db.get_user(user_id)

    # ── ลงทะเบียนชื่อ ──
    if user and not user["name"]:
        db.update_user_name(user_id, text)
        db.set_awaiting_med(user_id, 1)
        line_bot_api.reply_message(
            event.reply_token,
            [
                TextSendMessage(text=f"ขอบคุณค่ะ คุณ{text} 🙏"),
                TextSendMessage(text="💊 กรุณาพิมพ์ชื่อยาที่คุณใช้อยู่นะคะ\nเช่น: Amlodipine 5mg, Metformin")
            ]
        )
        return

    # ── ลงทะเบียนยา ──
    if user and user.get("awaiting_med"):
        db.update_user_med(user_id, text)
        name = user["name"]
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(
                text=f"เยี่ยมเลยค่ะ! 🎉 บันทึกยา '{text}' เรียบร้อย\n\nคุณ{name} พร้อมใช้งาน Oso-Care แล้วค่ะ ✅\nกดปุ่มเมนูด้านล่างได้เลยนะคะ 😊"
            )
        )
        return

    # ── ADR Mode ──
    if user and user.get("adr_mode"):
        db.set_adr_mode(user_id, 0)
        db.save_alert(user_id, "warning", "ผู้ป่วยรายงานอาการผิดปกติ", adr_description=text)
        notify_pharmacist(user_id, "🟡 ADR Report", adr_text=text)
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(
                text=f"✅ ได้รับข้อมูลแล้วค่ะ\nเภสัชกรจะติดต่อกลับเร็วๆ นี้นะคะ 💙\n\nกดปุ่มเมนูเพื่อใช้งานต่อได้เลยค่ะ 😊"
            )
        )
        return

    # ── Health log mode (บันทึกค่าสุขภาพ) ──
    if user and user.get("health_log_mode"):
        log_type = user.get("health_log_type", "")
        db.save_health_log(user_id, text, log_type)
        db.set_health_log_mode(user_id, 0)
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(
                text="✅ ได้รับข้อมูลแล้วค่ะ\nกดปุ่มเมนูเพื่อใช้งานต่อได้เลยค่ะ 😊"
            )
        )
        return

    # ══════════════════════════════════════════
    # ── 1. ตารางทานยา ──
    # ══════════════════════════════════════════
    if text == "ตารางทานยา":
        name = user["name"] if user else "คุณ"
        med  = user["med_name"] if user else "ยาตามใบสั่ง"
        logs = db.get_recent_med_logs(user_id, days=7)

        # สร้างตารางย้อนหลัง 7 วัน
        today = datetime.now().date()
        rows = []
        for i in range(6, -1, -1):
            from datetime import timedelta
            d = today - timedelta(days=i)
            d_str = d.strftime("%d/%m")
            day_logs = [l for l in logs if l["logged_at"][:10] == str(d)]
            if day_logs:
                status = "✅ กินแล้ว" if any(l["status"] == "taken" for l in day_logs) else "⏭ ข้าม"
            else:
                status = "—"
            rows.append(f"{d_str}  {status}")

        table_text = "\n".join(rows)
        taken_count  = sum(1 for l in logs if l["status"] == "taken")
        total_days   = 7
        adherence    = round(taken_count / total_days * 100)

        line_bot_api.reply_message(
            event.reply_token,
            [
                TextSendMessage(
                    text=f"💊 ตารางทานยาของคุณ{name}\nยา: {med}\n\n{table_text}\n\n📊 Adherence 7 วัน: {adherence}%"
                ),
                TemplateSendMessage(
                    alt_text="บันทึกการทานยาวันนี้",
                    template=ButtonsTemplate(
                        title=f"วันนี้ทานยาหรือยังคะ? 💊",
                        text=f"{med}",
                        actions=[
                            PostbackTemplateAction(label="✅ กินแล้ว", data="action=taken"),
                            PostbackTemplateAction(label="⏰ ยังไม่ได้กิน", data="action=skipped"),
                        ]
                    )
                )
            ]
        )
        return

    # ══════════════════════════════════════════
    # ── 2. บันทึกสุขภาพ ──
    # ══════════════════════════════════════════
    if text == "บันทึกสุขภาพ":
        name = user["name"] if user else "คุณ"
        logs = db.get_health_logs(user_id, limit=5)

        if not logs:
            history_text = "ยังไม่มีข้อมูลค่ะ"
        else:
            history_text = "\n".join(
                [f"• {l['logged_at'][:10]}  →  {l['value']}" for l in logs]
            )

        line_bot_api.reply_message(
            event.reply_token,
            [
                TextSendMessage(
                    text=f"📈 สมุดบันทึกสุขภาพ คุณ{name}\n\n5 รายการล่าสุด:\n{history_text}"
                ),
                TemplateSendMessage(
                    alt_text="บันทึกค่าสุขภาพ",
                    template=ButtonsTemplate(
                        title="📊 บันทึกค่าสุขภาพวันนี้",
                        text="เลือกสิ่งที่ต้องการบันทึกค่ะ",
                        actions=[
                            PostbackTemplateAction(
                                label="🩸 ความดันโลหิต",
                                data="action=log_health&type=bp"
                            ),
                            PostbackTemplateAction(
                                label="🍬 น้ำตาลในเลือด",
                                data="action=log_health&type=sugar"
                            ),
                            PostbackTemplateAction(
                                label="⚖️ น้ำหนัก",
                                data="action=log_health&type=weight"
                            ),
                        ]
                    )
                )
            ]
        )
        return

    # ══════════════════════════════════════════
    # ── 3. สถานะกล่องยา ──
    # ══════════════════════════════════════════
    if text == "สถานะกล่องยา":
        name = user["name"] if user else "คุณ"
        refill = db.get_refill_status(user_id)

        if not refill:
            line_bot_api.reply_message(
                event.reply_token,
                TemplateSendMessage(
                    alt_text="Oso-Refill Box",
                    template=ButtonsTemplate(
                        title="📦 Oso-Refill Box",
                        text="คุณยังไม่ได้สมัครบริการ\nจัดส่งยารายเดือนค่ะ",
                        actions=[
                            PostbackTemplateAction(
                                label="🛒 สมัครสมาชิก 299/เดือน",
                                data="action=subscribe_refill"
                            ),
                        ]
                    )
                )
            )
        else:
            days_left = refill.get("days_left", 0)
            status_emoji = "🟢" if days_left > 7 else "🟡" if days_left > 3 else "🔴"
            line_bot_api.reply_message(
                event.reply_token,
                TemplateSendMessage(
                    alt_text="สถานะกล่องยา",
                    template=ButtonsTemplate(
                        title=f"📦 Oso-Refill Box ของคุณ{name}",
                        text=f"{status_emoji} ยาเหลืออีก {days_left} วัน\nรอบถัดไป: {refill.get('next_date', '-')}",
                        actions=[
                            PostbackTemplateAction(
                                label="🔄 ต่ออายุสมาชิก",
                                data="action=renew_refill"
                            ),
                            PostbackTemplateAction(
                                label="📋 ดูรายการยา",
                                data="action=view_meds"
                            ),
                        ]
                    )
                )
            )
        return

    # ══════════════════════════════════════════
    # ── 4. แต้มของฉัน ──
    # ══════════════════════════════════════════
    if text in ["แต้มของฉัน", "แต้ม", "points"]:
        points   = db.get_points(user_id)
        name     = user["name"] if user else "คุณ"
        discount = (points // 100) * 10
        line_bot_api.reply_message(
            event.reply_token,
            TemplateSendMessage(
                alt_text="Health Points ของคุณ",
                template=ButtonsTemplate(
                    title=f"⭐ Oso-Points ของคุณ{name}",
                    text=f"สะสมแล้ว {points} แต้ม\n💰 แลกได้สูงสุด {discount} บาท\n(100 แต้ม = ส่วนลด 10 บาท)",
                    actions=[
                        PostbackTemplateAction(
                            label=f"🎁 แลกส่วนลด {discount} บาท" if discount > 0 else "⭐ สะสมต่อไป",
                            data=f"action=redeem&pts={(points//100)*100}&discount={discount}"
                        ),
                        PostbackTemplateAction(
                            label="📊 ประวัติการแลก",
                            data="action=redeem_history"
                        ),
                    ]
                )
            )
        )
        return

    # ══════════════════════════════════════════
    # ── 5. ปรึกษาเภสัชกร ──
    # ══════════════════════════════════════════
    if text == "ปรึกษาเภสัชกร":
        line_bot_api.reply_message(
            event.reply_token,
            TemplateSendMessage(
                alt_text="ปรึกษาเภสัชกร",
                template=ButtonsTemplate(
                    title="👩‍⚕️ ปรึกษาเภสัชกร",
                    text="เลือกบริการที่ต้องการค่ะ",
                    actions=[
                        PostbackTemplateAction(
                            label="💬 ถามเรื่องยาทั่วไป",
                            data="action=ask_pharmacist"
                        ),
                        PostbackTemplateAction(
                            label="📅 นัด Tele-pharmacy",
                            data="action=book_tele"
                        ),
                    ]
                )
            )
        )
        return

    # ── เปลี่ยนยา ──
    if text in ["เปลี่ยนยา", "แก้ไขยา"]:
        db.set_awaiting_med(user_id, 1)
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="💊 พิมพ์ชื่อยาใหม่ของคุณได้เลยค่ะ")
        )
        return

    # ── คำฉุกเฉิน ──
    urgent_words = ["ฉุกเฉิน", "ใจสั่น", "เจ็บหน้าอก", "หายใจไม่ออก", "หน้ามืด", "แพ้ยา"]
    if any(w in text for w in urgent_words):
        db.save_alert(user_id, "urgent", text)
        notify_pharmacist(user_id, f"🔴 URGENT: {text}")
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(
                text="⚠️ รับทราบค่ะ! กำลังแจ้งเภสัชกรทันทีเลยค่ะ\n\n🚨 หากอาการรุนแรงให้โทร 1669 ทันทีนะคะ\nเภสัชกรจะติดต่อกลับโดยเร็วที่สุดค่ะ 🏃‍♀️"
            )
        )
        return

    # ── Default ──
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(
            text="กดปุ่มเมนูด้านล่างได้เลยนะคะ 😊"
        )
    )

# ─────────────────────────── POSTBACK ───────────────────────────

@handler.add(PostbackEvent)
def handle_postback(event):
    raw  = event.postback.data
    data = dict(x.split("=") for x in raw.split("&") if "=" in x)
    action  = data.get("action", "")
    user_id = event.source.user_id
    user    = db.get_user(user_id)
    name    = user["name"] if user else "คุณ"

    # ── กินยาแล้ว (จากทั้ง reminder และ ตารางทานยา) ──
    if action == "taken":
        today_str = now_bkk().strftime("%Y-%m-%d")
        if db.check_taken_today(user_id, today_str):
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(
                    text=f"✅ คุณ{name} บันทึกการกินยาวันนี้ไปแล้วนะคะ\nกินยาพรุ่งนี้ตามเวลาด้วยนะคะ 💊"
                )
            )
            return
        db.log_medication(user_id, "taken")
        db.add_points(user_id, 10)
        points = db.get_points(user_id)
        now    = now_bkk().strftime("%H:%M น.")
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(
                text=f"เยี่ยมมากเลยค่ะ คุณ{name}! 🎉\nบันทึกการทานยาเวลา {now} แล้วค่ะ ✅\nได้รับ +10 Oso-Points\nสะสมแล้ว {points} แต้มค่ะ ✨"
            )
        )

    elif action == "skipped":
        db.log_medication(user_id, "skipped")
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(
                text="ไม่เป็นไรนะคะ 💙\nอย่าลืมกินยาในมื้อถัดไปด้วยนะคะ\nสุขภาพดีต้องกินยาสม่ำเสมอนะคะ 💊"
            )
        )

    # ── ADR ──
    elif action == "adr":
        db.set_adr_mode(user_id, 1)
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(
                text="📝 กรุณาพิมพ์อธิบายอาการที่ผิดปกติของคุณนะคะ\n\nเช่น: ปวดหัว มึนงง คลื่นไส้ ผื่นขึ้น หรืออาการอื่นๆ\n\n⚠️ หากอาการรุนแรงให้โทร 1669 ทันทีค่ะ"
            )
        )

    # ── บันทึกค่าสุขภาพ ──
    elif action == "log_health":
        h_type = data.get("type", "")
        type_map = {"bp": "ความดันโลหิต (เช่น 130/80)",
                    "sugar": "น้ำตาลในเลือด (เช่น 120 mg/dL)",
                    "weight": "น้ำหนัก (เช่น 65 kg)"}
        prompt = type_map.get(h_type, "ค่าสุขภาพ")
        db.set_health_log_mode(user_id, 1, h_type)
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=f"📊 พิมพ์ค่า{prompt}ของคุณได้เลยนะคะ")
        )

    # ── Weekly check-in ──
    elif action == "checkin_ok":
        db.log_medication(user_id, "checkin_ok")
        db.add_points(user_id, 20)
        points = db.get_points(user_id)
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(
                text=f"ดีมากเลยค่ะ คุณ{name}! 🌟\nได้รับ +20 Oso-Points\nสะสมแล้ว {points} แต้มค่ะ"
            )
        )

    # ── แลก Points ──
    elif action == "redeem":
        pts      = int(data.get("pts", 0))
        discount = int(data.get("discount", 0))
        if pts <= 0 or discount <= 0:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="⭐ ยังไม่มีแต้มพอค่ะ\nกินยาครบทุกวันเพื่อสะสมแต้มนะคะ 💊")
            )
            return
        db.redeem_points(user_id, pts, discount)
        remaining = db.get_points(user_id)
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(
                text=f"🎁 แลกส่วนลดสำเร็จค่ะ!\n\nใช้ {pts} แต้ม → ส่วนลด {discount} บาท\nแต้มคงเหลือ: {remaining} แต้ม\n\n📱 แสดง message นี้ให้เภสัชกรที่ร้านเพื่อรับส่วนลดได้เลยค่ะ 🏪"
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
            lines = ["📊 ประวัติการแลกแต้ม\n"]
            for h in history:
                lines.append(f"• {h['redeemed_at'][:10]}: {h['points_used']} แต้ม → -{h['discount_thb']} บาท")
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="\n".join(lines))
            )

    # ── ปรึกษาเภสัชกร ──
    elif action == "ask_pharmacist":
        notify_pharmacist(user_id, "💬 ผู้ป่วยต้องการปรึกษาเรื่องยา")
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(
                text="รับทราบค่ะ 💙\nเภสัชกรจะเข้ามาตอบคำถามของคุณเร็วๆ นี้นะคะ\nพิมพ์คำถามของคุณได้เลยค่ะ 😊"
            )
        )

    elif action == "book_tele":
        notify_pharmacist(user_id, "📅 ผู้ป่วยต้องการนัด Tele-pharmacy")
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(
                text="รับทราบค่ะ 📅\nเภสัชกรจะติดต่อกลับเพื่อนัดหมาย Tele-pharmacy ค่ะ\nบริการนี้รวมอยู่ใน Oso-Refill Box แล้วนะคะ 💊"
            )
        )

    # ── Refill ──
    elif action == "subscribe_refill":
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(
                text="🛒 Oso-Refill Box — 299 บาท/เดือน\n\n✅ จัดยารายเดือนส่งถึงบ้าน\n✅ Tele-pharmacy ก่อนยาหมด\n✅ ติดตามการใช้ยาอัตโนมัติ\n\nสนใจสมัครติดต่อเภสัชกรที่ร้านโอสถศาลาได้เลยค่ะ 🏪"
            )
        )

    elif action == "renew_refill":
        notify_pharmacist(user_id, "🔄 ผู้ป่วยต้องการต่ออายุ Oso-Refill Box")
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(
                text="รับทราบค่ะ 🔄\nเภสัชกรจะติดต่อกลับเพื่อต่ออายุ Oso-Refill Box ของคุณค่ะ 💊"
            )
        )

# ─────────────────────────── HELPERS ────────────────────────────

def send_med_reminder_to(user_id, reply_token=None):
    user = db.get_user(user_id)
    name = user["name"] if user else "คุณ"
    med  = user["med_name"] if user else "ยาตามใบสั่ง"
    msg  = TemplateSendMessage(
        alt_text="แจ้งเตือนกินยา",
        template=ButtonsTemplate(
            title=f"สวัสดีตอนเช้า คุณ{name} 🌅",
            text=f"ถึงเวลากิน {med} แล้วนะคะ 💊",
            actions=[
                PostbackTemplateAction(label="✅ กินแล้ว",        data="action=taken"),
                PostbackTemplateAction(label="⏰ ยังไม่ได้กิน",  data="action=skipped"),
                PostbackTemplateAction(label="⚠️ มีอาการผิดปกติ", data="action=adr"),
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
    patient  = db.get_user(patient_id)
    name     = patient["name"] if patient else "ไม่ระบุ"
    med      = patient["med_name"] if patient else "ไม่ระบุ"
    points   = db.get_points(patient_id)
    adr_line = f"\nอาการ: {adr_text}" if adr_text else ""
    line_bot_api.push_message(
        PHARMACIST_LINE_ID,
        TextSendMessage(
            text=f"🚨 แจ้งเตือนจาก Oso-Care\n━━━━━━━━━━━━━━━\nผู้ป่วย: {name}\nเหตุผล: {reason}{adr_line}\nยา: {med}\nOso-Points: {points} แต้ม\n━━━━━━━━━━━━━━━\nกรุณาติดต่อกลับโดยด่วนค่ะ"
        )
    )

# ─────────────────────────── SCHEDULER ──────────────────────────

def send_daily_reminder():
    for user in db.get_all_active_users():
        if not user["name"]:
            continue
        try:
            send_med_reminder_to(user["line_id"])
        except Exception as e:
            print(f"Reminder error: {e}")

def send_weekly_checkin():
    for user in db.get_all_active_users():
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
                            PostbackTemplateAction(label="😊 ปกติดี",         data="action=checkin_ok"),
                            PostbackTemplateAction(label="⚠️ มีอาการผิดปกติ", data="action=adr"),
                        ]
                    )
                )
            )
        except Exception as e:
            print(f"Checkin error: {e}")

scheduler = BackgroundScheduler(timezone="Asia/Bangkok")
scheduler.add_job(send_daily_reminder,  "cron", hour=8,  minute=0)
scheduler.add_job(send_weekly_checkin,  "cron", day_of_week="sun", hour=9, minute=0)
scheduler.start()

# ─────────────────────────── DASHBOARD ──────────────────────────

DASHBOARD_HTML = """
<!DOCTYPE html><html lang="th"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Oso-Care Dashboard</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',sans-serif;background:#f0f4f8;color:#333}
.header{background:linear-gradient(135deg,#2d7a4f,#5aab75);color:#fff;padding:20px 30px}
.header h1{font-size:1.5rem}.header p{opacity:.85;font-size:.9rem;margin-top:4px}
.container{max-width:1100px;margin:0 auto;padding:24px 16px}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:16px;margin-bottom:28px}
.stat-card{background:#fff;border-radius:12px;padding:20px;text-align:center;box-shadow:0 2px 8px rgba(0,0,0,.07)}
.stat-card .num{font-size:2rem;font-weight:700;color:#2d7a4f}
.stat-card .label{font-size:.85rem;color:#666;margin-top:4px}
.section{background:#fff;border-radius:12px;padding:20px;margin-bottom:24px;box-shadow:0 2px 8px rgba(0,0,0,.07)}
.section h2{font-size:1.1rem;margin-bottom:16px;color:#2d7a4f}
table{width:100%;border-collapse:collapse;font-size:.88rem}
th{background:#f7faf8;padding:10px 12px;text-align:left;font-weight:600;color:#444;border-bottom:2px solid #e8f0eb}
td{padding:10px 12px;border-bottom:1px solid #f0f0f0}
tr:hover td{background:#f9fdfb}
.badge{display:inline-block;padding:3px 10px;border-radius:20px;font-size:.78rem;font-weight:600}
.badge-urgent{background:#f8d7da;color:#721c24}
.badge-warn{background:#fff3cd;color:#856404}
.adh-bar{background:#e8f0eb;border-radius:4px;height:8px;width:100%}
.adh-fill{background:#2d7a4f;border-radius:4px;height:8px}
.adr-desc{font-size:.82rem;color:#888;margin-top:2px}
</style></head><body>
<div class="header"><h1>🏥 Oso-Care Dashboard</h1><p>ระบบติดตามผู้ป่วย — โอสถศาลา</p></div>
<div class="container">
<div class="stats">
  <div class="stat-card"><div class="num">{{total_users}}</div><div class="label">ผู้ป่วยทั้งหมด</div></div>
  <div class="stat-card"><div class="num">{{avg_adherence}}%</div><div class="label">Adherence เฉลี่ย</div></div>
  <div class="stat-card"><div class="num">{{alert_count}}</div><div class="label">แจ้งเตือนล่าสุด</div></div>
  <div class="stat-card"><div class="num">{{total_points}}</div><div class="label">Oso-Points รวม</div></div>
</div>
<div class="section"><h2>🚨 แจ้งเตือนล่าสุด</h2>
<table><thead><tr><th>ผู้ป่วย</th><th>ระดับ</th><th>รายละเอียด</th><th>เวลา</th></tr></thead><tbody>
{% for a in alerts %}
<tr><td>{{a.name}}</td>
<td>{% if a.level=='urgent' %}<span class="badge badge-urgent">🔴 ฉุกเฉิน</span>
{% else %}<span class="badge badge-warn">🟡 ผิดปกติ</span>{% endif %}</td>
<td>{{a.message}}{% if a.adr_description %}<div class="adr-desc">📝 {{a.adr_description}}</div>{% endif %}</td>
<td>{{a.created_at[:16]}}</td></tr>
{% endfor %}
{% if not alerts %}<tr><td colspan="4" style="text-align:center;color:#aaa;padding:20px">ยังไม่มีการแจ้งเตือนค่ะ ✅</td></tr>{% endif %}
</tbody></table></div>
<div class="section"><h2>👥 รายชื่อผู้ป่วยทั้งหมด</h2>
<table><thead><tr><th>ชื่อ</th><th>ยา</th><th>Adherence</th><th>กินแล้ว</th><th>ข้าม</th><th>แต้ม</th><th>ลงทะเบียน</th></tr></thead><tbody>
{% for u in users %}
<tr><td>{{u.name}}</td><td>{{u.med_name}}</td>
<td><div style="display:flex;align-items:center;gap:8px">
<div class="adh-bar"><div class="adh-fill" style="width:{{u.adherence}}%"></div></div>
<span style="font-size:.82rem;color:#555">{{u.adherence}}%</span></div></td>
<td style="color:#2d7a4f;font-weight:600">{{u.taken_count}}</td>
<td style="color:#c0392b">{{u.skipped_count}}</td>
<td>⭐ {{u.points}}</td>
<td style="color:#888;font-size:.82rem">{{u.registered_at[:10] if u.registered_at else '-'}}</td></tr>
{% endfor %}
{% if not users %}<tr><td colspan="7" style="text-align:center;color:#aaa;padding:20px">ยังไม่มีผู้ป่วยค่ะ</td></tr>{% endif %}
</tbody></table></div>
</div></body></html>
"""

def utc_to_bkk(dt_str):
    """แปลง UTC datetime string เป็น Bangkok time string"""
    if not dt_str:
        return dt_str
    try:
        # รองรับทั้ง "2026-03-07T09:33:00" และ "2026-03-07 09:33:00"
        dt_str_clean = dt_str.replace("T", " ")[:19]
        utc_dt = datetime.strptime(dt_str_clean, "%Y-%m-%d %H:%M:%S")
        utc_dt = pytz.utc.localize(utc_dt)
        bkk_dt = utc_dt.astimezone(BANGKOK)
        return bkk_dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return dt_str[:16]

@app.route("/dashboard")
def dashboard():
    if request.args.get("pw","") != DASHBOARD_PASSWORD:
        return "<h3 style='font-family:sans-serif;padding:40px;color:#c0392b'>❌ Password ไม่ถูกต้องค่ะ<br><small>เช่น /dashboard?pw=osocare2026</small></h3>", 403
    users          = db.get_all_users_detail()
    alerts         = db.get_recent_alerts(20)

    # แปลงเวลาทุก alert เป็น Bangkok time
    for a in alerts:
        a["created_at"] = utc_to_bkk(a.get("created_at", ""))

    # แปลงเวลาลงทะเบียนของ users ด้วย
    for u in users:
        if u.get("registered_at"):
            u["registered_at"] = utc_to_bkk(u["registered_at"])

    total_users    = len(users)
    avg_adherence  = round(sum(u["adherence"] for u in users)/total_users) if total_users else 0
    total_points   = sum(u["points"] for u in users)
    return render_template_string(
        DASHBOARD_HTML, users=users, alerts=alerts,
        total_users=total_users, avg_adherence=avg_adherence,
        alert_count=len(alerts), total_points=total_points
    )


@app.route("/reset_menu")
def reset_menu():
    pw = request.args.get("pw", "")
    if pw != DASHBOARD_PASSWORD:
        return "Unauthorized", 403
    setup_rich_menu()
    return "Rich Menu reset done! Check Railway logs.", 200

@app.route("/", methods=["GET"])
def index():
    return "Oso-Care Bot is running! 💊"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
