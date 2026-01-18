import discord
from discord.ext import commands
import os
import datetime
import pytz 
import asyncio
import discord.http 
import json
import urllib.request
import aiohttp 

# ==========================================
# 🕵️ THE "STEALTH MODE" PATCH
# ==========================================

# 1. Patch Login (Login as User, Create Session, Store Token)
async def patched_login(self, token):
    self.token = token.strip()
    self._token_type = "" # Clear this to avoid "Bot " prefix logic
    
    # Create Session manually if missing
    if not hasattr(self, '_HTTPClient__session') or getattr(self, '_HTTPClient__session').__class__.__name__ == '_MissingSentinel':
        self._HTTPClient__session = aiohttp.ClientSession()

    # Fetch Real Data (using stealth headers)
    req = urllib.request.Request("https://discord.com/api/v9/users/@me")
    req.add_header("Authorization", self.token)
    req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise discord.LoginFailure("Invalid User Token.")
        raise

# 2. Patch Request (The Critical Fix for 401 Errors)
original_request = discord.http.HTTPClient.request

async def patched_request(self, route, **kwargs):
    headers = kwargs.get('headers', {})
    
    # SPOOF USER AGENT (Discord blocks 'DiscordBot' UA on User Tokens)
    headers['User-Agent'] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    
    # FORCE RAW AUTHORIZATION (No "Bot " prefix, no spaces)
    headers['Authorization'] = self.token
    
    kwargs['headers'] = headers

    try:
        return await original_request(self, route, **kwargs)
    except discord.HTTPException as e:
        # Ignore 401s for Bot-specific endpoints that Users can't access
        if e.status == 401 and ("/applications/" in route.path or "soundboard" in route.path or "interaction" in route.path):
            return []
        raise e 

# Apply the patches
discord.http.HTTPClient.static_login = patched_login
discord.http.HTTPClient.request = patched_request
# ==========================================

# --- CONFIGURATION ---
TOKEN = os.getenv('DISCORD_TOKEN')

# --- SETUP ---
intents = discord.Intents.default()
intents.message_content = True 

bot = commands.Bot(command_prefix='+', intents=intents, help_command=None)

# --- HELPER FUNCTIONS ---
async def finished_callback(sink, dest_channel, *args):
    # Plain text response for safety
    await dest_channel.send("✅ **Recording finished.** Processing filenames...")
    
    files = []
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.datetime.now(ist)
    time_str = now.strftime("%d-%m-%Y_%I-%M-%p")

    for user_id, audio in sink.audio_data.items():
        user = bot.get_user(user_id)
        if user:
            username = user.display_name
        else:
            username = f"User_{user_id}"
            
        safe_name = "".join(x for x in username if x.isalnum() or x in "._- ")
        filename = f"{safe_name}_{time_str}_IST.mp3"
        
        audio.file.seek(0)
        files.append(discord.File(audio.file, filename))

    if files:
        await dest_channel.send(f"Here are the recordings:", files=files)
    else:
        await dest_channel.send("No audio was recorded.")

# --- COMMANDS ---

@bot.event
async def on_ready():
    print(f'Logged in as "{bot.user.name}"')
    print("✅ Stealth Mode Active. Ready to record.")

@bot.command()
async def help(ctx):
    # Plain text help menu
    msg = (
        "**🎙️ User Recorder**\n"
        "`+join` - Find you and join VC\n"
        "`+joinid <id>` - Join specific Channel ID\n"
        "`+record` - Start recording\n"
        "`+stop` - Stop & Upload\n"
        "`+name <text>` - Change Name"
    )
    await ctx.send(msg)

@bot.command()
async def name(ctx, *, new_name: str):
    try:
        await bot.user.edit(username=new_name)
        await ctx.send(f"✅ Username changed to: **{new_name}**")
    except Exception as e:
        await ctx.send(f"❌ Failed: {e}")

@bot.command()
async def join(ctx):
    await ctx.send("🔍 Scanning servers...")
    found = False
    for guild in bot.guilds:
        member = guild.get_member(ctx.author.id)
        if member and member.voice:
            try:
                await member.voice.channel.connect() 
                await ctx.send(f"👍 Joined **{member.voice.channel.name}** in **{guild.name}**!")
                found = True
                break
            except Exception as e:
                await ctx.send(f"❌ Connection Error: {e}")
                return
    if not found:
        await ctx.send("❌ I couldn't find you in any Voice Channel.")

@bot.command()
async def joinid(ctx, channel_id: str):
    try:
        channel = bot.get_channel(int(channel_id))
        if isinstance(channel, discord.VoiceChannel):
            await channel.connect()
            await ctx.send(f"👍 Joined **{channel.name}**")
        else:
            await ctx.send("❌ Not a voice channel.")
    except Exception as e:
        await ctx.send(f"❌ Error: {e}")

@bot.command()
async def record(ctx):
    if len(bot.voice_clients) == 0:
        return await ctx.send("❌ I am not in a VC.")
    vc = bot.voice_clients[0]
    if vc.recording:
        return await ctx.send("Already recording.")

    vc.start_recording(
        discord.sinks.MP3Sink(), 
        finished_callback, 
        ctx.channel 
    )
    ist = pytz.timezone('Asia/Kolkata')
    start_time = datetime.datetime.now(ist).strftime("%I:%M %p")
    await ctx.send(f"🔴 **Recording Started at {start_time} IST!**")

@bot.command()
async def stop(ctx):
    if len(bot.voice_clients) == 0:
        return await ctx.send("Not connected.")
    vc = bot.voice_clients[0]
    if vc.recording:
        vc.stop_recording()
        await ctx.send("🛑 Processing...")
    await asyncio.sleep(1)
    await vc.disconnect()

if __name__ == "__main__":
    if not TOKEN:
        print("Error: DISCORD_TOKEN not found.")
    else:
        bot.run(TOKEN)
