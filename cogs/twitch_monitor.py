import os
import json
import asyncio
from typing import List, Any, Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

# twitchAPI imports
try:
    from twitchAPI.twitch import Twitch
except Exception:
    Twitch = None

STREAMERS_FILE = "data/streamers.json"
os.makedirs("data", exist_ok=True)

def load_streamers() -> List[str]:
    if not os.path.exists(STREAMERS_FILE):
        return []
    try:
        with open(STREAMERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_streamers(arr: List[str]):
    with open(STREAMERS_FILE, "w", encoding="utf-8") as f:
        json.dump(arr, f, indent=2, ensure_ascii=False)

async def fetch_twitch_users(twitch_client: Any, logins: List[str]) -> List[Any]:
    try:
        res = await twitch_client.get_users(logins=logins)
        if isinstance(res, list):
            return res
        if hasattr(res, "data"):
            return res.data if res.data else []
        try:
            return list(res)
        except Exception:
            return [res]
    except TypeError:
        results = []
        try:
            async for page in twitch_client.get_users(logins=logins):
                if isinstance(page, list):
                    results.extend(page)
                elif isinstance(page, dict) and "data" in page:
                    results.extend(page["data"])
                else:
                    results.append(page)
        except Exception:
            pass
        return results
    except Exception:
        return []

async def fetch_streams_pages(twitch_client: Any, logins: List[str]):
    try:
        async for page in twitch_client.get_streams_generator(user_login=logins):
            yield page
        return
    except Exception:
        pass
    try:
        res = await twitch_client.get_streams(user_login=logins)
        if isinstance(res, dict) and "data" in res:
            yield res
            return
        if isinstance(res, list):
            yield {"data": res}
            return
    except TypeError:
        try:
            async for page in twitch_client.get_streams(user_login=logins):
                if isinstance(page, dict) and "data" in page:
                    yield page
                elif isinstance(page, list):
                    yield {"data": page}
                else:
                    yield page
        except Exception:
            return
    except Exception:
        return

class TwitchCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        if Twitch is None:
            raise RuntimeError("twitchAPI.Twitch not available; install twitchAPI package")
        self.twitch = Twitch(
            os.getenv("TWITCH_CLIENT_ID"),
            os.getenv("TWITCH_CLIENT_SECRET"),
            authenticate_app=False
        )
        self.streamers = load_streamers()
        self.stream_status = {s: False for s in self.streamers}
        self.stream_messages = {}  # ID embed-сообщений
        self.poll_interval = int(os.getenv("TWITCH_POLL_INTERVAL", 30))
        bot.loop.create_task(self._start())

    async def _start(self):
        try:
            await self.twitch.authenticate_app([])
        except Exception:
            for _ in range(5):
                try:
                    await asyncio.sleep(1)
                    await self.twitch.authenticate_app([])
                    break
                except Exception:
                    continue
        self.check_streams.change_interval(seconds=self.poll_interval)
        self.check_streams.start()

    async def get_user_by_login(self, login: str) -> Optional[Any]:
        res = await fetch_twitch_users(self.twitch, [login])
        return res[0] if res else None

    @tasks.loop(seconds=30)
    async def check_streams(self):
        if not self.streamers:
            return
        channel_id = int(os.getenv("WELCOME_CHANNEL_ID", 0))
        channel = self.bot.get_channel(channel_id)
        if not channel:
            return

        for s in self.streamers:
            self.stream_status.setdefault(s, False)

        live_now = set()
        async for page in fetch_streams_pages(self.twitch, self.streamers):
            data = page.get("data") if isinstance(page, dict) else (page if isinstance(page, list) else [])
            for stream in data:
                try:
                    name = stream.get("user_login") or getattr(stream, "user_login", None) or getattr(stream, "user_name", None)
                except Exception:
                    continue
                if not name:
                    continue

                name = name.lower()
                live_now.add(name)

                title = stream.get("title") if isinstance(stream, dict) else getattr(stream, "title", "Stream")
                game = stream.get("game_name") if isinstance(stream, dict) else getattr(stream, "game_name", "Unknown")
                viewers = stream.get("viewer_count") if isinstance(stream, dict) else getattr(stream, "viewer_count", "?")

                embed = discord.Embed(
                    title=title,
                    description=f"Игра: **{game}**\nЗрителей: **{viewers}**",
                    url=f"https://twitch.tv/{name}",
                    color=discord.Color.red()
                )
                embed.set_author(name=f"{name} в эфире!", url=f"https://twitch.tv/{name}")
                embed.set_footer(text="Twitch Monitor")

                if name in self.stream_messages:
                    try:
                        msg = await channel.fetch_message(self.stream_messages[name])
                        await msg.edit(embed=embed)
                    except Exception:
                        msg = await channel.send(embed=embed)
                        self.stream_messages[name] = msg.id
                else:
                    msg = await channel.send(embed=embed)
                    self.stream_messages[name] = msg.id

                self.stream_status[name] = True

        for name in list(self.streamers):
            was_live = self.stream_status.get(name, False)
            is_live = name in live_now
            if was_live and not is_live:
                if name in self.stream_messages:
                    try:
                        old_msg = await channel.fetch_message(self.stream_messages[name])
                        await old_msg.delete()
                    except Exception:
                        pass
                    self.stream_messages.pop(name, None)

                await channel.send(f"⚫ **{name}** закончил стрим.")
                self.stream_status[name] = False

    # -------------------
    # commands
    # -------------------
    @app_commands.command(name="twitch_add", description="Добавить стримера в список мониторинга")
    async def twitch_add(self, interaction: discord.Interaction, streamer: str):
        login = streamer.strip().lower()
        await interaction.response.defer(ephemeral=True)
        try:
            user = await self.get_user_by_login(login)
        except Exception as e:
            return await interaction.followup.send(f"Ошибка при проверке Twitch: {e}", ephemeral=True)

        if not user:
            return await interaction.followup.send(f"❌ Стример `{login}` не найден.", ephemeral=True)

        uname = None
        try:
            uname = user.get("login") if isinstance(user, dict) else getattr(user, "login", None) or getattr(user, "user_login", None) or getattr(user, "user_name", None)
        except Exception:
            uname = None
        if not uname:
            uname = getattr(user, "display_name", None) or getattr(user, "name", None) or login

        uname = str(uname).lower()
        if uname in self.streamers:
            return await interaction.followup.send(f"⚠️ `{uname}` уже в списке.", ephemeral=True)

        self.streamers.append(uname)
        save_streamers(self.streamers)
        self.stream_status[uname] = False
        return await interaction.followup.send(f"✅ `{uname}` добавлен для мониторинга.", ephemeral=True)

    @app_commands.command(name="twitch_remove", description="Удалить стримера из мониторинга")
    async def twitch_remove(self, interaction: discord.Interaction, streamer: str):
        login = streamer.strip().lower()
        if login not in self.streamers:
            return await interaction.response.send_message(f"⚠️ `{login}` нет в списке.", ephemeral=True)
        self.streamers.remove(login)
        save_streamers(self.streamers)
        self.stream_status.pop(login, None)
        self.stream_messages.pop(login, None)
        return await interaction.response.send_message(f"🗑️ `{login}` удалён.", ephemeral=True)

    @app_commands.command(name="twitch_list", description="Показать список отслеживаемых стримеров")
    async def twitch_list(self, interaction: discord.Interaction):
        if not self.streamers:
            return await interaction.response.send_message("📭 Список пуст.", ephemeral=True)
        text = "\n".join(f"• {s}" for s in self.streamers)
        return await interaction.response.send_message(f"📜 **Отслеживаемые стримеры:**\n{text}", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(TwitchCog(bot))