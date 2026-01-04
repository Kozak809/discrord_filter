import os
import discord
import asyncio
import json
from google import genai
from google.genai import types

# ==== SETTINGS ====
DISCORD_TOKEN = ""
GEMINI_API_KEY = ""
DB_FILE = "users.json"

ai_client = genai.Client(api_key=GEMINI_API_KEY)

MODEL_NAME = "gemini-3-flash-preview" 

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
client = discord.Client(intents=intents)

# ==== FILE OPERATIONS (DB) ====
def load_users():
    if not os.path.exists(DB_FILE):
        return {}
    with open(DB_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}

def save_users(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def get_rating(user_id):
    users = load_users()
    return users.get(str(user_id), {}).get("rating", 0)

def update_rating(user_id, change):
    users = load_users()
    uid = str(user_id)
    
    if uid not in users:
        users[uid] = {"rating": 50, "violations": 0} 
    
    users[uid]["rating"] += change
    save_users(users)
    return users[uid]["rating"]

# ==== AI LOGIC (NEW LIBRARY) ====
async def check_message_with_ai(text: str):
    prompt = f"""
    You are a moderator. Check the text: "{text}".
    If there is profanity, insults, or toxicity - is_bad: true.
    Response ONLY JSON:
    {{ "is_bad": bool, "reason": "str", "severity": int(1-10) }}
    """
    
    try:
        response = await asyncio.to_thread(
            ai_client.models.generate_content,
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        
        if response.text:
            return json.loads(response.text)
        return {"is_bad": False, "reason": "Empty", "severity": 0}

    except Exception as e:
        print(f"⚠️ AI Error: {e}")
        return {"is_bad": False, "reason": "Error", "severity": 0}

# ==== MUTE FUNCTIONS ====
async def mute_user(member: discord.Member, guild: discord.Guild):
    muted_role = discord.utils.get(guild.roles, name="Muted")
    if muted_role is None:
        try:
            muted_role = await guild.create_role(name="Muted")
            for channel in guild.channels:
                await channel.set_permissions(muted_role, send_messages=False, speak=False)
        except:
            return
    
    for channel in guild.channels:
        if channel.overwrites_for(muted_role).send_messages is not False:
            try:
                await channel.set_permissions(muted_role, send_messages=False, speak=False)
            except:
                pass

    try:
        await member.add_roles(muted_role)
    except:
        pass

# ==== DISCORD EVENTS ====
@client.event
async def on_ready():
    if not os.path.exists(DB_FILE):
            save_users({})
    print(f"✅ Bot is Running (by Kozak)")

@client.event
async def on_message(message: discord.Message):
    if message.author == client.user:
        return

    if message.content.startswith("!rating"):
        rating = get_rating(message.author.id)
        await message.channel.send(f"📊 Rating: **{rating}**")
        return

    # Rating variable
    new_rating = get_rating(message.author.id)

    if len(message.content) > 3:
        ai_result = await check_message_with_ai(message.content)

        if ai_result["is_bad"]:
            try: await message.delete()
            except: pass

            users = load_users()
            uid = str(message.author.id)

            if uid not in users:
                 users[uid] = {"rating": 50, "violations": 0}
            
            users[uid]["violations"] += 1
            save_users(users)
            
            penalty = -5 * ai_result.get("severity", 1)
            new_rating = update_rating(message.author.id, penalty)

            await message.channel.send(
                f"⚠️ {message.author.mention} удалено! Причина: {ai_result.get('reason')}\n"
                f"Нарушение #{users[uid]['violations']}. Рейтинг: {new_rating}",
                delete_after=10
            )
        else:
            new_rating = update_rating(message.author.id, 1)
    else:
        new_rating = update_rating(message.author.id, 1)

    # MUTE CHECK (General)
    if new_rating <= 0:
        if isinstance(message.author, discord.Member):
            muted_role = discord.utils.get(message.guild.roles, name="Muted")
            if muted_role and muted_role not in message.author.roles:
                await mute_user(message.author, message.guild)
                
                await message.channel.send(
                    f"🔇 {message.author.mention} muted for 10 sec due to low rating!",
                    delete_after=10
                )
                
                await asyncio.sleep(10)
                
                if muted_role in message.author.roles:
                    await message.author.remove_roles(muted_role)
                    update_rating(message.author.id, 20) # Restore points
                    await message.channel.send(f"🔊 {message.author.mention} unmuted.", delete_after=5)

client.run(DISCORD_TOKEN)
