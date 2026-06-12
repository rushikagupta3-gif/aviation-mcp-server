"""FastAPI backend for the Multimodal Field Report Generator.

POST /generate  { notes, transcript, ocr_text }  ->  report dict
Uses Google Gemini (free tier) with structured JSON output.
"""
from __future__ import annotations

import json
import os

import google.generativeai as genai
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

genai.configure(api_key=os.environ["GEMINI_API_KEY"])
model = genai.GenerativeModel("gemini-1.5-flash")

app = FastAPI(title="Field Report Generator API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

SYSTEM_PROMPT = """\
You are an expert aviation field inspector generating professional site inspection reports.

Given observations from a site inspection (typed notes, voice transcript, and/or OCR text \
from photos), generate a comprehensive, regulation-grounded field report with 3-4 sections.

Guidelines:
- Title: clear, descriptive (e.g. "Runway Lighting Infrastructure Inspection Report")
- Metadata: inspector "Auto-generated", status "DRAFT"
- Sections: cover Observations, Compliance Assessment, Findings & Risk, Recommendations
- Each section body: 2-4 sentences, professional tone, specific to the observations given
- Citations: reference relevant aviation standards (e.g. CAAS-AIC.pdf, ICAO-Annex14.pdf,
  FAR-Part139.pdf, CAP168.pdf). Assign sequential IDs starting at 1.
- References array: every citation ID must have a matching entry with a realistic snippet
  (quoted regulatory text, 10-20 words)
- All citation IDs in sections must appear in the references array

Be specific to the actual content in the observations — do not generate generic filler.

You MUST respond with ONLY valid JSON in exactly this structure, no markdown, no extra text:
{
  "title": "string",
  "metadata": {"inspector": "string", "status": "string"},
  "sections": [
    {
      "heading": "string",
      "body": "string",
      "citations": [{"id": 1, "source": "string", "chunk_id": "string"}]
    }
  ],
  "references": [
    {"id": 1, "source": "string", "chunk_id": "string", "snippet": "string"}
  ]
}\
"""


class GenerateRequest(BaseModel):
    notes: str = ""
    transcript: str = ""
    ocr_text: str = ""


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/generate")
def generate_report(request: GenerateRequest):
    parts = [
        f"Field Notes:\n{request.notes}" if request.notes.strip() else "",
        f"Voice Transcript:\n{request.transcript}" if request.transcript.strip() else "",
        f"OCR Text from Photos:\n{request.ocr_text}" if request.ocr_text.strip() else "",
    ]
    combined = "\n\n".join(p for p in parts if p).strip()

    if not combined:
        raise HTTPException(status_code=400, detail="At least one input field is required.")

    prompt = (
        SYSTEM_PROMPT
        + "\n\nGenerate a field inspection report based on these observations:\n\n"
        + combined
    )

    response = model.generate_content(prompt)
    text = response.text.strip()

    # Strip markdown code fences if Gemini wraps the JSON
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    return json.loads(text)
