import discord
from discord.ext import commands
from discord import app_commands
import json
import sqlite3
import os
from typing import Dict, Any, Optional

# пути к файлам
JSON_PATH = "./data/profiles.json"
DB_PATH = "./data/profiles.db"

DEFAULT_GAMES = [
    "Genshin Impact",
    "League of Legends",
    "Apex Legends",
    "CS2",
    "Valorant",
    "Fortnite",
    "Minecraft",
    "GTA Online",
    "Warframe",
    "Overwatch 2"
]

DEFAULT_SERVERS = [
    "Europe",
    "North America",
    "Asia",
    "CIS",
    "South America"
]

# ID канала модераторов (из окружения). Преобразуем в int если возможно.
_mod_env = os.getenv("MODERATOR_CHANNEL_ID")
try:
    MOD_CHANNEL_ID: Optional[int] = int(_mod_env) if _mod_env is not None else None
except (TypeError, ValueError):
    MOD_CHANNEL_ID = None

# ----------------------------------------

# ------------- Helpers: JSON / SQLite -------------
def ensure_files_and_db():
    # Ensure data directory exists
    data_dir = os.path.dirname(JSON_PATH)
    if data_dir and not os.path.exists(data_dir):
        os.makedirs(data_dir, exist_ok=True)

    # ensure json file exists
    if not os.path.exists(JSON_PATH):
        with open(JSON_PATH, "w", encoding="utf-8") as f:
            json.dump({}, f, ensure_ascii=False, indent=2)

    # ensure sqlite and table
    db_dir = os.path.dirname(DB_PATH)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS profiles (
            id INTEGER PRIMARY KEY,
            gender TEXT,
            age INTEGER,
            games TEXT,
            servers TEXT
        )
    """)
    conn.commit()
    conn.close()


def load_profiles() -> Dict[str, Any]:
    # Use JSON_PATH consistently and handle empty file
    if not os.path.exists(JSON_PATH) or os.stat(JSON_PATH).st_size == 0:
        return {}
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            # If file is corrupted, return empty and overwrite later
            return {}


def save_profiles(data: Dict[str, Any]) -> None:
    # Ensure parent dir exists (safety)
    data_dir = os.path.dirname(JSON_PATH)
    if data_dir and not os.path.exists(data_dir):
        os.makedirs(data_dir, exist_ok=True)

    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def upsert_profile_db(user_id: int, profile: Dict[str, Any]) -> None:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    # Using INSERT ... ON CONFLICT to update existing
    cur.execute(
        """
        INSERT INTO profiles (id, gender, age, games, servers)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            gender=excluded.gender,
            age=excluded.age,
            games=excluded.games,
            servers=excluded.servers
        """,
        (
            user_id,
            profile.get("gender"),
            profile.get("age"),
            json.dumps(profile.get("games", []), ensure_ascii=False),
            json.dumps(profile.get("servers", []), ensure_ascii=False),
        ),
    )
    conn.commit()
    conn.close()


# ------------- Embed generator -------------
def make_profile_embed(member: discord.Member, profile: Dict[str, Any]) -> discord.Embed:
    emb = discord.Embed(title=f"Профиль — {member.display_name}", color=discord.Color.blurple())
    gender = profile.get("gender") or "Не указан"
    age = str(profile.get("age")) if profile.get("age") is not None else "Не указан"
    games = profile.get("games") or []
    servers = profile.get("servers") or []

    emoji_gender = {"Мужской": "♂️", "Женский": "♀️", "Не указан": "❓"}
    emb.add_field(name="Пол", value=f"{emoji_gender.get(gender, '')} {gender}", inline=False)
    emb.add_field(name="Возраст", value=age, inline=False)
    emb.add_field(name="Игры", value=", ".join(games) if games else "Не выбраны", inline=False)
    emb.add_field(name="Серверы", value=", ".join(servers) if servers else "Не выбраны", inline=False)

    joined = "—"
    try:
        if member.joined_at:
            joined = member.joined_at.date()
    except Exception:
        joined = "—"

    emb.set_footer(text=f"ID: {member.id} • Присоединился: {joined}")
    return emb


# ---------------- UI components ----------------
# We will store a reference to the View in 'view_ref' inside Select/Button classes
# so we don't attempt to set the read-only .parent property.

class ProfileEditView(discord.ui.View):
    def __init__(self, owner_id: int, profiles_ref: Dict[str, Any], bot: commands.Bot):
        super().__init__(timeout=None)
        self.owner_id = owner_id
        self.profiles_ref = profiles_ref  # reference to loaded JSON data
        self.bot = bot

        # Add selects/buttons
        self.add_item(GenderSelect(view_ref=self, row=0))
        self.add_item(GamesSelect(view_ref=self, row=1))
        self.add_item(ServersSelect(view_ref=self, row=2))

        # Buttons row: change age (modal), request custom role modal
        self.add_item(ChangeAgeButton(view_ref=self, row=3))
        self.add_item(CustomRoleButton(view_ref=self, row=3))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Only profile owner allowed to interact
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Вы можете редактировать только свой профиль.", ephemeral=True)
            return False
        return True

    # Helpers to get and save profile easily
    def get_profile(self) -> Dict[str, Any]:
        uid = str(self.owner_id)
        return self.profiles_ref.setdefault(uid, {"gender": None, "age": None, "games": [], "servers": []})

    def save_and_persist(self):
        uid = str(self.owner_id)
        save_profiles(self.profiles_ref)
        upsert_profile_db(int(uid), self.profiles_ref[uid])


# ---- Gender Select ----
class GenderSelect(discord.ui.Select):
    def __init__(self, view_ref: ProfileEditView, row: int = 0):
        self.view_ref = view_ref
        options = [
            discord.SelectOption(label="Мужской"),
            discord.SelectOption(label="Женский"),
            discord.SelectOption(label="Не указан"),
        ]
        super().__init__(placeholder="Выберите пол", options=options, row=row, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        profile = self.view_ref.get_profile()
        # single select => first value
        profile["gender"] = self.values[0]
        self.view_ref.save_and_persist()

        # Update main embed (original message)
        embed = make_profile_embed(interaction.user, profile)
        try:
            await interaction.response.edit_message(embed=embed, view=self.view_ref)
        except Exception:
            # fallback if edit_message not allowed
            await interaction.response.send_message("Пол обновлён.", ephemeral=True)

        # update status message (followup)
        await update_status_followup(interaction, f"Пол обновлён: **{self.values[0]}**")


# ---- Games Select (multi) ----
class GamesSelect(discord.ui.Select):
    def __init__(self, view_ref: ProfileEditView, row: int = 1):
        self.view_ref = view_ref
        options = [discord.SelectOption(label=g) for g in DEFAULT_GAMES]
        super().__init__(
            placeholder="Выберите игры (можно несколько)",
            options=options,
            min_values=0,
            max_values=len(options),
            row=row
        )

    async def callback(self, interaction: discord.Interaction):
        profile = self.view_ref.get_profile()
        profile["games"] = self.values
        self.view_ref.save_and_persist()

        embed = make_profile_embed(interaction.user, profile)
        try:
            await interaction.response.edit_message(embed=embed, view=self.view_ref)
        except Exception:
            await interaction.response.send_message("Игры сохранены.", ephemeral=True)
        await update_status_followup(interaction, "Игровые роли обновлены")


# ---- Servers Select (multi) ----
class ServersSelect(discord.ui.Select):
    def __init__(self, view_ref: ProfileEditView, row: int = 2):
        self.view_ref = view_ref
        options = [discord.SelectOption(label=s) for s in DEFAULT_SERVERS]
        super().__init__(
            placeholder="Выберите серверы (можно несколько)",
            options=options,
            min_values=0,
            max_values=len(options),
            row=row
        )

    async def callback(self, interaction: discord.Interaction):
        profile = self.view_ref.get_profile()
        profile["servers"] = self.values
        self.view_ref.save_and_persist()

        embed = make_profile_embed(interaction.user, profile)
        try:
            await interaction.response.edit_message(embed=embed, view=self.view_ref)
        except Exception:
            await interaction.response.send_message("Серверы сохранены.", ephemeral=True)
        await update_status_followup(interaction, "Серверы обновлены")


# ---- Change Age Button -> opens modal ----
class ChangeAgeButton(discord.ui.Button):
    def __init__(self, view_ref: ProfileEditView, row: int = 3):
        super().__init__(label="Изменить возраст", style=discord.ButtonStyle.primary, row=row)
        self.view_ref = view_ref

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ChangeAgeModal(view_ref=self.view_ref))


class ChangeAgeModal(discord.ui.Modal, title="Смена возраста"):
    # single text input for age
    age = discord.ui.TextInput(label="Возраст", style=discord.TextStyle.short, placeholder="Введите возраст (12–99)", max_length=3)

    def __init__(self, view_ref: ProfileEditView):
        super().__init__()
        self.view_ref = view_ref

    async def on_submit(self, interaction: discord.Interaction):
        age_raw = self.age.value.strip()
        try:
            age_int = int(age_raw)
        except ValueError:
            await interaction.response.send_message("Возраст должен быть числом.", ephemeral=True)
            return

        if not (12 <= age_int <= 99):
            await interaction.response.send_message("Возраст должен быть в диапазоне 12–99.", ephemeral=True)
            return

        profile = self.view_ref.get_profile()
        profile["age"] = age_int
        self.view_ref.save_and_persist()

        embed = make_profile_embed(interaction.user, profile)

        # Try to update the original message that contains the view; if cannot — send ephemeral confirmation
        try:
            await interaction.response.edit_message(embed=embed, view=self.view_ref)
        except Exception:
            # If editing original message is not possible, respond ephemerally
            try:
                await interaction.response.send_message("Возраст обновлён.", ephemeral=True)
            except Exception:
                pass

        await update_status_followup(interaction, f"Возраст обновлён: **{age_int}**")


# ---- Custom Role Button -> opens modal ----
class CustomRoleButton(discord.ui.Button):
    def __init__(self, view_ref: ProfileEditView, row: int = 3):
        super().__init__(label="Запросить кастомную роль", style=discord.ButtonStyle.secondary, row=row)
        self.view_ref = view_ref

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(CustomRoleModal(view_ref=self.view_ref))


class CustomRoleModal(discord.ui.Modal, title="Запрос на кастомную роль"):
    role = discord.ui.TextInput(label="Название роли", max_length=64, placeholder="Введите название роли")
    reason = discord.ui.TextInput(label="Причина (опционально)", style=discord.TextStyle.long, required=False, max_length=500)

    def __init__(self, view_ref: ProfileEditView):
        super().__init__()
        self.view_ref = view_ref

    async def on_submit(self, interaction: discord.Interaction):
        role_name = self.role.value.strip()
        reason = self.reason.value.strip() if self.reason.value else "Не указана"

        profile = self.view_ref.get_profile()
        # сохраняем запрошенное имя роли в profile.custom_role_request
        profile["custom_role_request"] = role_name
        self.view_ref.save_and_persist()

        # отправляем в мод-канал, если указан
        if MOD_CHANNEL_ID:
            try:
                ch = self.view_ref.bot.get_channel(MOD_CHANNEL_ID)
                if ch:
                    embed = discord.Embed(title="Запрос кастомной роли", color=discord.Color.orange())
                    embed.add_field(name="Пользователь", value=f"{interaction.user.mention} ({interaction.user.id})", inline=False)
                    embed.add_field(name="Роль", value=role_name, inline=False)
                    embed.add_field(name="Причина", value=reason, inline=False)
                    await ch.send(embed=embed)
            except Exception as e:
                # лог ошибки, но не ломаем UX
                print(f"[Profile] Ошибка отправки в мод-канал: {e}")

        # обновим только статус
        try:
            await interaction.response.send_message("Запрос отправлен модераторам и сохранён в профиле (черновик).", ephemeral=True)
        except Exception:
            pass

        await update_status_followup(interaction, "Запрос кастомной роли отправлен")


# ----------------- Utility to update the status followup (single message) -----------------
# We'll maintain mapping in the Cog of user_id -> status_message_id for ephemeral followups.

async def update_status_followup(interaction: discord.Interaction, text: str):
    """
    Edit the previously sent followup status message (one per invoking user).
    Expects bot to have attribute 'profile_status_map' (a dict user_id -> message_id).
    """
    bot: commands.Bot = interaction.client  # type: ignore
    status_map: Dict[int, int] = getattr(bot, "profile_status_map", {}) or {}
    msg_id = status_map.get(interaction.user.id)
    if msg_id:
        try:
            await interaction.followup.edit_message(message_id=msg_id, content=text)
        except Exception:
            # fallback: send ephemeral followup
            try:
                await interaction.followup.send(text, ephemeral=True)
            except Exception:
                pass
    else:
        # if mapping missing, just send a followup and store it
        try:
            msg = await interaction.followup.send(text, ephemeral=True)
            status_map[interaction.user.id] = msg.id
            setattr(bot, "profile_status_map", status_map)
        except Exception:
            pass


# ---------------- Cog ----------------
class ProfileCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        ensure_files_and_db()
        self.profiles = load_profiles()  # dict keyed by str(user_id)
        # map user_id -> status_message_id (ephemeral followup)
        # stored on bot object for persistence across cogs/instances in runtime
        if not hasattr(bot, "profile_status_map"):
            setattr(bot, "profile_status_map", {})

    @commands.Cog.listener()
    async def on_ready(self):
        # just informational
        print("[Profile] Cog loaded")

    @app_commands.command(name="profile", description="Просмотр/редактирование профиля")
    @app_commands.describe(member="Упомяните пользователя для просмотра его профиля")
    async def profile(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        target = member or interaction.user
        uid_str = str(target.id)

        # ensure profile exists
        if uid_str not in self.profiles:
            self.profiles[uid_str] = {"gender": None, "age": None, "games": [], "servers": []}
            save_profiles(self.profiles)
            upsert_profile_db(int(uid_str), self.profiles[uid_str])

        profile = self.profiles[uid_str]
        embed = make_profile_embed(target, profile)

        # If owner -> attach edit view; otherwise view is None (read-only)
        if target.id == interaction.user.id:
            view = ProfileEditView(owner_id=interaction.user.id, profiles_ref=self.profiles, bot=self.bot)
            # send main response (embed + view) as ephemeral
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            # send the status followup message and store its id
            try:
                msg = await interaction.followup.send("Изменений пока нет", ephemeral=True)
                status_map: Dict[int, int] = getattr(self.bot, "profile_status_map", {})
                status_map[interaction.user.id] = msg.id
                setattr(self.bot, "profile_status_map", status_map)
            except Exception:
                pass
        else:
            # Viewing someone else's profile — no view, no status message
            await interaction.response.send_message(embed=embed, ephemeral=True)


# ----------------- Setup -----------------
async def setup(bot: commands.Bot):
    await bot.add_cog(ProfileCog(bot))