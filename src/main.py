import os
import json
import base64
from flask import Flask, jsonify, render_template, request
from dotenv import load_dotenv
from twilio.twiml.voice_response import VoiceResponse, Gather
from twilio.jwt.access_token import AccessToken
from twilio.jwt.access_token.grants import VoiceGrant
from flask import send_from_directory
from ai import extract_intent_and_entities
from datetime import datetime, time
from zoneinfo import ZoneInfo
from google_calendar import (
    cancel_reservation_by_details,
    create_reservation,
    modify_reservation_by_details,
    test_calendar_connection,
)
from restaurant import answer_from_kb




load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
app = Flask(__name__, template_folder=TEMPLATE_DIR)
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_API_KEY = os.getenv("TWILIO_API_KEY")
TWILIO_API_SECRET = os.getenv("TWILIO_API_SECRET")
TWILIO_TWIML_APP_SID = os.getenv("TWILIO_TWIML_APP_SID")

KST = ZoneInfo("Asia/Seoul")
TTS_VOICE = os.getenv("TTS_VOICE", "Polly.Joanna-Neural")
SPEECH_TIMEOUT = os.getenv("SPEECH_TIMEOUT", "1")
RESERVATION_FIELDS = ("customer_name", "party_size", "date", "time")
CANCEL_FIELDS = ("customer_name", "date", "time")
MODIFY_FIELDS = ("customer_name", "date", "time", "new_date", "new_time")


def _load_state():
    raw_states = request.values.getlist("state")
    if not raw_states:
        return {}

    allowed_keys = {
        "flow",
        "awaiting_confirmation",
        "customer_name",
        "party_size",
        "date",
        "time",
        "new_date",
        "new_time",
        "notes",
    }

    for raw_state in reversed(raw_states):
        try:
            padded = raw_state + "=" * (-len(raw_state) % 4)
            decoded = base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8")
            state = json.loads(decoded)
            if isinstance(state, dict):
                return {key: state.get(key) for key in allowed_keys if key in state}
        except Exception:
            try:
                state = json.loads(raw_state)
                if isinstance(state, dict):
                    return {key: state.get(key) for key in allowed_keys if key in state}
            except json.JSONDecodeError:
                pass

    return {}


def _encode_state(state):
    state_json = json.dumps(state, separators=(",", ":"))
    encoded = base64.urlsafe_b64encode(state_json.encode("utf-8")).decode("utf-8")
    return encoded.rstrip("=")


def _merge_reservation_state(state, result):
    merged = dict(state)
    for field in RESERVATION_FIELDS:
        if result.get(field):
            if merged.get("flow") == "modify_reservation":
                if field == "date" and not merged.get("date"):
                    merged["date"] = result.get("date")
                elif field == "time" and not merged.get("time"):
                    merged["time"] = result.get("time")
                elif field == "date" and merged.get("date") and not merged.get("new_date"):
                    merged["new_date"] = result.get("date")
                elif field == "time" and merged.get("time") and not merged.get("new_time"):
                    merged["new_time"] = result.get("time")
                elif field not in ("date", "time"):
                    merged[field] = result.get(field)
            else:
                merged[field] = result.get(field)

    new_notes = result.get("notes")
    if new_notes:
        old_notes = merged.get("notes")
        merged["notes"] = f"{old_notes}; {new_notes}" if old_notes else new_notes

    return merged


def _next_missing_field(state):
    flow = state.get("flow", "make_reservation")
    if flow == "cancel_reservation":
        fields = CANCEL_FIELDS
    elif flow == "modify_reservation":
        fields = MODIFY_FIELDS
    else:
        fields = RESERVATION_FIELDS

    for field in fields:
        if not state.get(field):
            return field
    return None


def _question_for_field(field, state):
    flow = state.get("flow", "make_reservation")
    if flow == "cancel_reservation":
        questions = {
            "customer_name": "May I have the name on the reservation you want to cancel?",
            "date": "What date is the reservation you want to cancel?",
            "time": "What time is the reservation you want to cancel?",
        }
    elif flow == "modify_reservation":
        questions = {
            "customer_name": "May I have the name on the reservation you want to modify?",
            "date": "What is the current reservation date?",
            "time": "What is the current reservation time?",
            "new_date": "What new date would you like?",
            "new_time": "What new time would you like?",
        }
    else:
        questions = {
            "customer_name": "May I have the name for the reservation?",
            "party_size": "How many people will be coming?",
            "date": "What date would you like to reserve?",
            "time": "What time would you like to reserve?",
        }
    return questions[field]


def _gather_follow_up(response, question, state):
    state_token = _encode_state(state)
    gather = Gather(
        input="speech",
        action=f"{request.url_root}process-speech?state={state_token}",
        method="POST",
        speech_timeout=SPEECH_TIMEOUT,
        language="en-US",
    )
    gather.say(question, voice=TTS_VOICE)
    response.append(gather)
    response.say("Sorry, I did not hear anything. Please call again.", voice=TTS_VOICE)
    response.hangup()


def _gather_anything_else(response):
    gather = Gather(
        input="speech",
        action=f"{request.url_root}process-speech",
        method="POST",
        speech_timeout=SPEECH_TIMEOUT,
        language="en-US",
    )
    gather.say("Is there anything else you would like to know?", voice=TTS_VOICE)
    response.append(gather)
    response.say("Thank you for calling NOPS Seoul Station Branch. Goodbye.", voice=TTS_VOICE)
    response.hangup()


def _is_yes(text):
    normalized = text.lower().strip()
    yes_words = ("yes", "yeah", "yep", "correct", "confirm", "that's right", "sure", "ok", "okay")
    return any(word in normalized for word in yes_words)


def _is_no(text):
    normalized = text.lower().strip()
    no_words = ("no", "nope", "cancel", "not correct", "wrong", "stop")
    return any(word in normalized for word in no_words)


def _is_done(text):
    normalized = text.lower().strip().strip(".!")
    done_phrases = {
        "no",
        "no thanks",
        "no thank you",
        "nothing",
        "nothing else",
        "that's all",
        "that is all",
        "i'm done",
        "im done",
    }
    return normalized in done_phrases


def _parse_start_time(date_value, time_value):
    return datetime.strptime(
        f"{date_value} {time_value}",
        "%Y-%m-%d %H:%M"
    ).replace(tzinfo=KST)


def _is_valid_reservation_time(start_time):
    weekday = start_time.weekday()
    start_clock = start_time.time()

    if time(16, 0) <= start_clock < time(17, 0):
        return False, "That time is during our break time from 4 PM to 5 PM."

    if start_clock < time(11, 0):
        return False, "That time is before we open at 11 AM."

    if weekday in (4, 5):
        if start_clock > time(21, 0):
            return False, "On Friday and Saturday, last order is at 9 PM."
    else:
        if start_clock > time(20, 0):
            return False, "Sunday through Thursday, last order is at 8 PM."

    return True, None


def _confirmation_text(state):
    flow = state.get("flow")
    if flow == "cancel_reservation":
        return (
            f"Let me confirm. You want to cancel the reservation under {state.get('customer_name')} "
            f"on {state.get('date')} at {state.get('time')}. Is that correct?"
        )
    if flow == "modify_reservation":
        return (
            f"Let me confirm. You want to move the reservation under {state.get('customer_name')} "
            f"from {state.get('date')} at {state.get('time')} to {state.get('new_date')} "
            f"at {state.get('new_time')}. Is that correct?"
        )

    note_text = f" with this note: {state.get('notes')}" if state.get("notes") else ""
    return (
        f"Let me confirm. You want a reservation for {state.get('party_size')} people "
        f"on {state.get('date')} at {state.get('time')}, under the name "
        f"{state.get('customer_name')}{note_text}. Is that correct?"
    )


def _request_confirmation(response, state):
    state["awaiting_confirmation"] = True
    _gather_follow_up(response, _confirmation_text(state), state)


def _execute_confirmed_action(response, state):
    flow = state.get("flow", "make_reservation")

    if flow == "cancel_reservation":
        start_time = _parse_start_time(state.get("date"), state.get("time"))
        result = cancel_reservation_by_details(state.get("customer_name"), start_time)
        if result.get("ok"):
            response.say("Your reservation has been cancelled.", voice=TTS_VOICE)
        else:
            response.say(
                "Sorry, I could not find a matching reservation to cancel.",
                voice=TTS_VOICE
            )
        return

    if flow == "modify_reservation":
        old_start_time = _parse_start_time(state.get("date"), state.get("time"))
        new_start_time = _parse_start_time(state.get("new_date"), state.get("new_time"))
        is_valid, reason = _is_valid_reservation_time(new_start_time)
        if not is_valid:
            response.say(reason, voice=TTS_VOICE)
            return

        result = modify_reservation_by_details(
            state.get("customer_name"),
            old_start_time,
            new_start_time,
        )
        if result.get("ok"):
            response.say(
                f"Your reservation has been updated to {state.get('new_date')} at {state.get('new_time')}.",
                voice=TTS_VOICE
            )
        else:
            response.say(
                "Sorry, I could not modify that reservation. The original reservation was not found, or the new time is unavailable.",
                voice=TTS_VOICE
            )
        return

    start_time = _parse_start_time(state.get("date"), state.get("time"))
    is_valid, reason = _is_valid_reservation_time(start_time)
    if not is_valid:
        response.say(reason, voice=TTS_VOICE)
        return

    notes = state.get("notes")
    booking_result = create_reservation(
        customer_name=state.get("customer_name"),
        party_size=int(state.get("party_size")),
        start_time=start_time,
        phone=None,
        notes=(
            f"Created from AI receptionist voice call. Notes: {notes}"
            if notes else "Created from AI receptionist voice call"
        )
    )
    if booking_result.get("ok"):
        note_text = f" I also added this note: {notes}." if notes else ""
        response.say(
            f"Your reservation is confirmed for {state.get('party_size')} people on {state.get('date')} "
            f"at {state.get('time')}, under the name {state.get('customer_name')}.{note_text}",
            voice=TTS_VOICE
        )
    else:
        response.say(
            "Sorry, that time slot is not available. Please choose another time.",
            voice=TTS_VOICE
        )

def validate_env():
    missing=[]
    if not TWILIO_ACCOUNT_SID:
        missing.append("TWILIO_ACCOUNT_SID")
    if not TWILIO_API_KEY:
        missing.append("TWILIO_API_KEY")
    if not TWILIO_API_SECRET:
        missing.append("TWILIO_API_SECRET")
    if not TWILIO_TWIML_APP_SID:
        missing.append("TWILIO_TWIML_APP_SID")
    if missing:
        return missing
    return None

@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "message":"AI Receptionist backend is running!",
        "status":"ok"
    }),200

@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status":"healthy",
        "service":"ai-receptionist",
        "method":request.method
    }),200

@app.route("/calendar/auth", methods=["GET"])
def calendar_auth():
    try:
        result = test_calendar_connection()
        return jsonify(result), 200
    except Exception as exc:
        return jsonify({
            "ok": False,
            "error": "Google Calendar authorization failed.",
            "details": str(exc),
        }), 500

@app.route("/token", methods=["GET"])
def token():
    missing = validate_env()
    if missing:
        return jsonify({
            "ok":False,
            "error":"Missing environment variables.",
            "missing":missing
        }),500
    
    identity = "tanvir-browser-client"
    access_token = AccessToken(
        TWILIO_ACCOUNT_SID,
        TWILIO_API_KEY,
        TWILIO_API_SECRET,
        identity=identity
    )
    voice_grant = VoiceGrant(
        outgoing_application_sid=TWILIO_TWIML_APP_SID,
        incoming_allow=True
    )
    access_token.add_grant(voice_grant)
    jwt_token = access_token.to_jwt()
    if isinstance(jwt_token, bytes):
        jwt_token = jwt_token.decode("utf-8")
    return jsonify({
        "token":jwt_token,
        "identity":identity
    }),200

@app.route("/voice", methods=["GET","POST"])
def voice():
    """
    Twilio calls this route when someone starts a browser or phone call. We answer the call, greet the caller, and gather speech input.
    """
    response = VoiceResponse()
    gather = Gather(input="speech",
                    action=f"{request.url_root}process-speech",
                    method="POST",
                    speech_timeout=SPEECH_TIMEOUT,
                    language="en-US")
    gather.say(
        "Hello, thank you for calling NOPS Seoul Station Branch. How can I help you today?",
        voice=TTS_VOICE
    )
    response.append(gather)
    response.say(
        "I didn't catch that. Please call again. Thank you.",
        voice=TTS_VOICE
    )
    response.hangup()
    return str(response), 200, {"Content-Type": "text/xml"}

@app.route("/process-speech", methods=["GET", "POST"])
def process_speech():
    """
    Twilio sends recognized speech here after the caller speaks.
    Now we send that transcript to Grok for intent + entity extraction.
    """
    speech_result = request.values.get("SpeechResult", "").strip()

    response = VoiceResponse()

    if not speech_result:
        response.say(
            "Sorry, I did not hear anything. Please call again.",
            voice=TTS_VOICE
        )
        response.hangup()
        return str(response), 200, {"Content-Type": "text/xml"}

    previous_state = _load_state()
    if previous_state.get("awaiting_confirmation"):
        if _is_yes(speech_result):
            try:
                _execute_confirmed_action(response, previous_state)
            except Exception as exc:
                print("Confirmed action error:", exc)
                response.say(
                    "Sorry, I had trouble completing that action in the calendar.",
                    voice=TTS_VOICE
                )
                response.hangup()
                return str(response), 200, {"Content-Type": "text/xml"}

            _gather_anything_else(response)
            return str(response), 200, {"Content-Type": "text/xml"}

        if _is_no(speech_result):
            response.say("No problem. I have not made any calendar changes.", voice=TTS_VOICE)
            response.hangup()
            return str(response), 200, {"Content-Type": "text/xml"}

        _gather_follow_up(
            response,
            "Please say yes to confirm, or no to cancel.",
            previous_state,
        )
        return str(response), 200, {"Content-Type": "text/xml"}

    if not previous_state and _is_done(speech_result):
        response.say("Thank you for calling NOPS Seoul Station Branch. Goodbye.", voice=TTS_VOICE)
        response.hangup()
        return str(response), 200, {"Content-Type": "text/xml"}

    ai_output = extract_intent_and_entities(speech_result, previous_state)
    print("Speech Result:", speech_result)
    print("AI output:", ai_output)
    if not ai_output.get("ok"):
        response.say(
            "I heard you, but I had trouble understanding your request in the AI system.",
            voice=TTS_VOICE
        )
        response.say(
            "Please try again later.",
            voice=TTS_VOICE
        )
        response.hangup()
        return str(response), 200, {"Content-Type": "text/xml"}

    result = ai_output["result"]

    intent = result.get("intent")
    if not previous_state:
        if intent in ("make_reservation", "cancel_reservation", "modify_reservation"):
            previous_state["flow"] = intent
    elif previous_state.get("flow"):
        intent = previous_state["flow"]

    reservation_state = _merge_reservation_state(previous_state, result)
    customer_name = reservation_state.get("customer_name")
    party_size = reservation_state.get("party_size")
    date = reservation_state.get("date")
    time_value = reservation_state.get("time")
    notes = reservation_state.get("notes")

    if intent in ("make_reservation", "cancel_reservation", "modify_reservation") or previous_state:
        missing_field = _next_missing_field(reservation_state)
        if missing_field:
            _gather_follow_up(
                response,
                _question_for_field(missing_field, reservation_state),
                reservation_state,
            )
            return str(response), 200, {"Content-Type": "text/xml"}

        try:
            if intent == "make_reservation":
                start_time = _parse_start_time(date, time_value)
            elif intent == "modify_reservation":
                start_time = _parse_start_time(
                    reservation_state.get("new_date"),
                    reservation_state.get("new_time")
                )
            else:
                start_time = None

            if start_time:
                is_valid, reason = _is_valid_reservation_time(start_time)
                if not is_valid:
                    if intent == "modify_reservation":
                        reservation_state.pop("new_time", None)
                    else:
                        reservation_state.pop("time", None)
                    _gather_follow_up(
                        response,
                        f"{reason} Please choose another time.",
                        reservation_state,
                    )
                    return str(response), 200, {"Content-Type": "text/xml"}
        except Exception as exc:
            print("Time validation error:", exc)
            response.say(
                "I understood the details, but the date or time format was not clear. Please try again.",
                voice=TTS_VOICE
            )
            response.hangup()
            return str(response), 200, {"Content-Type": "text/xml"}

        _request_confirmation(response, reservation_state)
        return str(response), 200, {"Content-Type": "text/xml"}
        
    elif intent == "ask_hours":
        response.say(answer_from_kb(intent), voice=TTS_VOICE)
        _gather_anything_else(response)
        return str(response), 200, {"Content-Type": "text/xml"}

    elif intent == "ask_menu":
        response.say(answer_from_kb(intent), voice=TTS_VOICE)
        _gather_anything_else(response)
        return str(response), 200, {"Content-Type": "text/xml"}

    elif intent == "ask_parking":
        response.say(answer_from_kb(intent), voice=TTS_VOICE)
        _gather_anything_else(response)
        return str(response), 200, {"Content-Type": "text/xml"}

    elif intent == "ask_location":
        response.say(answer_from_kb(intent), voice=TTS_VOICE)
        _gather_anything_else(response)
        return str(response), 200, {"Content-Type": "text/xml"}

    elif intent in ("ask_event", "ask_seating", "ask_private_room"):
        response.say(answer_from_kb(intent), voice=TTS_VOICE)
        _gather_anything_else(response)
        return str(response), 200, {"Content-Type": "text/xml"}

    else:
        response.say(
            "I can help with reservations, business hours, location, parking, menu, events, and seating information.",
            voice=TTS_VOICE
        )

    response.hangup()
    return str(response), 200, {"Content-Type": "text/xml"}

@app.route("/browser", methods=["GET"])
def browser():
    return render_template("browser.html")

@app.route("/twilio.min.js")
def serve_twilio_sdk():
    return send_from_directory(TEMPLATE_DIR, "twilio.min.js")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=True)
