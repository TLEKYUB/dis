import discord
from discord.ext import commands, tasks
import yt_dlp as youtube_dl
import asyncio

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

# แนะนำเก็บ channel per guild
voice_channels_per_guild = {}

ytdl_format_options = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0'
}

ffmpeg_options = {
    'options': '-vn'
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
        if 'entries' in data:
            data = data['entries'][0]
        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

@bot.event
async def on_ready():
    print(f"✅ เข้าสู่ระบบในชื่อ {bot.user}")
    maintain_voice_connection.start()

@bot.command()
async def join(ctx):
    global target_voice_channel_id

    # เช็คว่าผู้ใช้ที่สั่งอยู่ในห้องเสียงไหม
    if ctx.author.voice and ctx.author.voice.channel:
        channel = ctx.author.voice.channel
        try:
            # ถ้าบอทอยู่ในห้องอื่น ให้ตัดการเชื่อมต่อก่อน
            if ctx.voice_client:
                await ctx.voice_client.disconnect()

            vc = await channel.connect()
            await ctx.guild.change_voice_state(channel=channel, self_mute=False, self_deaf=True)
            target_voice_channel_id = channel.id
            await ctx.send(f"✅ เข้าห้องเสียง: {channel.name}")
        except Exception as e:
            await ctx.send(f"❌ ไม่สามารถเข้าห้องได้: {e}")
    else:
        await ctx.send("❌ คุณไม่ได้อยู่ในห้องเสียง จึงไม่สามารถสั่งให้บอทเข้าห้องได้")

@bot.command()
async def leave(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        voice_channels_per_guild.pop(ctx.guild.id, None)
        await ctx.send("👋 ออกจากห้องเสียงแล้ว")
    else:
        await ctx.send("❌ บอทยังไม่ได้อยู่ในห้องเสียง")

@bot.command()
async def play(ctx, *, search: str):
    if not ctx.voice_client:
        await ctx.send("❌ บอทยังไม่ได้อยู่ในห้องเสียง กรุณาใช้คำสั่ง t!join ก่อน")
        return

    voice_client = ctx.voice_client

    async with ctx.typing():
        try:
            player = await YTDLSource.from_url(search, loop=bot.loop, stream=True)
        except Exception as e:
            await ctx.send(f"❌ พบปัญหาในการดึงเพลง: {e}")
            return

        if voice_client.is_playing():
            voice_client.stop()

        voice_client.play(player, after=lambda e: print(f"เพลงเล่นจบ: {e}") if e else None)
        await ctx.send(f"▶️ กำลังเล่นเพลง: {player.title}")

@bot.command()
async def stop(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("⏹️ หยุดเพลงเรียบร้อยแล้ว")
    else:
        await ctx.send("❌ ไม่มีเพลงที่กำลังเล่นอยู่")

@tasks.loop(seconds=10)
async def maintain_voice_connection():
    for guild_id, channel_id in voice_channels_per_guild.items():
        guild = bot.get_guild(guild_id)
        if guild:
            channel = guild.get_channel(channel_id)
            if channel and isinstance(channel, discord.VoiceChannel):
                voice_client = guild.voice_client
                if not voice_client or not voice_client.is_connected():
                    try:
                        await channel.connect()
                        print(f"🔁 Reconnected to {channel.name} (mute)")
                    except Exception as e:
                        print(f"❌ reconnect error: {e}")

@bot.command()
async def rejoin(ctx):
    channel_id = voice_channels_per_guild.get(ctx.guild.id)
    if not channel_id:
        await ctx.send("❌ ยังไม่มีห้องเสียงที่บอทเคยเข้าร่วม")
        return

    if ctx.voice_client:
        await ctx.voice_client.disconnect()

    channel = ctx.guild.get_channel(channel_id)
    if isinstance(channel, discord.VoiceChannel):
        try:
            await channel.connect()
            await ctx.send(f"🔁 เข้าร่วมห้องเสียงเดิมอีกครั้ง: {channel.name}")
        except Exception as e:
            await ctx.send(f"❌ ไม่สามารถเข้าห้องใหม่ได้: {e}")
    else:
        await ctx.send("❌ ไม่พบห้องเสียงเดิมหรือไม่ใช่ห้องเสียง")

@bot.command()
async def helpme(ctx):
    help_text = """
**📚 คำสั่งของบอท:**

`!join` — ให้บอทเข้าห้องเสียงที่คุณอยู่ (ไม่ต้องใส่ channel_id)  
`!leave` — ให้บอทออกจากห้องเสียง  
`!play <ชื่อเพลงหรือ URL>` — เล่นเพลงจากชื่อหรือ URL (YouTube/Spotify ที่รองรับ)  
`!stop` — หยุดเพลงที่กำลังเล่น  
`!rejoin` — ให้บอทออกจากห้องเสียงแล้วเข้าห้องเสียงเดิมอีกครั้ง  
`!helpme` — แสดงคำสั่งทั้งหมดและคำอธิบาย  
"""
    await ctx.send(help_text)


bot.run("MTM3MTU4MDY0NjE1MzEzMDAyNA.GwVM9u.23hL0yHzQ1ipEGwIoH6Mf9FZIuUBG-TIDVG3vs")
