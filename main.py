import os
from dotenv import load_dotenv
import imaplib
import smtplib
import email
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


ATTACHMENT_DIR = "attachments"
os.makedirs(ATTACHMENT_DIR, exist_ok=True)

load_dotenv()

EMAIL_ADDRESS = os.getenv('EMAIL_ADDRESS')
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD')
# GROQ_API_KEY = os.getenv('GROQ_API_KEY')

IMAP_SERVER = "imap.gmail.com"
SMTP_SERVER = "smtp.gmail.com"
IMAP_PORT = 993
SMTP_PORT = 587
MODEL_NAME = "llama-3.3-70b-versatile"

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def fetch_unread_email():
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        mail.select("inbox")

        _, data = mail.search(None, 'ALL')
        email_ids = data[0].split()

        if not email_ids:
            return None, None, None, []

        latest_email_id = email_ids[-1]
        _, data = mail.fetch(latest_email_id, "(RFC822)")

        raw_email = data[0][1]
        message = email.message_from_bytes(raw_email)

        sender = message["From"]
        subject = message["Subject"]
        email_id = message["Message-ID"]
        timestamp = message["Date"]
        body = ""
        attachments = []

        if message.is_multipart():
            for part in message.walk():
                content_type = part.get_content_type()
                disposition = str(part.get("Content-Disposition"))

                if content_type == "text/plain" and "attachment" not in disposition:
                    body = part.get_payload(decode=True).decode()
                
                if "attachment" in disposition:
                    filename = part.get_filename()
                    if filename:
                        attachment_data = part.get_payload(decode=True)
                        attachments.append({
                            "filename": filename,
                            "data": attachment_data,
                            "content_type": content_type
                        })

        else:
            body = message.get_payload(decode=True).decode()

        mail.logout()
        return sender, subject, body, email_id, timestamp, attachments
    except Exception as e:
        print("Error fetching email:", e)
        return None, None, None, None, None, []


def generate_response(email_body):
    reply = """Hi Bikram,

I've received your files. I will analyze them shortly.

Regards,
Sarah Wilson
Model Risk Management"""
    
    return reply

def send_email(to_email, subject, body):
    try:
        msg = MIMEMultipart()
        msg["From"] = EMAIL_ADDRESS
        msg["To"] = to_email
        msg["Subject"] = "Re: " + subject

        msg.attach(MIMEText(body, "plain"))

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        server.sendmail(EMAIL_ADDRESS, to_email, msg.as_string())
        server.quit()

        print("Email sent successfully!")
    except Exception as e:
        print("Error sending email:", e)


@app.get("/")
def home():
    return {"Status": "Running"}


@app.post("/process-email")
async def process_email():
    sender, subject, body, email_id, timestamp, attachments = fetch_unread_email()
    if sender and body:
        print(f"New email from: {sender}\nSubject: {subject}\nBody: {body}\nAttachments: {[att['filename'] for att in attachments]}")

        saved_files = []
        for att in attachments:
            if att["filename"].lower().endswith(('.csv', '.md')):
                file_path = os.path.join(ATTACHMENT_DIR, att["filename"])
                with open(file_path, "wb") as f:
                    f.write(att["data"])
                saved_files.append(file_path)

        response_text = generate_response(body)
        send_email(sender, subject, response_text)

        return {
            "status": "success",
            "message": "Email processed successfully.",
            "saved_files": saved_files,
            "email_body": body,
            "email_subject": subject,
            "email_sender": sender,
            "email_id": email_id,
            "email_timestamp": timestamp,
        }
    else:
        return {"status": "failed", "message": "No unread emails."}