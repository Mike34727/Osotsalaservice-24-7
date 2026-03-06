import os
from flask import Flask, request, abort
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

line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

db.init_db()

@app.route("/webhook", methods=["POST"])
def webhook():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK"

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

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    text = event.message.text.strip()
    user = db.get_user(user_id)

    if user and not user["name"]:
        db.update_user_name(user_id, text)
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(
                text=f"ขอบคุณค่ะ คุณ{text} 🙏\nลงทะเบียนเรียบร้อยแล้ว!\n\nระบบจะส่งแจ้งเตือนกินยาทุกเช้า 08:00 น. นะคะ 💊\nถ้ามีอาการผิดปกติพิมพ์ว่า ฉุกเฉิน ได้เลยค่ะ"
            )
        )
        return

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

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(
            text="รับทราบค่ะ 😊\nถ้ามีอาการผิดปกติพิมพ์ว่า ฉุกเฉิน ได้เลยนะคะ"
        )
    )

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
        db.save_alert(user_id, "warning", "ผู้ป่วยกดแจ้งอาการผิดปกติ")
        notify_pharmacist(user_id, "🟡 ผู้ป่วยกดแจ้งอาการผิดปกติ")
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="รับทราบค่ะ ⚠️\nเภสัชกรจะติดต่อกลับเร็วๆ นี้นะคะ 📞")
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

def notify_pharmacist(patient_id, reason):
    if not PHARMACIST_LINE_ID:
        return
    patient = db.get_user(patient_id)
    name = patient["name"] if patient else "ไม่ระบุ"
    med = patient["med_name"] if patient else "ไม่ระบุ"
    points = db.get_points(patient_id)
    line_bot_api.push_message(
        PHARMACIST_LINE_ID,
        TextSendMessage(
            text=f"🚨 แจ้งเตือนจาก Oso-Care\n━━━━━━━━━━━━━━━\nผู้ป่วย: {name}\nเหตุผล: {reason}\nยา: {med}\nHealth Points: {points} แต้ม\n━━━━━━━━━━━━━━━\nกรุณาติดต่อกลับโดยด่วนค่ะ"
        )
    )

def send_daily_reminder():
    users = db.get_all_active_users()
    for user in users:
        name = user["name"] or "คุณ"
        med = user["med_name"]
        try:
            line_bot_api.push_message(
                user["line_id"],
                TemplateSendMessage(
                    alt_text="แจ้งเตือนกินยาประจำวัน",
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
            )
        except Exception as e:
            print(f"Error: {e}")

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
            print(f"Error: {e}")

scheduler = BackgroundScheduler(timezone="Asia/Bangkok")
scheduler.add_job(send_daily_reminder, "cron", hour=8, minute=0)
scheduler.add_job(send_weekly_checkin, "cron", day_of_week="sun", hour=9, minute=0)
scheduler.start()

@app.route("/", methods=["GET"])
def index():
    return "Oso-Care Bot is running! 💊"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
