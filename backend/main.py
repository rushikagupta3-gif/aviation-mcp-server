"""FastAPI backend for the Multimodal Field Report Generator.

POST /generate  { notes, transcript, ocr_text }  ->  report dict
Uses Claude claude-opus-4-8 with adaptive thinking + structured JSON output.
"""
from __future__ import annotations

import json
import os

import anthropic
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Field Report Generator API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

REPORT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "metadata": {
            "type": "object",
            "properties": {
                "inspector": {"type": "string"},
                "status": {"type": "string"},
            },
            "required": ["inspector", "status"],
            "additionalProperties": False,
        },
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "heading": {"type": "string"},
                    "body": {"type": "string"},
                    "citations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "integer"},
                                "source": {"type": "string"},
                                "chunk_id": {"type": "string"},
                            },
                            "required": ["id", "source", "chunk_id"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["heading", "body", "citations"],
                "additionalProperties": False,
            },
        },
        "references": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "source": {"type": "string"},
                    "chunk_id": {"type": "string"},
                    "snippet": {"type": "string"},
                },
                "required": ["id", "source", "chunk_id", "snippet"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["title", "metadata", "sections", "references"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """\
You are an expert aviation field inspector generating professional site inspection reports.

Given observations from a site inspection (typed notes, voice transcript, and/or OCR text \
from photos), generate a comprehensive, regulation-grounded field report with 3–4 sections.

Guidelines:
- Title: clear, descriptive (e.g. "Runway Lighting Infrastructure Inspection Report")
- Metadata: inspector "Auto-generated", status "DRAFT"
- Sections: cover Observations, Compliance Assessment, Findings & Risk, Recommendations
- Each section body: 2–4 sentences, professional tone, specific to the observations given
- Citations: reference relevant aviation standards (e.g. CAAS-AIC.pdf, ICAO-Annex14.pdf,
  FAR-Part139.pdf, CAP168.pdf). Assign sequential IDs starting at 1.
- References array: every citation ID must have a matching entry with a realistic snippet
  (quoted regulatory text, 10–20 words)
- All citation IDs in sections must appear in the references array

Be specific to the actual content in the observations — do not generate generic filler.\
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

    response = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=4096,
        thinking={"type": "adaptive"},
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": (
                    "Generate a field inspection report based on these observations:\n\n"
                    + combined
                ),
            }
        ],
        output_config={
            "format": {
                "type": "json_schema",
                "name": "field_report",
                "schema": REPORT_SCHEMA,
            }
        },
    )

    text = next(b.text for b in response.content if b.type == "text")
    return json.loads(text)
