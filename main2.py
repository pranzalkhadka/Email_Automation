import os
from dotenv import load_dotenv
import imaplib
import smtplib
import email
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

EMAIL_ADDRESS = os.getenv('EMAIL_ADDRESS')
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD')
GROQ_API_KEY = os.getenv('GROQ_API_KEY')

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

DOWNLOAD_DIR = "downloads"
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

def fetch_unread_email():
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        mail.select("inbox")

        _, data = mail.search(None, 'UNSEEN')
        email_ids = data[0].split()

        if not email_ids:
            return None, None, None, None, None

        latest_email_id = email_ids[-1]
        _, data = mail.fetch(latest_email_id, "(RFC822)")

        raw_email = data[0][1]
        message = email.message_from_bytes(raw_email)

        sender = message["From"]
        subject = message["Subject"]
        message_id = message["Message-ID"] 
        body = ""
        pdf_path = None

        if message.is_multipart():
            for part in message.walk():
                if part.get_content_type() == "text/plain":
                    body = part.get_payload(decode=True).decode()
                elif part.get_content_type() == "application/pdf":
                    filename = part.get_filename()
                    if not filename:
                        filename = f"attachment_{latest_email_id}.pdf"
                    filename = "".join(c if c.isalnum() or c in "._-" else "_" for c in filename)
                    pdf_path = os.path.join(DOWNLOAD_DIR, filename)
                    with open(pdf_path, "wb") as f:
                        f.write(part.get_payload(decode=True))
                    print(f"PDF saved to: {pdf_path}")

        mail.logout()
        return sender, subject, body, pdf_path, message_id
    except Exception as e:
        print("Error fetching email:", e)
        return None, None, None, None, None



def generate_response(email_body, pdf_path=None):
    # Hardcoded response
    reply = """Hi Pranjal,

I've received your files for the Lending Club Credit Risk Model. I will analyze these documents and get back to you with my assessment.

Thank you for the submission.

Regards,
Sarah Wilson
Model Risk Management"""
    
    return reply

def send_email(to_email, subject, original_body, reply_body, original_message_id=None):
    try:
        if subject is None:
            subject = "No subject"
            
        msg = MIMEMultipart()
        msg["From"] = EMAIL_ADDRESS
        msg["To"] = to_email
        
        clean_subject = subject.replace("Re:", "").strip()
        msg["Subject"] = f"Re: {clean_subject}"

        if original_message_id:
            msg["In-Reply-To"] = original_message_id
            msg["References"] = original_message_id
        
        full_body = f"{reply_body}\n\n----- Original Message -----\n{original_body}"
        
        msg.attach(MIMEText(full_body, "plain"))

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        server.sendmail(EMAIL_ADDRESS, to_email, msg.as_string())
        server.quit()

        print("Email replied successfully in same thread!")
    except Exception as e:
        print("Error replying to email:", e)


@app.get("/")
def home():
    return {"Status": "Running"}


@app.post("/process-email")
async def process_email():
    sender, subject, body, pdf_path, message_id = fetch_unread_email()
    if sender and body:
        print(f"New email from: {sender}\nSubject: {subject}\nBody: {body}")
        if pdf_path:
            print(f"PDF attachment saved at: {pdf_path}")

        response_text = generate_response(body, pdf_path)
        send_email(sender, subject, body, response_text, message_id)

        return {
            "status": "success",
            "message": "Email replied in same thread.",
            "sender": sender,
            "subject": subject,
            "body": body,
            "pdf_path": pdf_path
        }
    else:
        return {"status": "failed", "message": "No unread emails."}