import os
import json
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from restaurant import get_kb_context

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


def extract_intent_and_entities(user_text: str, reservation_state=None) -> dict:
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
        "notes": "short note or null",
        "receptionist_reply": "short spoken answer or null",
        "needs_clarification": false
    }
    """

    if not XAI_API_KEY:
        return {
            "ok": False,
            "error": "Missing XAI_API_KEY in .env"
        }

    today = datetime.now(KST).strftime("%Y-%m-%d")
    state_context = ""
    if reservation_state:
        state_context = f"""
Current partial reservation details:
{json.dumps(reservation_state, ensure_ascii=False)}

The caller may be answering a follow-up question with only one missing detail.
Keep the existing details and extract any new detail from the latest caller speech.
""".strip()

    system_prompt = f"""
You are an AI receptionist for NOPS Seoul Station Branch, a restaurant.
Your job is to extract the caller's intent and reservation entities from their speech.
You also write a short, natural spoken reply for restaurant questions that do not require a Flask action.

Today's date in Seoul is {today}.

{state_context}

Use this restaurant knowledge base to classify and answer restaurant questions:
{get_kb_context()}

Return ONLY valid JSON.
Do not add markdown.
Do not explain anything.

Allowed intents:
- make_reservation
- ask_hours
- ask_menu
- ask_parking
- ask_location
- ask_event
- ask_seating
- ask_private_room
- cancel_reservation
- modify_reservation
- unknown

Rules:
- If the caller wants to book, reserve, make a reservation, get a table, or asks for a table, use intent "make_reservation".
- If the caller wants to cancel a reservation, use intent "cancel_reservation".
- If the caller wants to change, move, update, or modify a reservation, use intent "modify_reservation".
- If the caller gives missing reservation details after being asked a follow-up question, still use intent "make_reservation".
- If the current partial reservation flow is cancel_reservation or modify_reservation, keep that intent.
- Convert relative dates like "today", "tomorrow", and "next Friday" into YYYY-MM-DD using today's Seoul date.
- Return time in 24-hour HH:MM format.
- If date or time is missing, return null for that field.
- If party size is missing, return null.
- If customer name is missing, return null.
- Put seating requests, private room requests, birthday notes, late arrival notes, and other reservation preferences in notes.
- If there are no notes, return null for notes.
- Do not guess missing details.
- For restaurant questions that do not match a specific intent, use intent "unknown" and answer naturally from the knowledge base.
- If the caller only says they want to ask a question, use intent "unknown" and ask what they would like to know.
- If the caller's meaning is unclear, use intent "unknown" and politely ask them to repeat or clarify.
- For casual non-restaurant questions, use intent "unknown" and politely explain that you can help with restaurant-related questions.
- Set receptionist_reply to null for reservation, cancellation, and modification flows because Flask handles those replies.
- For information questions and unknown intent, write a concise receptionist_reply suitable for text-to-speech.
- Set needs_clarification to true only when the caller needs to repeat, clarify, or finish asking their question. Otherwise set it to false.
- Never invent information that is not in the knowledge base.

JSON schema:
{{
    "intent": "one of the allowed intents",
    "customer_name": "string or null",
    "party_size": "integer or null",
    "date": "YYYY-MM-DD string or null",
    "time": "HH:MM string or null",
    "confidence": "low or medium or high",
    "notes": "short string or null",
    "receptionist_reply": "short spoken answer or null",
    "needs_clarification": "boolean"
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
