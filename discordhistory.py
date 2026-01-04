import os
import discord
import asyncio
import json
import aiohttp

# ==== SETTINGS ====
DISCORD_TOKEN = ""
OPENAI_API_KEY = "sk-proj-"
OPENAI_ENDPOINT = "https://api.openai.com/v1"
DB_FILE = "users.json"

MODEL_NAME = "gpt-4o-mini"  

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

# ==== AI LOGIC (OPENAI GPT) ====
async def check_message_with_ai(text: str):
    prompt = f"""
    You are a lenient moderator. Check the text: "{text}".
    
    Only flag as bad if there is:
    - SEVERE profanity or slurs
    - DIRECT personal insults or attacks
    - EXTREME toxicity or hate speech
    
    Ignore: mild words, jokes, sarcasm, friendly banter, caps lock, exclamation marks.
    
    Severity scale:
    1-3: mild (ignore)
    4-6: moderate (warning only)
    7-10: severe (delete)
    
    Only set is_bad: true if severity >= 7.
    
    Response ONLY JSON:
    {{ "is_bad": bool, "reason": "str", "severity": int(1-10) }}
    """
    
    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": MODEL_NAME,
                "messages": [
                    {"role": "system", "content": "You are a content moderation assistant. Always respond with valid JSON only."},
                    {"role": "user", "content": prompt}
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.3
            }
            
            async with session.post(
                f"{OPENAI_ENDPOINT}/chat/completions",
                headers=headers,
                json=payload
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    content = data["choices"][0]["message"]["content"]
                    return json.loads(content)
                else:
                    print(f"⚠️ API Error: {response.status}")
                    return {"is_bad": False, "reason": "API Error", "severity": 0}

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
    print(f"✅ Bot is Running with OpenAI GPT (by Kozak)")

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
            try: 
                await message.delete()
            except: 
                pass

            users = load_users()
            uid = str(message.author.id)

            if uid not in users:
                users[uid] = {"rating": 50, "violations": 0}
            
            users[uid]["violations"] += 1
            save_users(users)
            
            penalty = -5 * ai_result.get("severity", 1)
            new_rating = update_rating(message.author.id, penalty)

            await message.channel.send(
                f"⚠️ {message.author.mention} removed! Reason: {ai_result.get('reason')}\n"
                f"Violation #{users[uid]['violations']}. Rating: {new_rating}",
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
            
            if muted_role is None:
                try:
                    muted_role = await message.guild.create_role(
                        name="Muted",
                        color=discord.Color.dark_gray(),
                        reason="Auto-moderation mute role"
                    )
                except Exception as e:
                    print(f"❌ Failed to create role: {e}")
                    return
            
            for channel in message.guild.channels:
                try:
                    overwrites = channel.overwrites_for(muted_role)
                    if overwrites.send_messages is not False or overwrites.speak is not False:
                        await channel.set_permissions(
                            muted_role,
                            send_messages=False,
                            speak=False,
                            add_reactions=False,
                            reason="Enforce mute permissions"
                        )
                except Exception as e:
                    print(f"⚠️ Failed to set permissions for {channel.name}: {e}")
            
            # Check if already muted
            if muted_role not in message.author.roles:
                try:
                    await message.author.add_roles(muted_role, reason="Low rating auto-mute")
                    
                    await message.channel.send(
                        f"🔇 {message.author.mention} muted for 30 seconds due to low rating!",
                        delete_after=10
                    )
                    
                    await asyncio.sleep(30)
                    
                    if muted_role in message.author.roles:
                        await message.author.remove_roles(muted_role, reason="Mute expired")
                        update_rating(message.author.id, 20)  
                        await message.channel.send(
                            f"🔊 {message.author.mention} unmuted.",
                            delete_after=5
                        )
                except Exception as e:
                    print(f"❌ Mute error: {e}")

client.run(DISCORD_TOKEN)
