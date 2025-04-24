import os
import json
import re
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from jinja2 import Environment, FileSystemLoader
from openai import OpenAI
import pdfkit
from dotenv import load_dotenv
from faster_whisper import WhisperModel

# ─── 1. Load environment variables ─────────────────────────────────
load_dotenv()  # expects OPENAI_API_KEY and WKHTMLTOPDF_PATH in .env

# ─── 2. Initialize local Whisper for transcription ─────────────────
whisper_model = WhisperModel("base")
def transcribe_audio(audio_path: str) -> str:
    segments, _ = whisper_model.transcribe(audio_path)
    return " ".join(segment.text for segment in segments)

# ─── 3. Configure OpenAI client and PDF generator ────────────────
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
PDFKIT_CONFIG = pdfkit.configuration(
    wkhtmltopdf=os.getenv("WKHTMLTOPDF_PATH")
)

# ─── 4. FastAPI application setup ───────────────────────────────────
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve UI
@app.get("/")
def serve_ui():
    return FileResponse("static/index.html", media_type="text/html")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Setup Jinja2
jinja_env = Environment(loader=FileSystemLoader("templates"))

# ─── 5. Quick PDF test endpoint ────────────────────────────────────
@app.get("/testpdf")
def testpdf():
    html = "<h1>PDF test</h1><p>wkhtmltopdf is working.</p>"
    out = "tmp/test.pdf"
    pdfkit.from_string(html, out, configuration=PDFKIT_CONFIG)
    return FileResponse(out, media_type="application/pdf")

# ─── 6. Transcription + Template Selection + LLM + PDF ─────────────
@app.post("/transcribe")
async def transcribe(file: UploadFile = File(...)):
    try:
        # a) Save uploaded audio
        base, _ = os.path.splitext(file.filename)
        in_path = f"tmp/{file.filename}"
        with open(in_path, "wb") as f:
            f.write(await file.read())

        # b) Transcribe locally
        transcript = transcribe_audio(in_path)

        # c) Parse out template directive (first line: "Template: name")
        #    Build a map of available templates
        tmpl_map = {os.path.splitext(f)[0].lower(): f
                    for f in os.listdir("templates") if f.endswith(".html")}
        m = re.match(r"template\s*[:\-]?\s*([\w ]+)", transcript, re.IGNORECASE)
        if m:
            key = m.group(1).strip().lower().replace(" ", "_")
            transcript_body = transcript[m.end():].strip()
            tpl_file = tmpl_map.get(key)
            if not tpl_file:
                return JSONResponse(status_code=400, content={
                    "error": f"Unknown template '{m.group(1)}'. Available: {list(tmpl_map.keys())}"})
        else:
            # default to first template
            tpl_file = list(tmpl_map.values())[0]
            transcript_body = transcript

        # d) Build LLM prompt to extract all form fields
        prompt = (
            "Extract the following fields into JSON only, for template '" + tpl_file + "':\n"
            "[list your expected keys here]\n\n"
            f"Transcript:\n{transcript_body}"
        )
        chat = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Extract form data into JSON only."},
                {"role": "user",   "content": prompt}
            ]
        )
        raw = chat.choices[0].message.content
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return JSONResponse(status_code=500, content={"error": "Invalid JSON from LLM", "raw": raw})

        # e) Render the selected Jinja2 template
        template = jinja_env.get_template(tpl_file)
        html = template.render(**data)

        # f) Generate PDF
        out_pdf = f"tmp/filled_{base}.pdf"
        pdfkit.from_string(html, out_pdf, configuration=PDFKIT_CONFIG)

        # g) Return the PDF to the client
        return FileResponse(out_pdf, media_type="application/pdf")

    except Exception as e:
        import traceback; traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})
