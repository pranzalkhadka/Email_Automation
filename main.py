import os
from dotenv import load_dotenv
import imaplib
import smtplib
import email
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langchain_groq import ChatGroq
from langchain.schema import HumanMessage
import google.generativeai as genai
import pdfkit
import tempfile
import shutil

load_dotenv()

EMAIL_ADDRESS = os.getenv('EMAIL_ADDRESS')
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD')
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
GEMINI_API_KEY = "AIzaSyBXiMNmOVmrCnOCP-sjGcaPnL1bTfzDI2Y"  

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

genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel("gemini-1.5-pro")

extraction_prompt = """
Extract ALL text and form structure from this image with maximum detail. Include:
1. All headers, labels, and text exactly as they appear
2. All form fields (text inputs, checkboxes, etc.)
3. The layout structure (what elements are grouped together)
4. Any special formatting (bold, larger text, etc.)
5. The overall organization of the form (left/right columns, sections)

Return this as a detailed JSON structure that could be used to recreate the form.
"""

generation_prompt = """
Create a complete HTML and CSS implementation of this form based on the provided structure.
The HTML should:
1. Match the original form's layout as closely as possible
2. Include all form fields with proper types (text inputs, checkboxes, etc.)
3. Maintain the visual hierarchy (headers, sections)
4. Use CSS to style it cleanly with appropriate spacing and alignment

Return ONLY the complete HTML code with embedded CSS in this format:
<!DOCTYPE html>
<html>
<head>
<style>
/* CSS here */
</style>
</head>
<body>
<!-- Form HTML here -->
</body>
</html>
"""

def generate_pdf(html_path, output_pdf_path):
    try:
        pdfkit.from_file(html_path, output_pdf_path)
        print(f"PDF generated at {output_pdf_path}")
    except Exception as e:
        print(f"PDF generation error: {e}")

def process_image_to_pdf(image_path, temp_dir):
    """
    Process an image to extract form data, generate HTML, and create a PDF.
    Returns the path to the generated PDF or None if processing fails.
    """
    output_html_path = os.path.join(temp_dir, f"processed_{os.path.basename(image_path)}.html")
    output_pdf_path = os.path.join(temp_dir, f"processed_{os.path.basename(image_path)}.pdf")

    try:
        image_file = genai.upload_file(image_path)

        try:
            extraction_response = gemini_model.generate_content([extraction_prompt, image_file])
            extracted_data = extraction_response.text

            generation_response = gemini_model.generate_content([generation_prompt, extracted_data])
            html_content = generation_response.text

            with open(output_html_path, "w") as f:
                f.write(html_content)
            print(f"HTML saved to {output_html_path}")

            generate_pdf(output_html_path, output_pdf_path)
            return output_pdf_path

        finally:
            genai.delete_file(image_file.name)

    except Exception as e:
        print(f"Error processing image {image_path}: {e}")
        return None

def fetch_unread_email():
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        mail.select("inbox")

        _, data = mail.search(None, 'UNSEEN')
        email_ids = data[0].split()

        if not email_ids:
            return None, None, None, [], None

        latest_email_id = email_ids[-1]
        _, data = mail.fetch(latest_email_id, "(RFC822)")

        raw_email = data[0][1]
        message = email.message_from_bytes(raw_email)

        sender = message["From"]
        subject = message["Subject"]
        body = ""
        attachments = []
        temp_dir = tempfile.mkdtemp()  

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
                        if content_type.startswith("image/"):
                            image_path = os.path.join(temp_dir, filename)
                            with open(image_path, "wb") as f:
                                f.write(attachment_data)

        else:
            body = message.get_payload(decode=True).decode()

        mail.logout()
        return sender, subject, body, attachments, temp_dir
    except Exception as e:
        print("Error fetching email:", e)
        return None, None, None, [], None

def generate_response(email_body):
    chat = ChatGroq(groq_api_key=GROQ_API_KEY, model_name=MODEL_NAME)
    response = chat.invoke([HumanMessage(content=f"Read the email and give a respectful reply: {email_body}")])
    return response.content

def send_email(to_email, subject, body, processed_pdf_path, temp_dir):
    try:
        msg = MIMEMultipart()
        msg["From"] = EMAIL_ADDRESS
        msg["To"] = to_email
        msg["Subject"] = "Re: " + subject

        msg.attach(MIMEText(body, "plain"))

        if processed_pdf_path and os.path.exists(processed_pdf_path):
            with open(processed_pdf_path, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                "attachment; filename=processed_form.pdf"
            )
            msg.attach(part)

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        server.sendmail(EMAIL_ADDRESS, to_email, msg.as_string())
        server.quit()

        print("Email sent successfully!")
    except Exception as e:
        print("Error sending email:", e)
    finally:
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
            print(f"Cleaned up temporary files in {temp_dir}")

@app.get("/")
def home():
    return {"Status": "Running"}

@app.post("/process-email")
async def process_email():
    sender, subject, body, attachments, temp_dir = fetch_unread_email()
    if sender and body:
        print(f"New email from: {sender}\nSubject: {subject}\nBody: {body}\nAttachments: {[att['filename'] for att in attachments]}")

        processed_pdf_path = None
        for attachment in attachments:
            if attachment["content_type"].startswith("image/"):
                image_path = os.path.join(temp_dir, attachment["filename"])
                processed_pdf_path = process_image_to_pdf(image_path, temp_dir)
                break  

        response_text = generate_response(body)
        send_email(sender, subject, response_text, processed_pdf_path, temp_dir)

        return {"status": "success", "message": "Email processed successfully."}
    else:
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
        return {"status": "failed", "message": "No unread emails."}