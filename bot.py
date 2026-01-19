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
import subprocess 
import time
import io

# ==========================================
# ☢️ THE "NUCLEAR" PATCH v20 (Login System)
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

# 2. DIRECT SEND
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

    files_to_send = []
    if kwargs.get('files'):
        files_to_send.extend(kwargs['files'])
    if kwargs.get('file'):
        files_to_send.append(kwargs['file'])

    if files_to_send:
        data = aiohttp.FormData()
        if content:
            data.add_field('payload_json', json.dumps({'content': str(content)}))
        
        for i, file in enumerate(files_to_send):
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
                if resp.status != 200:
                    print(f"❌ Upload Failed: {resp.status}")
                return await resp.json()
        except Exception as e:
            print(f"❌ Upload Error: {e}")
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
# 🧠 SYNC SINK
# ==========================================
class SyncWaveSink(discord.sinks.WaveSink):
    def __init__(self):
        super().__init__()
        self.start_time = None
        self.bytes_per_second = 192000

    def write(self, data, user_id):
        if self.start_time is None:
            self.start_time = time.time()

        if user_id not in self.audio_data:
            self.audio_data[user_id] = discord.sinks.core.AudioData(io.BytesIO())

        file = self.audio_data[user_id].file
        
        elapsed_seconds = time.time() - self.start_time
        expected_bytes = int(elapsed_seconds * self.bytes_per_second)
        expected_bytes = expected_bytes - (expected_bytes % 4) 
        
        current_bytes = file.tell()
        padding_needed = expected_bytes - current_bytes
        
        if padding_needed > 3840: 
            padding_needed = padding_needed - (padding_needed % 4)
            chunk_size = min(padding_needed, 1920000) 
            file.write(b'\x00' * chunk_size)
            
        file.write(data)

# ==========================================
# 🎵 SAFE MERGE
# ==========================================
async def convert_and_merge(file_list, output_filename, duration):
    if not file_list: return None
    
    cmd = ['ffmpeg', '-y']
    for f in file_list:
        cmd.extend(['-i', f])
    
    if len(file_list) == 1:
         cmd.extend([
            '-af', 'apad', 
            '-t', str(duration),
            '-b:a', '128k', 
            output_filename
        ])
    else:
        cmd.extend([
            '-filter_complex', 
            f'amix=inputs={len(file_list)}:duration=longest:dropout_transition=3:normalize=0,apad', 
            '-t', str(duration),
            '-b:a', '128k', 
            output_filename
        ])
        
    process = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    await process.communicate()
    return output_filename

async def convert_wav_to_mp3_padded(wav_filename, mp3_filename, duration):
    cmd = [
        'ffmpeg', '-y', 
        '-i', wav_filename, 
        '-af', 'apad', 
        '-t', str(duration),
        '-b:a', '128k', 
        mp3_filename
    ]
    process = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    await process.communicate()
    return mp3_filename

# ==========================================

# --- CONFIGURATION ---
TOKEN = os.getenv('DISCORD_TOKEN')
SECRET_KEY = os.getenv('KEY') # The Login Password
AUTHORIZED_USERS = set() # Stores logged-in user IDs

MERGE_MODE = False
SESSION_START_TIME = None 

# --- SETUP ---
intents = discord.Intents.default()
intents.message_content = True 
intents.members = True 

bot = commands.Bot(command_prefix='+', intents=intents, help_command=None)

# --- 🔒 THE GATEKEEPER (LOGIN CHECK) ---
@bot.check
async def global_login_check(ctx):
    # Always allow the login command
    if ctx.command.name == 'login':
        return True
    
    # Check if user is logged in
    if ctx.author.id in AUTHORIZED_USERS:
        return True
    else:
        # Reject everyone else
        await ctx.send("❌ **You don't have permission.** Please use `+login <key>` first.")
        return False
# ---------------------------------------

# --- HELPER FUNCTIONS ---
async def finished_callback(sink, dest_channel, *args):
    global SESSION_START_TIME
    if SESSION_START_TIME:
        total_duration = (datetime.datetime.now() - SESSION_START_TIME).total_seconds()
    else:
        total_duration = 10 
        
    await dest_channel.send(f"✅ **Recording finished.** Duration: {int(total_duration)}s. Processing...")
    
    temp_wavs = [] 
    real_names = [] 
    final_files = []
    
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.datetime.now(ist)
    time_str = now.strftime("%I-%M-%p")

    i = 0
    for user_id, audio in sink.audio_data.items():
        username = None
        try:
            if hasattr(dest_channel, 'guild'):
                member = dest_channel.guild.get_member(user_id)
                if member: username = member.display_name
        except: pass
        if not username:
            user = bot.get_user(user_id)
            if user: username = user.display_name or user.name
        if not username:
            username = await asyncio.to_thread(fetch_real_name_sync, user_id, bot.http.token)

        safe_username = "".join(x for x in username if x.isalnum() or x in "._- ")
        real_name = f"{safe_username}_{time_str}.mp3"
        real_names.append(real_name)

        temp_name = f"input_{i}.wav"
        with open(temp_name, "wb") as f:
            f.write(audio.file.getbuffer())
        temp_wavs.append(temp_name)
        i += 1
    
    global MERGE_MODE
    
    if MERGE_MODE and temp_wavs:
        await dest_channel.send("🔄 **Merging & Padding...**")
        merged_output = "merged_temp.mp3" 
        final_nice_name = f"Conversation_{time_str}.mp3" 
        
        result = await convert_and_merge(temp_wavs, merged_output, total_duration)
        
        if result and os.path.exists(result) and os.path.getsize(result) > 0:
            await dest_channel.send("Here is the full conversation:", 
                                  file=discord.File(result, filename=final_nice_name))
            os.remove(result)
        else:
            await dest_channel.send("❌ Merge failed (Empty or Error). Sending separate files.")
            MERGE_MODE = False 

    if not MERGE_MODE:
        for idx, wav in enumerate(temp_wavs):
            mp3_name = real_names[idx] 
            await convert_wav_to_mp3_padded(wav, mp3_name, total_duration)
            if os.path.exists(mp3_name):
                final_files.append(discord.File(mp3_name))
        
        if final_files:
            await dest_channel.send("Here are the synced recordings:", files=final_files)
        else:
            await dest_channel.send("No audio recorded.")

    for f in temp_wavs:
        if os.path.exists(f): os.remove(f)
    for f in final_files:
        if os.path.exists(f.filename): os.remove(f.filename)

# --- COMMANDS ---

@bot.event
async def on_ready():
    print(f'Logged in as "{bot.user.name}"')
    print("✅ Nuclear Patch v20 (Login System) Active.")

# --- NEW LOGIN COMMAND ---
@bot.command()
async def login(ctx, key: str):
    # Try to delete the message for security (if bot has permission)
    try: await ctx.message.delete()
    except: pass

    if key == SECRET_KEY:
        AUTHORIZED_USERS.add(ctx.author.id)
        await ctx.send(f"✅ **Access Granted.** Welcome, {ctx.author.display_name}. You may now use the bot.")
    else:
        await ctx.send("❌ **Wrong Key.** Access Denied.")
# -------------------------

@bot.command()
async def help(ctx):
    msg = (
        "**🎙️ User Recorder**\n"
        "`+login <key>` - Unlock the bot\n"
        "`+join` - Find you and join VC\n"
        "`+joinid <id>` - Join specific Channel ID\n"
        "`+record` - Synced Separate Files\n"
        "`+recordall` - Synced & Merged File\n"
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
            await ctx.send("❌ Rate Limited.")
        else:
            await ctx.send(f"❌ Failed: {resp.status}")

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

    global MERGE_MODE, SESSION_START_TIME
    MERGE_MODE = False 
    SESSION_START_TIME = datetime.datetime.now() 

    vc.start_recording(
        SyncWaveSink(), 
        finished_callback, 
        ctx.channel 
    )
    ist = pytz.timezone('Asia/Kolkata')
    start_time = datetime.datetime.now(ist).strftime("%I:%M %p")
    await ctx.send(f"🔴 **Recording Started (Synced) at {start_time} IST!**")

@bot.command()
async def recordall(ctx):
    if len(bot.voice_clients) == 0:
        return await ctx.send("❌ I am not in a VC.")
    vc = bot.voice_clients[0]
    if vc.recording:
        return await ctx.send("Already recording.")

    global MERGE_MODE, SESSION_START_TIME
    MERGE_MODE = True 
    SESSION_START_TIME = datetime.datetime.now() 

    vc.start_recording(
        SyncWaveSink(), 
        finished_callback, 
        ctx.channel 
    )
    ist = pytz.timezone('Asia/Kolkata')
    start_time = datetime.datetime.now(ist).strftime("%I:%M %p")
    await ctx.send(f"🔴 **Recording Started (Synced + Merged) at {start_time} IST!**")

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
