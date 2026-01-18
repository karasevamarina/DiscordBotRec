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
# 🛡️ THE "SILENCER" PATCH (Fixes 401 Errors)
# ==========================================

# 1. Patch Login (To force User Token)
async def patched_login(self, token):
    self.token = token.strip()
    self._token_type = None 
    
    # Create Session manually
    if not hasattr(self, '_HTTPClient__session') or getattr(self, '_HTTPClient__session').__class__.__name__ == '_MissingSentinel':
        self._HTTPClient__session = aiohttp.ClientSession()

    # Fetch Real Data
    req = urllib.request.Request("https://discord.com/api/v9/users/@me")
    req.add_header("Authorization", self.token)
    req.add_header("User-Agent", "DiscordBot (https://github.com/Rapptz/discord.py, 2.0.0)")
    
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise discord.LoginFailure("Invalid User Token.")
        raise

# 2. Patch Request (To silence "Unauthorized" errors for Bot-only features)
original_request = discord.http.HTTPClient.request

async def patched_request(self, route, **kwargs):
    try:
        return await original_request(self, route, **kwargs)
    except discord.HTTPException as e:
        # If Discord says "401 Unauthorized" for Commands or Sounds, ignore it!
        # These features are for Real Bots only, so we just return empty data.
        if e.status == 401 and ("/applications/" in route.path or "soundboard" in route.path):
            return [] 
        raise e # If it's a real error (like login fail), raise it.

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
    # UPDATED LOG FORMAT HERE
    print(f'Logged in as "{bot.user.name}" "{bot.user.display_name}"')
    print(f"Connected to {len(bot.guilds)} servers.")
    print("✅ Bot is stable and ignoring 401 errors.")

@bot.command()
async def help(ctx):
    embed = discord.Embed(title="🎙️ User Recorder", color=discord.Color.green())
    embed.description = "Full Recording Capability Enabled"
    embed.add_field(name="+join", value="Finds you and joins.", inline=False)
    embed.add_field(name="+joinid <id>", value="Join specific ID.", inline=False)
    embed.add_field(name="+record", value="Start recording audio.", inline=False)
    embed.add_field(name="+stop", value="Stop and Upload.", inline=False)
    embed.add_field(name="+name <text>", value="Change display name.", inline=False)
    await ctx.send(embed=embed)

@bot.command()
async def name(ctx, *, new_name: str):
    try:
        await bot.user.edit(username=new_name)
        await ctx.send(f"✅ Username changed to: **{new_name}**")
    except Exception as e:
        await ctx.send(f"❌ Failed (Discord Rate Limit?): {e}")

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
