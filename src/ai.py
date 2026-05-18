import os
import json
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv()

XAI_API_KEY = os.getenv("XAI_API_KEY")
XAI_MODEL = os.getenv("XAI_MODEL", "grok-3-mini")
XAI_BASE_URL = os.getenv("XAI_BASE_URL", "https://api.x.ai/v1/chat/completions")
KST = ZoneInfo("Asia/Seoul")


def _extract_json(content: str) -> dict:
    """
    Parse model output into JSON.
    Handles clean JSON and accidental markdown-wrapped JSON.
    """
    content = content.strip()

    if content.startswith("```"):
        content = content.replace("```json", "").replace("```", "").strip()

    start = content.find("{")
    end = content.rfind("}")

    if start == -1 or end == -1:
        raise json.JSONDecodeError("No JSON object found", content, 0)

    return json.loads(content[start:end + 1])


def extract_intent_and_entities(user_text: str) -> dict:
    """
    Send caller transcript to Grok and return structured reservation-related info.

    Expected output format:
    {
        "intent": "make_reservation",
        "customer_name": "Tanvir",
        "party_size": 2,
        "date": "2026-05-18",
        "time": "19:00",
        "confidence": "high",
        "notes": "short note"
    }
    """

    if not XAI_API_KEY:
        return {
            "ok": False,
            "error": "Missing XAI_API_KEY in .env"
        }

    today = datetime.now(KST).strftime("%Y-%m-%d")

    system_prompt = f"""
You are an AI receptionist for NOPS Seoul Station Branch, a restaurant.
Your job is to extract the caller's intent and reservation entities from their speech.

Today's date in Seoul is {today}.

Return ONLY valid JSON.
Do not add markdown.
Do not explain anything.

Allowed intents:
- make_reservation
- ask_hours
- ask_menu
- ask_parking
- ask_location
- cancel_reservation
- modify_reservation
- unknown

Rules:
- If the caller wants to book, reserve, make a reservation, get a table, or asks for a table, use intent "make_reservation".
- Convert relative dates like "today", "tomorrow", and "next Friday" into YYYY-MM-DD using today's Seoul date.
- Return time in 24-hour HH:MM format.
- If date or time is missing, return null for that field.
- If party size is missing, return null.
- If customer name is missing, return null.
- Do not guess missing details.
- For casual non-restaurant questions, use intent "unknown".

JSON schema:
{{
    "intent": "one of the allowed intents",
    "customer_name": "string or null",
    "party_size": "integer or null",
    "date": "YYYY-MM-DD string or null",
    "time": "HH:MM string or null",
    "confidence": "low or medium or high",
    "notes": "short string"
}}
""".strip()

    user_prompt = f"Caller said: {user_text}"

    payload = {
        "model": XAI_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.1
    }

    headers = {
        "Authorization": f"Bearer {XAI_API_KEY}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(
            XAI_BASE_URL,
            headers=headers,
            json=payload,
            timeout=30
        )
        response.raise_for_status()

        data = response.json()
        content = data["choices"][0]["message"]["content"].strip()
        parsed = _extract_json(content)

        return {
            "ok": True,
            "result": parsed
        }

    except json.JSONDecodeError:
        return {
            "ok": False,
            "error": "Grok returned non-JSON output",
            "raw": content if "content" in locals() else None
        }

    except requests.RequestException as exc:
        return {
            "ok": False,
            "error": f"xAI request failed: {str(exc)}"
        }

    except Exception as exc:
        return {
            "ok": False,
            "error": f"Unexpected AI error: {str(exc)}"
        }