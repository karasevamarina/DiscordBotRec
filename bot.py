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
import subprocess # NEW: Required for merging

# ==========================================
# ☢️ THE "NUCLEAR" PATCH v11 (Record All & Merge)
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

# 4. Helper: DIRECT NAME FETCH
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
# 🎵 MERGE FUNCTIONALITY (FFMPEG)
# ==========================================
async def merge_audio_files(file_list, output_filename):
    if not file_list:
        return None
        
    # Build FFmpeg command to mix audio
    # command: ffmpeg -i 1.mp3 -i 2.mp3 -filter_complex amix=inputs=2:duration=longest output.mp3
    
    cmd = ['ffmpeg', '-y'] # -y overwrites output
    for f in file_list:
        cmd.extend(['-i', f])
        
    # Complex filter to mix N inputs
    cmd.extend(['-filter_complex', f'amix=inputs={len(file_list)}:duration=longest:dropout_transition=3'])
    cmd.append(output_filename)
    
    try:
        # Run FFmpeg in background
        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        await process.communicate()
        return output_filename
    except Exception as e:
        print(f"Merge Error: {e}")
        return None

# ==========================================

# --- CONFIGURATION ---
TOKEN = os.getenv('DISCORD_TOKEN')
MERGE_MODE = False # Global flag to track if we want merged output

# --- SETUP ---
intents = discord.Intents.default()
intents.message_content = True 

bot = commands.Bot(command_prefix='+', intents=intents, help_command=None)

# --- HELPER FUNCTIONS ---
async def finished_callback(sink, dest_channel, *args):
    await dest_channel.send("✅ **Recording finished.** Processing filenames...")
    
    saved_files = [] # For merging
    discord_files = [] # For sending individual files
    
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.datetime.now(ist)
    time_str = now.strftime("%I-%M-%p")

    # 1. Process all individual files
    for user_id, audio in sink.audio_data.items():
        username = await asyncio.to_thread(fetch_real_name_sync, user_id, bot.http.token)
        safe_name = "".join(x for x in username if x.isalnum() or x in "._- ")
        filename = f"{safe_name}_{time_str}.mp3"
        
        # Save locally for merging
        with open(filename, "wb") as f:
            f.write(audio.file.getbuffer())
        saved_files.append(filename)
        
        # Prepare for Discord Upload (Reset pointer)
        audio.file.seek(0)
        discord_files.append(discord.File(audio.file, filename))

    global MERGE_MODE
    
    if MERGE_MODE:
        # --- MERGE MODE ENABLED ---
        await dest_channel.send("🔄 **Merging audio streams... (This might take a moment)**")
        merged_filename = f"Conversation_{time_str}.mp3"
        
        result = await merge_audio_files(saved_files, merged_filename)
        
        if result and os.path.exists(result):
            # Send ONLY the merged file
            await dest_channel.send("Here is the full conversation:", file=discord.File(result))
            os.remove(result) # Cleanup
        else:
            await dest_channel.send("❌ Merge failed. Sending separate files instead.")
            await dest_channel.send(files=discord_files)
            
        MERGE_MODE = False # Reset flag
    else:
        # --- NORMAL MODE ---
        if discord_files:
            await dest_channel.send("Here are the recordings:", files=discord_files)
        else:
            await dest_channel.send("No audio was recorded (Silence).")

    # Cleanup local temp files
    for f in saved_files:
        if os.path.exists(f):
            os.remove(f)

# --- COMMANDS ---

@bot.event
async def on_ready():
    print(f'Logged in as "{bot.user.name}"')
    print("✅ Nuclear Patch v11 (Merge Supported) Active.")

@bot.command()
async def help(ctx):
    msg = (
        "**🎙️ User Recorder**\n"
        "`+join` - Find you and join VC\n"
        "`+record` - Record Separate Files\n"
        "`+recordall` - Record & Merge into ONE file\n"
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

    global MERGE_MODE
    MERGE_MODE = False # Explicitly set to false

    vc.start_recording(
        discord.sinks.MP3Sink(), 
        finished_callback, 
        ctx.channel 
    )
    ist = pytz.timezone('Asia/Kolkata')
    start_time = datetime.datetime.now(ist).strftime("%I:%M %p")
    await ctx.send(f"🔴 **Recording Started (Separate Files) at {start_time} IST!**")

@bot.command()
async def recordall(ctx):
    if len(bot.voice_clients) == 0:
        return await ctx.send("❌ I am not in a VC.")
    vc = bot.voice_clients[0]
    if vc.recording:
        return await ctx.send("Already recording.")

    # Enable Merging
    global MERGE_MODE
    MERGE_MODE = True 

    vc.start_recording(
        discord.sinks.MP3Sink(), 
        finished_callback, 
        ctx.channel 
    )
    ist = pytz.timezone('Asia/Kolkata')
    start_time = datetime.datetime.now(ist).strftime("%I:%M %p")
    await ctx.send(f"🔴 **Recording Started (MERGE MODE) at {start_time} IST!**")

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
