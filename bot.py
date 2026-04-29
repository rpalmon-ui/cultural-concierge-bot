import os
import json
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import anthropic
from supabase import create_client, Client

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ALLOWED_USER_ID = 6109483824
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

conversation_histories = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Hi Ruth! I'm your Cultural Concierge.\n\n"
        "Tell me what you're doing:\n"
        "• 'I'm getting in the car'\n"
        "• 'I just finished [title] and loved it'\n"
        "• 'What should I watch tonight?'"
    )

async def get_user_library(user_id: int) -> dict:
    response = supabase.table("library").select("*").eq("user_id", user_id).execute()
    items = response.data if response.data else []
    return {
        "consumed": [item for item in items if item.get("status") == "consumed"],
        "pending": [item for item in items if item.get("status") == "pending"]
    }

async def save_to_library(user_id: int, title: str, category: str, recommender: str = "AI recommendation") -> None:
    try:
        supabase.table("library").insert({
            "user_id": user_id,
            "title": title,
            "category": category,
            "recommender": recommender,
            "status": "pending",
            "added_date": datetime.now().isoformat()
        }).execute()
    except Exception as e:
        print(f"Error saving to library: {e}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ALLOWED_USER_ID:
        await update.message.reply_text("Sorry, this is a private bot.")
        return

    user_id = update.effective_user.id
    user_message = update.message.text

    if user_id not in conversation_histories:
        conversation_histories[user_id] = []

    conversation_histories[user_id].append({"role": "user", "content": user_message})

    if len(conversation_histories[user_id]) > 10:
        conversation_histories[user_id] = conversation_histories[user_id][-10:]

    library = await get_user_library(user_id)
    library_context = json.dumps(library, indent=2, default=str)

    system_prompt = f"""You are Ruth's Cultural Concierge. Her library:
{library_context}

When you recommend something, always end with: "Want me to add this to your list?"
If Ruth says yes, reply with: "Added! [title] | [category] | [creator]"
Make suggestions based on her taste, remember who recommended things, and respond to her context cues."""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1024,
            system=system_prompt,
            messages=conversation_histories[user_id]
        )

        reply = response.content[0].text
        conversation_histories[user_id].append({"role": "assistant", "content": reply})

        if reply.startswith("Added!"):
            parts = reply.split("|")
            if len(parts) >= 3:
                title = parts[0].replace("Added!", "").strip()
                category = parts[1].strip()
                creator = parts[2].strip()
                await save_to_library(user_id, title, category, "AI recommendation")

        await update.message.reply_text(reply)

    except Exception as e:
        await update.message.reply_text(f"Error: {str(e)}")

def main() -> None:
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.run_polling()

if __name__ == '__main__':
    main()
