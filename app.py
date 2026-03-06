import os
from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi,
    ReplyMessageRequest, PushMessageRequest,
    TextMessage, TemplateMessage,
    ButtonsTemplate, PostbackAction, URIAction
)
from linebot.v3.webhooks import (
    MessageEvent, FollowEvent,
    PostbackEvent, TextMessageContent
)
from apscheduler.schedulers.background import BackgroundScheduler
import database as db

app = Flask(__name__)

# ===== ตั้งค่า Token =====
CHANNEL_SECRET = os.environ.get("CHANNEL_SECRET", "")
CHANNEL_ACCESS_TOKEN = os.environ.get("CHANNEL_ACCESS_TOKEN", "")
PHARMACIST_LINE_ID = os.environ.get("PHARMACIST_LINE_ID", "")

configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

# ===== เริ่ม Database =====
db.init_db()

# ===== Webhook =====
@app.route("/webhook", methods=["POST"])
def webhook():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK"

# ===== เมื่อมีคนกด Add Friend =====
@handler.add(FollowEvent)
def handle_follow(event):
    user_id = event.source.user_id
    db.save_user(user_id)

    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message(ReplyMessageRequest(
            reply_token=event.reply_token,
            messages=[
                TextMessage(text="สวัสดีค่ะ 👋 ยินดีต้อนรับสู่ Oso-Care\nระบบดูแลสุขภาพจากโอสถศาลา 💊"),
                TextMessage(text="กรุณาพิมพ์ชื่อ-นามสกุลของคุณเพื่อลงทะเบียนนะคะ\nเช่น: สมชาย มีสุข")
            ]
        ))

# ===== เมื่อผู้ใช้พิมพ์ข้อความ =====
@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_id = event.source.user_id
    text = event.message.text.strip()
    user = db.get_user(user_id)

    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)

        # ถ้ายังไม่มีชื่อ → รับชื่อ
        if user and not user["name"]:
            db.update_user_name(user_id, text)
            line_bot_api.reply_message(ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(
                    text=f"ขอบคุณค่ะ คุณ{text} 🙏\nลงทะเบียนเรียบร้อยแล้ว!\n\nระบบจะส่งแจ้งเตือนกินยาทุกเช้า 08:00 น. นะคะ 💊\nถ้ามีอาการผิดปกติพิมพ์ว่า 'ฉุกเฉิน' ได้เลยค่ะ"
                )]
            ))
            return

        # ถ้าพิมพ์คำว่า ฉุกเฉิน
        if "ฉุกเฉิน" in text or "ใจสั่น" in text or "เจ็บหน้าอก" in text:
            notify_pharmacist(user_id, f"🔴 URGENT: {text}", line_bot_api)
            db.save_alert(user_id, "urgent", text)
            line_bot_api.reply_message(ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(
                    text="⚠️ รับทราบค่ะ! กำลังแจ้งเภสัชกรทันทีเลยค่ะ\nรอสักครู่นะคะ เภสัชกรจะติดต่อกลับโดยเร็วที่สุดค่ะ 🏃‍♀️"
                )]
            ))
            return

        # คำถามทั่วไป
        line_bot_api.reply_message(ReplyMessageRequest(
            reply_token=event.reply_token,
            messages=[TextMessage(
                text="รับทราบค่ะ 😊\nถ้ามีอาการผิดปกติพิมพ์ว่า 'ฉุกเฉิน' ได้เลยนะคะ\nหรือรอแจ้งเตือนกินยาตอนเช้า 08:00 น. ค่ะ"
            )]
        ))

# ===== เมื่อกดปุ่ม Postback =====
@handler.add(PostbackEvent)
def handle_postback(event):
    data = dict(x.split("=") for x in event.postback.data.split("&"))
    action = data.get("action", "")
    user_id = event.source.user_id
    user = db.get_user(user_id)
    name = user["name"] if user else "คุณ"

    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)

        if action == "taken":
            db.log_medication(user_id, "taken")
            db.add_points(user_id, 10)
            points = db.get_points(user_id)
            line_bot_api.reply_message(ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(
                    text=f"เยี่ยมมากเลยค่ะ คุณ{name}! 🎉\nได้รับ +10 Health Points\nสะสมแล้ว {points} แต้มค่ะ ✨"
                )]
            ))

        elif action == "skipped":
            db.log_medication(user_id, "skipped")
            line_bot_api.reply_message(ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(
                    text="ไม่เป็นไรนะคะ 💙\nอย่าลืมกินยาในมื้อถัดไปด้วยนะคะ\nถ้าไม่สบายหรือมีอาการอะไรพิมพ์บอกได้เลยค่ะ"
                )]
            ))

        elif action == "adr":
            db.save_alert(user_id, "warning", "ผู้ป่วยรายงานอาการผิดปกติผ่านปุ่ม")
            notify_pharmacist(user_id, "🟡 ผู้ป่วยกดแจ้งอาการผิดปกติ", line_bot_api)
            line_bot_api.reply_message(ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(
                    text="รับทราบค่ะ ⚠️\nเภสัชกรจะติดต่อกลับเร็วๆ นี้นะคะ\nถ้าเร่งด่วนมากโทรหาเราได้เลยค่ะ 📞"
                )]
            ))

        elif action == "checkin_ok":
            db.log_medication(user_id, "checkin_ok")
            db.add_points(user_id, 20)
            points = db.get_points(user_id)
            line_bot_api.reply_message(ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(
                    text=f"ดีมากเลยค่ะ คุณ{name}! 🌟\nได้รับ +20 Health Points สำหรับการเช็กอินสัปดาห์นี้\nสะสมแล้ว {points} แต้มค่ะ"
                )]
            ))

# ===== แจ้งเตือนเภสัชกร =====
def notify_pharmacist(patient_id, reason, line_bot_api):
    if not PHARMACIST_LINE_ID:
        return
    patient = db.get_user(patient_id)
    name = patient["name"] if patient else "ไม่ระบุ"
    med = patient["med_name"] if patient else "ไม่ระบุ"
    points = db.get_points(patient_id)

    line_bot_api.push_message(PushMessageRequest(
        to=PHARMACIST_LINE_ID,
        messages=[TextMessage(
            text=f"""🚨 แจ้งเตือนจาก Oso-Care
━━━━━━━━━━━━━━━
ผู้ป่วย: {name}
เหตุผล: {reason}
ยา: {med}
Health Points: {points} แต้ม
━━━━━━━━━━━━━━━
กรุณาติดต่อกลับโดยด่วนค่ะ"""
        )]
    ))

# ===== Scheduler: ส่ง Reminder ทุกวัน =====
def send_daily_reminder():
    users = db.get_all_active_users()
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        for user in users:
            name = user["name"] or "คุณ"
            med = user["med_name"]
            try:
                line_bot_api.push_message(PushMessageRequest(
                    to=user["line_id"],
                    messages=[TemplateMessage(
                        alt_text="แจ้งเตือนกินยาประจำวัน",
                        template=ButtonsTemplate(
                            title=f"สวัสดีตอนเช้า คุณ{name} 🌅",
                            text=f"ถึงเวลากิน {med} แล้วนะคะ\n💊 กินหลังอาหารเช้าเลยค่ะ",
                            actions=[
                                PostbackAction(label="✅ กินแล้ว", data="action=taken"),
                                PostbackAction(label="⏰ ยังไม่ได้กิน", data="action=skipped"),
                                PostbackAction(label="⚠️ มีอาการผิดปกติ", data="action=adr")
                            ]
                        )
                    )]
                ))
            except Exception as e:
                print(f"Error sending to {user['line_id']}: {e}")

def send_weekly_checkin():
    users = db.get_all_active_users()
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        for user in users:
            name = user["name"] or "คุณ"
            try:
                line_bot_api.push_message(PushMessageRequest(
                    to=user["line_id"],
                    messages=[TemplateMessage(
                        alt_text="เช็กอินประจำสัปดาห์",
                        template=ButtonsTemplate(
                            title=f"💙 ครบ 7 วันแล้วนะคะ คุณ{name}!",
                            text="ช่วงสัปดาห์ที่ผ่านมาเป็นยังไงบ้างคะ?",
                            actions=[
                                PostbackAction(label="😊 ปกติดี ไม่มีอะไร", data="action=checkin_ok"),
                                PostbackAction(label="⚠️ มีอาการผิดปกติ", data="action=adr")
                            ]
                        )
                    )]
                ))
            except Exception as e:
                print(f"Error sending to {user['line_id']}: {e}")

scheduler = BackgroundScheduler(timezone="Asia/Bangkok")
scheduler.add_job(send_daily_reminder, "cron", hour=8, minute=0)
scheduler.add_job(send_weekly_checkin, "cron", day_of_week="sun", hour=9, minute=0)
scheduler.start()

@app.route("/", methods=["GET"])
def index():
    return "Oso-Care Bot is running! 💊"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
