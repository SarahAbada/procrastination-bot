import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
import requests
import discord
from discord.ext import commands

# Import RAG pipeline
from tasks import process_assignment

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
HF_API_KEY = os.getenv("HF_API_KEY")
HF_MODEL = os.getenv("HF_MODEL", "google/flan-t5-large")

# local bridge from bridge.js
BRIDGE_BASE_URL = os.getenv("BRIDGE_BASE_URL", "http://localhost:3000")
BRIDGE_SECRET = os.getenv("BRIDGE_SECRET", "YOUR_BRIDGE_SECRET")

# Path to a lecture PDF for the course
# For hackathon demo, start with one lecture file that matches the assignment
LECTURE_PDF_PATH = os.getenv("LECTURE_PDF_PATH", "lecture.pdf")

# Set to True only if your Google Calendar auth is already working
USE_GOOGLE_CALENDAR = os.getenv("USE_GOOGLE_CALENDAR", "False").lower() == "true"


# DISCORD SETUP

intents = discord.Intents.default()
message_content = getattr(intents, "message_content", None)
if message_content is not None:
    intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# BRIGHTSPACE BRIDGE

def fetch_deadlines():
    """
    Calls the Express bridge from bridge.js:
    GET /deadlines
    Header: x-bridge-token
    """
    headers = {"x-bridge-token": BRIDGE_SECRET}
    url = f"{BRIDGE_BASE_URL}/deadlines"

    response = requests.get(url, headers=headers, timeout=20)
    response.raise_for_status()

    data = response.json()
    if not isinstance(data, list):
        raise ValueError("Bridge did not return a list of deadlines.")

    return data


def pick_assignment(assignments):
    """
    Picks the most useful assignment to demo.
    Tries to ignore empty links and picks the nearest due date.
    """
    valid = []
    for a in assignments:
        title = a.get("title", "").strip()
        link = a.get("link", "").strip()
        due = a.get("due")

        if not title:
            continue
        if not link:
            continue

        valid.append(a)

    if not valid:
        return None

    def due_key(item):
        raw = item.get("due")
        if not raw:
            return datetime.max
        try:
            # Handles ISO strings like 2026-03-30T23:59:00Z
            cleaned = raw.replace("Z", "+00:00")
            return datetime.fromisoformat(cleaned)
        except Exception:
            return datetime.max

    valid.sort(key=due_key)
    return valid[0]


# HUGGING FACE LLM

def query_huggingface(prompt):
    """
    Uses Hugging Face Inference API.
    """
    api_url = f"https://api-inference.huggingface.co/models/{HF_MODEL}"
    headers = {"Authorization": f"Bearer {HF_API_KEY}"}
    payload = {
        "inputs": prompt,
        "parameters": {
            "max_new_tokens": 350,
            "temperature": 0.4,
            "return_full_text": False
        }
    }

    response = requests.post(api_url, headers=headers, json=payload, timeout=60)
    result = response.json()

    if isinstance(result, list) and len(result) > 0 and "generated_text" in result[0]:
        return result[0]["generated_text"].strip()

    if isinstance(result, dict) and "error" in result:
        return f"Hugging Face error: {result['error']}"

    return "Could not generate a response from Hugging Face."


def generate_plan(data):
    """
    data comes from process_assignment():
      {
        'title': ...,
        'due': ...,
        'assignment_text': ...,
        'relevant_lecture_content': ...
      }
    """
    prompt = f"""
You are an academic planning assistant for students.

Your job is to break an assignment into manageable steps using ONLY the provided lecture material.
Do not invent course content.
Do not claim information that is not supported by the lecture material.

Assignment title:
{data['title']}

Due date:
{data['due']}

Assignment description:
{data['assignment_text']}

Relevant lecture material:
{data['relevant_lecture_content']}

Write a student-friendly plan with exactly these sections:

Assignment Summary
Step-by-Step Plan
Suggested Timeline
Lecture Concepts to Review

Keep it concise, practical, and easy to paste into Discord.
Use bullet points.
"""
    return query_huggingface(prompt)

# GOOGLE CALENDAR

def create_event(summary, start_time, end_time, description=""):
    try:
        creds = Credentials.from_authorized_user_file("token.json")
        service = build("calendar", "v3", credentials=creds)

        event = {
            "summary": summary,
            "description": description,
            "start": {"dateTime": start_time, "timeZone": "America/Toronto"},
            "end": {"dateTime": end_time, "timeZone": "America/Toronto"},
        }

        service.events().insert(calendarId="primary", body=event).execute()
        return True
    except Exception as e:
        print("Calendar error:", e)
        return False


def parse_due_date(due_value):
    if not due_value:
        return None
    try:
        return datetime.fromisoformat(due_value.replace("Z", "+00:00"))
    except Exception:
        try:
            return datetime.fromisoformat(due_value)
        except Exception:
            return None


def create_schedule_events(title, due_value):
    due = parse_due_date(due_value)
    if due is None:
        return []

    checkpoints = [
        ("Start " + title, due - timedelta(days=5)),
        ("Work on " + title, due - timedelta(days=3)),
        ("Finalize " + title, due - timedelta(days=1)),
    ]

    created = []
    for name, date_obj in checkpoints:
        local_date = date_obj.replace(hour=10, minute=0, second=0, microsecond=0)
        end_date = local_date + timedelta(hours=2)

        success = create_event(
            summary=name,
            start_time=local_date.isoformat(),
            end_time=end_date.isoformat(),
            description=f"Auto-generated study block for {title}"
        )
        created.append((name, local_date.strftime("%Y-%m-%d %I:%M %p"), success))

    return created

# FORMATTING

def safe_truncate(text, limit=1800):
    if not text:
        return ""
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit - 3] + "..."


def format_assignment_card(assignment):
    title = assignment.get("title", "Untitled")
    due = assignment.get("due", "Unknown due date")
    a_type = assignment.get("type", "Unknown type")
    link = assignment.get("link", "No link")

    return (
        f"**Selected Assignment**\n"
        f"**Title:** {title}\n"
        f"**Due:** {due}\n"
        f"**Type:** {a_type}\n"
        f"**Link:** {link}"
    )

# MAIN DISCORD COMMAND

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")


@bot.command()
async def plan(ctx):
    await ctx.send("Pulling deadlines and generating your study plan...")

    try:
        assignments = fetch_deadlines()
    except Exception as e:
        await ctx.send(f"Could not fetch deadlines from the bridge: {e}")
        return

    if not assignments:
        await ctx.send("No deadlines were returned from Brightspace.")
        return

    assignment = pick_assignment(assignments)
    if assignment is None:
        await ctx.send("I found deadlines, but none had a usable assignment link.")
        return

    await ctx.send(format_assignment_card(assignment))

    try:
        rag_data = process_assignment(assignment, LECTURE_PDF_PATH)
    except Exception as e:
        await ctx.send(f"RAG processing failed: {e}")
        return

    try:
        plan_output = generate_plan(rag_data)
    except Exception as e:
        await ctx.send(f"Plan generation failed: {e}")
        return

    await ctx.send("**Generated Plan**")
    await ctx.send(safe_truncate(plan_output))

    if USE_GOOGLE_CALENDAR:
        events = create_schedule_events(rag_data["title"], rag_data["due"])
        if not events:
            await ctx.send("Could not create calendar events from the due date.")
            return

        lines = ["**Calendar Events**"]
        for name, dt, success in events:
            status = "✅" if success else "⚠️"
            lines.append(f"{status} {dt} — {name}")
        await ctx.send("\n".join(lines))
    else:
        await ctx.send(
            "**Suggested Schedule**\n"
            "- 5 days before: Start and review lecture concepts\n"
            "- 3 days before: Main implementation / drafting\n"
            "- 1 day before: Final polish and submission check"
        )


# SHOW ALL DEADLINES

@bot.command()
async def deadlines(ctx):
    try:
        assignments = fetch_deadlines()
    except Exception as e:
        await ctx.send(f"Could not fetch deadlines: {e}")
        return

    if not assignments:
        await ctx.send("No deadlines found.")
        return

    lines = ["**Upcoming Deadlines**"]
    for a in assignments[:10]:
        title = a.get("title", "Untitled")
        due = a.get("due", "Unknown due date")
        lines.append(f"- **{title}** — {due}")

    await ctx.send("\n".join(lines))

bot.run(DISCORD_TOKEN)
