import logging
import os
import json
import uuid
import base64
from datetime import datetime, timezone

import azure.functions as func

from azure.storage.blob import BlobServiceClient
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeDocumentRequest
from azure.core.credentials import AzureKeyCredential

import requests


# ==============================
#   AUTH: GET USER ID
# ==============================

def get_user_id(req: func.HttpRequest) -> str:
    """
    Extracts the authenticated user id from Azure Static Web Apps.
    If running locally or no auth, returns 'anonymous'.
    """
    principal_header = req.headers.get("x-ms-client-principal")
    if not principal_header:
        return "anonymous"

    decoded = base64.b64decode(principal_header)
    principal = json.loads(decoded.decode("utf-8"))
    return principal.get("userId", "anonymous")


# ==============================
#   BLOB STORAGE UPLOAD
# ==============================

def upload_to_blob(pdf_bytes: bytes) -> str:
    """
    Uploads the PDF file to Azure Blob Storage and returns the file URL.
    """
    connection_str = os.environ["BLOB_ACCOUNT_CONNECTION"]
    container_name = os.environ.get("BLOB_CONTAINER_NAME", "resumes")

    blob_service_client = BlobServiceClient.from_connection_string(connection_str)
    container_client = blob_service_client.get_container_client(container_name)

    blob_name = f"{uuid.uuid4()}.pdf"
    blob_client = container_client.get_blob_client(blob_name)
    blob_client.upload_blob(pdf_bytes, overwrite=True)

    return blob_client.url


# ==============================
#   EXTRACT TEXT FROM PDF
# ==============================

def extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    """
    Sends the PDF bytes directly to Azure Document Intelligence
    to extract the text from it, using the 'body' parameter
    expected by the installed SDK.
    """
    endpoint = os.environ["DOCINT_ENDPOINT"]
    key = os.environ["DOCINT_KEY"]

    client = DocumentIntelligenceClient(
        endpoint=endpoint,
        credential=AzureKeyCredential(key)
    )

    # Use 'body' and specify content_type for the binary PDF
    poller = client.begin_analyze_document(
        model_id="prebuilt-layout",
        body=pdf_bytes,
        content_type="application/pdf"
    )

    result = poller.result()

    lines = []
    for page in result.pages:
        for line in page.lines:
            lines.append(line.content)

    return "\n".join(lines)



# ==============================
#   GEMINI CV ANALYSIS
# ==============================

def analyze_resume_with_ai(resume_text: str, target_role: str) -> dict:
    """
    Analyze resume using Google's Gemini 1.5 Flash via REST API (no SDK).
    Returns a structured JSON-like dict.
    """
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return {
            "overall_score": 50,
            "summary": "Demo mode: no GOOGLE_API_KEY configured.",
            "strengths": ["Demo strength 1", "Demo strength 2"],
            "weaknesses": ["Demo weakness 1", "Demo weakness 2"],
            "missing_keywords": ["Azure", "Kubernetes"],
            "improvement_suggestions": [
                "Configure a Gemini API key to get real analysis.",
                "Add concrete metrics and cloud technologies to your CV."
            ]
        }

    # Build prompt
    prompt = f"""
You are an expert technical recruiter specialized in cloud, data, and AI roles.

Your task:
- Read the resume text
- Consider the target job role
- Return a STRICT JSON object with fields:
    - overall_score (0-100)
    - summary
    - strengths (list of strings)
    - weaknesses (list of strings)
    - missing_keywords (list of strings)
    - improvement_suggestions (list of strings)

TARGET ROLE:
{target_role}

RESUME TEXT:
\"\"\"{resume_text}\"\"\"
"""

    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"

    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": api_key
    }

    body = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": prompt}
                ]
            }
        ]
    }

    try:
        resp = requests.post(url, headers=headers, json=body, timeout=60)
        resp.raise_for_status()
        data = resp.json()

        # Extract the text answer
        candidates = data.get("candidates", [])
        if not candidates:
            return {
                "overall_score": 0,
                "summary": "Gemini returned no candidates.",
                "strengths": [],
                "weaknesses": [],
                "missing_keywords": [],
                "improvement_suggestions": []
            }

        text = candidates[0]["content"]["parts"][0]["text"]

        # Try to parse JSON from the text Gemini returned
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Sometimes the model wraps JSON in markdown ``` fences; try to extract
            import re
            match = re.search(r"\{[\s\S]*\}", text)
            if match:
                try:
                    return json.loads(match.group(0))
                except:
                    pass
            # Fallback: just send raw text
            return {"raw": text}

    except Exception as e:
        logging.exception("Error calling Gemini REST API")
        return {
            "overall_score": 0,
            "summary": f"Gemini API error: {str(e)}",
            "strengths": [],
            "weaknesses": [],
            "missing_keywords": [],
            "improvement_suggestions": []
        }



# ==============================
#   MAIN AZURE FUNCTION
# ==============================

def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("🚀 analyze_resume function triggered")

    try:
        # 1) Get logged user (or anonymous)
        user_id = get_user_id(req)

        # 2) Get target job role
        target_role = (
            req.headers.get("x-target-role")
            or req.params.get("targetRole")
            or "Cloud Engineer"
        )

        # 3) Read PDF bytes
        pdf_bytes = req.get_body()
        if not pdf_bytes:
            return func.HttpResponse(
                json.dumps({"error": "No file provided."}),
                status_code=400,
                mimetype="application/json"
            )

        # 4) Upload to Blob Storage (for history / future use)
        blob_url = upload_to_blob(pdf_bytes)
        logging.info(f"📄 Uploaded CV → {blob_url}")

        # 5) Extract resume text directly from bytes (not from URL)
        resume_text = extract_text_from_pdf_bytes(pdf_bytes)
        logging.info("📄 Extracted text from resume")


        # 6) Analyze with OpenAI
        analysis = analyze_resume_with_ai(resume_text, target_role)
        logging.info("🤖 OpenAI analysis complete")

        # 7) Build response
        payload = {
            "userId": user_id,
            "targetRole": target_role,
            "blobUrl": blob_url,
            "uploadedAt": datetime.now(timezone.utc).isoformat(),
            "analysis": analysis
        }

        return func.HttpResponse(
            json.dumps(payload),
            status_code=200,
            mimetype="application/json"
        )

    except Exception as e:
        logging.exception("❌ Error during resume analysis")
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500,
            mimetype="application/json"
        )
