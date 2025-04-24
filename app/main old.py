import os
import json
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from jinja2 import Environment, FileSystemLoader
from openai import OpenAI
import pdfkit
from dotenv import load_dotenv

# ─── 1. Environment ─────────────────────────────────────────────────
load_dotenv()  # expects OPENAI_API_KEY, WKHTMLTOPDF_PATH in .env

# ─── 2. OpenAI client & PDF config ──────────────────────────────────
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
PDFKIT_CONFIG = pdfkit.configuration(
    wkhtmltopdf=os.getenv("WKHTMLTOPDF_PATH")
)

# ─── 3. FastAPI setup ───────────────────────────────────────────────
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],    # tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── 4. Serve UI ────────────────────────────────────────────────────
# a) Root returns your index.html
@app.get("/")
def serve_ui():
    return FileResponse("static/index.html", media_type="text/html")

# b) Mount the rest of static files under /static
app.mount("/static", StaticFiles(directory="static"), name="static")

# ─── 5. Jinja2 loader ────────────────────────────────────────────────
jinja_env = Environment(loader=FileSystemLoader("templates"))

# ─── 6. Smoke-test PDF ──────────────────────────────────────────────
@app.get("/testpdf")
def testpdf():
    html = "<h1>PDF test</h1><p>If you see this, wkhtmltopdf is working.</p>"
    out = "tmp/test.pdf"
    pdfkit.from_string(html, out, configuration=PDFKIT_CONFIG)
    return FileResponse(out, media_type="application/pdf")

# ─── 7. Voice → PDF endpoint ────────────────────────────────────────
@app.post("/transcribe")
async def transcribe(file: UploadFile = File(...)):
    try:
        # a) Save upload
        base, _ = os.path.splitext(file.filename)
        in_path = f"tmp/{file.filename}"
        with open(in_path, "wb") as f:
            f.write(await file.read())

        # b) Whisper (v1 SDK)
        resp = client.audio.transcriptions.create(
            model="whisper-1",
            file=open(in_path, "rb")
        )
        transcript = resp.text

        # c) Extract form fields via chat
        prompt = (
            "Extract these fields into JSON keys exactly as named:\n"
            # list your form field names here
            "follow_up_date, audiologist, provider_number, device_usage, cosi_outcomes, reprogramming\n\n"
            f"Transcript:\n{transcript}"
        )
        chat = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Extract follow-up form data into JSON."},
                {"role": "user",   "content": prompt}
            ]
        )
        data = json.loads(chat.choices[0].message.content)

        # d) Render Jinja2 template
        template = jinja_env.get_template("fitting_followup.html")
        html = template.render(**data)

        # e) HTML → PDF
        out_pdf = f"tmp/filled_{base}.pdf"
        pdfkit.from_string(html, out_pdf, configuration=PDFKIT_CONFIG)

        # f) Return to browser
        return FileResponse(out_pdf, media_type="application/pdf")

    except Exception as e:
        import traceback; traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})
