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
# ☢️ THE "NUCLEAR" PATCH v8 (Sync & Names)
# ==========================================

# 1. Login Patch
async def patched_login(self, token):
    self.token = token.strip().strip('"')
    self._token_type = ""
    
    if not hasattr(self, '_HTTPClient__session') or getattr(self, '_HTTPClient__session').__class__.__name__ == '_MissingSentinel':
        self._HTTPClient__session = aiohttp.ClientSession()

    req = urllib.request.Request("https://discord.com/api/v9/users/@me")
    req.add_header("Authorization", self.token)
    req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
    
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise discord.LoginFailure("Invalid User Token.")
        raise

# 2. DIRECT SEND (File Uploads)
async def direct_send(self, content=None, **kwargs):
    if hasattr(self, 'channel'):
        channel_id = self.channel.id 
    elif hasattr(self, 'id'):
        channel_id = self.id 
    else:
        return

    url = f"https://discord.com/api/v9/channels/{channel_id}/messages"
    
    global bot
    session = bot.http._HTTPClient__session
    
    headers = {
        "Authorization": bot.http.token,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }

    files = kwargs.get('files')
    if files:
        data = aiohttp.FormData()
        if content:
            data.add_field('payload_json', json.dumps({'content': str(content)}))
        
        for i, file in enumerate(files):
            file.fp.seek(0)
            data.add_field(
                f'files[{i}]', 
                file.fp, 
                filename=file.filename,
                content_type='audio/mpeg' 
            )
        
        headers.pop("Content-Type", None) 
        try:
            async with session.post(url, data=data, headers=headers) as resp:
                return await resp.json()
        except:
            return None
    else:
        headers["Content-Type"] = "application/json"
        payload = {}
        if content:
            payload['content'] = str(content)
            
        async with session.post(url, json=payload, headers=headers) as resp:
            return await resp.json()

# 3. Request Patch
original_request = discord.http.HTTPClient.request
async def patched_request(self, route, **kwargs):
    headers = kwargs.get('headers', {})
    headers['Authorization'] = self.token
    headers['User-Agent'] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    kwargs['headers'] = headers
    
    try:
        return await original_request(self, route, **kwargs)
    except discord.HTTPException as e:
        if e.status == 401:
            return []
        raise e

# 4. Helper: DIRECT NAME FETCH (Uses urllib to guarantee success)
def fetch_real_name_sync(user_id, token):
    url = f"https://discord.com/api/v9/users/{user_id}"
    req = urllib.request.Request(url)
    req.add_header("Authorization", token)
    req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
    
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            return data.get('global_name') or data.get('username')
    except:
        return f"User_{user_id}"

# Apply Patches
discord.http.HTTPClient.static_login = patched_login
discord.http.HTTPClient.request = patched_request
discord.abc.Messageable.send = direct_send
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
        # USE DIRECT SYNC FETCH (Fixes the User_994 issue)
        username = await asyncio.to_thread(fetch_real_name_sync, user_id, bot.http.token)
            
        # Clean the name
        safe_name = "".join(x for x in username if x.isalnum() or x in "._- ")
        
        # Format: Username_Date_Time_IST.mp3
        filename = f"{safe_name}_{time_str}_IST.mp3"
        
        audio.file.seek(0)
        files.append(discord.File(audio.file, filename))

    if files:
        await dest_channel.send(f"Here are the recordings:", files=files)
    else:
        await dest_channel.send("No audio was recorded (Silence).")

# --- COMMANDS ---

@bot.event
async def on_ready():
    print(f'Logged in as "{bot.user.name}"')
    print("✅ Nuclear Patch v8 Active.")

@bot.command()
async def help(ctx):
    msg = (
        "**🎙️ User Recorder**\n"
        "`+join` - Find you and join VC\n"
        "`+joinid <id>` - Join specific Channel ID\n"
        "`+record` - Start recording\n"
        "`+stop` - Stop & Upload\n"
        "`+name <text>` - Change Display Name"
    )
    await ctx.send(msg)

@bot.command()
async def name(ctx, *, new_name: str):
    url = "https://discord.com/api/v9/users/@me"
    headers = {
        "Authorization": bot.http.token,
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    payload = {"global_name": new_name}
    
    session = bot.http._HTTPClient__session
    async with session.patch(url, json=payload, headers=headers) as resp:
        if resp.status == 200:
            await ctx.send(f"✅ Display Name changed to: **{new_name}**")
        elif resp.status == 429:
            await ctx.send("❌ Rate Limited: Try again in 10 minutes.")
        else:
            text = await resp.text()
            await ctx.send(f"❌ Failed ({resp.status}): {text}")

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

    # ADDED FILTERS TO FIX SILENCE SYNC
    # 'aresample=async=1' tries to keep audio synced with wall clock time
    vc.start_recording(
        discord.sinks.MP3Sink(options={'options': '-af aresample=async=1'}), 
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
