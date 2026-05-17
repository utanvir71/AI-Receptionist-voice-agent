import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()


XAI_API_KEY = os.getenv("XAI_API_KEY")
XAI_MODEL = os.getenv("XAI_MODEL", "grok-3-mini")
XAI_BASE_URL = os.getenv("XAI_BASE_URL","https://api.x.ai/v1/chat/completions")

def extract_intent_and_entities(user_text: str)-> dict:
    """
    Send caller transcript to Grok and return structured reservation-related info.
    Excepted output format:
    {
        "intent": "...."
        "customer_name":"....."
        "party_size":....
        "date":"...."
        "time":"...."
        "confidence":"low|medum|high"
        "notes":"...."
    }
    """

    if not XAI_API_KEY:
        return{
            "ok":False,
            "error":"Missing XAI_API_KEY in .env"
        }
    system_prompt   = """
    You are an AI receptionist for a resturant.
    Your job is to extract the caller's intent and keye reservation entities from their speech.

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

    JSON schema:
    {
        "intent": "one of the allowed intents",
        "customer_name": "string or null",
        "party_size": "integer or null",
        "date" : "string or null",
        "time" : "string or null",
        "confidence": "low or medium or high",
        "notes": "short string"
    }
    """
    user_prompt = f'Caller said: {user_text}'
    payload = {
        "model" : XAI_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt.strip()},
            {"role": "user", "content": user_prompt}
        ],
        "temperature":0.5
    }
    headers = {
        "Authorization":f"Bearer {XAI_API_KEY}",
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
        parsed = json.loads(content)
        return{
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
        return{
            "ok":False,
            "error":f"xAI request failed: {str(exc)}"
        }
    except Exception as exc:
        return{
            "ok": False,
            "error": f"Unexpected Ai error: {str(exc)}"
        }