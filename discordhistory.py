import os
import discord
from supabase import create_client, Client
from datetime import datetime

# ==== Настройки ====
DISCORD_TOKEN = ""  # токен бота
SUPABASE_URL = ""
SUPABASE_KEY = ""
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True  
client = discord.Client(intents=intents)


def get_user_rating(username: str):
    user = supabase.table("users").select("rating").eq("username", username).execute().data
    return user[0]["rating"] if user else None


def update_rating(username: str, guild: str, change: int):
    user = supabase.table("users").select("*").eq("username", username).execute().data
    if user:
        new_rating = user[0]["rating"] + change
        supabase.table("users").update({
            "rating": new_rating,
            "guild": guild,
            "updated_at": datetime.utcnow().isoformat()
        }).eq("username", username).execute()
        return new_rating
    else:
        supabase.table("users").insert({
            "username": username,
            "guild": guild,
            "rating": change,
            "updated_at": datetime.utcnow().isoformat()
        }).execute()
        return change


async def mute_user(member: discord.Member, guild: discord.Guild):
    """Выдаёт роль 'Muted' пользователю"""
    muted_role = discord.utils.get(guild.roles, name="Muted")
    if muted_role is None:
        # если роли нет — создаём
        muted_role = await guild.create_role(name="Muted", reason="Для наказаний")
        for channel in guild.channels:
            await channel.set_permissions(muted_role, send_messages=False, speak=False)

    await member.add_roles(muted_role)
    print(f"Пользователь {member} замучен")


@client.event
async def on_ready():
    print(f"Бот вошел как {client.user}")


@client.event
async def on_message(message: discord.Message):
    if message.author == client.user:
        return

    username = str(message.author)
    guild = message.guild.name if message.guild else "ЛС"
    content = message.content

    # Команда для просмотра рейтинга
    if content.startswith("!rating"):
        rating = get_user_rating(username)
        rating = rating if rating is not None else 0
        await message.channel.send(f"📊 {message.author.mention}, твой рейтинг: **{rating}**")
        return

    bad_words = supabase.table("bad_words").select("word").execute().data
    bad_list = [w["word"].lower() for w in bad_words]

    # Проверка на мат
    if any(bad in content.lower() for bad in bad_list):
        try:
            await message.delete()

            new_rating = update_rating(username, guild, -10)

            supabase.table("users").update({
                "last_bad_message": content,
                "last_bad_at": datetime.utcnow().isoformat()
            }).eq("username", username).execute()

            await message.channel.send(
                f"⚠️ {message.author.mention}, мат запрещён! (-10 очков)",
                delete_after=5
            )

            print(f"Мат: {username} ({guild}) -10 очков → рейтинг {new_rating}")

            if new_rating <= 0 and message.guild:
                await mute_user(message.author, message.guild)
                supabase.table("users").update({"rating": 11}).eq("username", username).execute()
                await message.channel.send(
                    f"🔇 {message.author.mention} замучен за плохое поведение!",
                    delete_after=5
                )
        except Exception as e:
            print("Ошибка при обработке мата:", e)


        except Exception as e:
            print("Ошибка при обработке мата:", e)


        except Exception as e:
            print("Ошибка при обработке мата:", e)
    else:
        new_rating = update_rating(username, guild, +1)
        print(f"Сообщение: {username} ({guild}) +1 очко → рейтинг {new_rating}")


client.run(DISCORD_TOKEN)