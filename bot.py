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
# ☢️ THE "NUCLEAR" PATCH v12 (True Silence Sync)
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
# 🧠 CUSTOM SINK (THE SILENCE FIX)
# ==========================================
class SyncWaveSink(discord.sinks.WaveSink):
    def __init__(self):
        super().__init__()
        self.start_time = None
        # Discord Audio: 48000 Hz, 2 Channels (Stereo), 16-bit (2 bytes)
        # Bytes per second = 48000 * 2 * 2 = 192,000
        self.bytes_per_second = 192000

    def write(self, user_id, data):
        if self.start_time is None:
            self.start_time = time.time()

        if user_id not in self.audio_data:
            self.audio_data[user_id] = discord.sinks.core.AudioData(io.BytesIO())

        file = self.audio_data[user_id].file
        
        # 1. Calculate Expected Size based on Time
        elapsed_seconds = time.time() - self.start_time
        expected_bytes = int(elapsed_seconds * self.bytes_per_second)
        
        # 2. Calculate Missing Silence
        current_bytes = file.tell()
        padding_needed = expected_bytes - current_bytes
        
        # 3. Inject Silence (Zeros) if lag > 20ms
        if padding_needed > 3840: # 3840 bytes = 20ms (one packet)
            # Limit padding to avoid memory crashes on huge lags (cap at 10s at a time)
            chunk_size = min(padding_needed, 1920000) 
            file.write(b'\x00' * chunk_size)
            
        # 4. Write Actual Audio
        file.write(data)

# ==========================================
# 🎵 CONVERSION & MERGE
# ==========================================
async def convert_and_merge(file_list, output_filename, merge=False):
    if not file_list: return None
    
    # If merging, mix everything
    if merge:
        cmd = ['ffmpeg', '-y']
        for f in file_list:
            cmd.extend(['-i', f])
        # Mix + Compress to MP3
        cmd.extend(['-filter_complex', f'amix=inputs={len(file_list)}:duration=longest:dropout_transition=3', '-b:a', '128k', output_filename])
    
    # If not merging, we just return the list (we convert individually in callback)
    # The callback logic below handles individual conversion
    else:
        return None 
        
    process = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    await process.communicate()
    return output_filename

async def convert_wav_to_mp3(wav_filename, mp3_filename):
    cmd = ['ffmpeg', '-y', '-i', wav_filename, '-b:a', '128k', mp3_filename]
    process = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    await process.communicate()
    return mp3_filename

# ==========================================

# --- CONFIGURATION ---
TOKEN = os.getenv('DISCORD_TOKEN')
MERGE_MODE = False

# --- SETUP ---
intents = discord.Intents.default()
intents.message_content = True 

bot = commands.Bot(command_prefix='+', intents=intents, help_command=None)

# --- HELPER FUNCTIONS ---
async def finished_callback(sink, dest_channel, *args):
    await dest_channel.send("✅ **Recording finished.** Processing sync & filenames...")
    
    saved_wavs = []
    final_files = []
    
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.datetime.now(ist)
    time_str = now.strftime("%I-%M-%p")

    # 1. Process Raw WAV data
    for user_id, audio in sink.audio_data.items():
        username = await asyncio.to_thread(fetch_real_name_sync, user_id, bot.http.token)
        safe_name = "".join(x for x in username if x.isalnum() or x in "._- ")
        
        # Save Raw WAV
        wav_name = f"{safe_name}_{time_str}.wav"
        with open(wav_name, "wb") as f:
            f.write(audio.file.getbuffer())
        saved_wavs.append(wav_name)
    
    global MERGE_MODE
    
    if MERGE_MODE:
        await dest_channel.send("🔄 **Merging synced audio...**")
        merged_name = f"Conversation_{time_str}.mp3"
        result = await convert_and_merge(saved_wavs, merged_name, merge=True)
        
        if result and os.path.exists(result):
            await dest_channel.send("Here is the full conversation:", file=discord.File(result))
            os.remove(result)
        else:
            await dest_channel.send("❌ Merge failed.")
    else:
        # Convert each WAV to MP3 individually
        for wav in saved_wavs:
            mp3_name = wav.replace(".wav", ".mp3")
            await convert_wav_to_mp3(wav, mp3_name)
            if os.path.exists(mp3_name):
                final_files.append(discord.File(mp3_name))
        
        if final_files:
            await dest_channel.send("Here are the synced recordings:", files=final_files)
        else:
            await dest_channel.send("No audio recorded.")

    # Cleanup WAVs and MP3s
    for f in saved_wavs:
        if os.path.exists(f): os.remove(f)
    for f in final_files:
        if os.path.exists(f.filename): os.remove(f.filename)

# --- COMMANDS ---

@bot.event
async def on_ready():
    print(f'Logged in as "{bot.user.name}"')
    print("✅ Nuclear Patch v12 (SYNC ENGINE) Active.")

@bot.command()
async def help(ctx):
    msg = (
        "**🎙️ User Recorder**\n"
        "`+join` - Find you and join VC\n"
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

    global MERGE_MODE
    MERGE_MODE = False 

    # USE CUSTOM SYNC SINK
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

    global MERGE_MODE
    MERGE_MODE = True 

    # USE CUSTOM SYNC SINK
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
