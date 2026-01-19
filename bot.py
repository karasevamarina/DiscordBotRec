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
import math
import yt_dlp
import traceback

# ==========================================
# ☢️ THE "NUCLEAR" PATCH v61 (Stable Master)
# ==========================================

# 1. Login Patch (USER BOT MODE)
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

# 2. DIRECT SEND (STABLE UPLOAD FIX)
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
        # FIX: Always send payload_json for files
        payload = {'content': str(content) if content else ""}
        data.add_field('payload_json', json.dumps(payload))
        
        for i, file in enumerate(files_to_send):
            file.fp.seek(0)
            data.add_field(
                f'files[{i}]', 
                file.fp, 
                filename=file.filename,
                content_type='application/octet-stream' 
            )
        
        headers.pop("Content-Type", None) 
        
        try:
            async with session.post(url, data=data, headers=headers) as resp:
                if resp.status not in [200, 201]:
                    print(f"❌ Upload Failed: {resp.status}")
                    if hasattr(self, 'send'): 
                        await self.send(f"❌ **Upload Failed.** Status: {resp.status}")
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
# 🧠 SYNC SINK (RECORDER STABLE)
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
# 🎵 SAFE MERGE & SPLIT (RECORDER STABLE)
# ==========================================
async def split_audio_if_large(filepath, limit_mb=9):
    if not os.path.exists(filepath): return []
    
    file_size_mb = os.path.getsize(filepath) / (1024 * 1024)
    if file_size_mb <= limit_mb:
        return [filepath]

    chunk_duration = 500 
    
    base_name = filepath.rsplit('.', 1)[0]
    ext = filepath.rsplit('.', 1)[1]
    output_pattern = f"{base_name}_part%03d.{ext}"
    
    cmd = [
        'ffmpeg', '-y', '-i', filepath,
        '-f', 'segment', 
        '-segment_time', str(chunk_duration), 
        '-c', 'copy', 
        output_pattern
    ]
    
    process = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    await process.communicate()
    
    parts = []
    i = 0
    while True:
        part_name = f"{base_name}_part{i:03d}.{ext}"
        if os.path.exists(part_name):
            parts.append(part_name)
            i += 1
        else:
            break
            
    return parts

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
SECRET_KEY = os.getenv('KEY')
if SECRET_KEY:
    SECRET_KEY = SECRET_KEY.strip()

AUTHORIZED_USERS = set() 
MERGE_MODE = False
SESSION_START_TIME = None 
AUTO_REC_MODE = None 

# AUDIO FX GLOBALS
VOLUME_LEVEL = 1.0 # 1.0 = 100%
BASS_ACTIVE = False
FOLLOW_MODE = False

# --- SETUP ---
intents = discord.Intents.default()
intents.message_content = True 
intents.members = True 
intents.voice_states = True 

bot = commands.Bot(command_prefix='+', intents=intents, help_command=None)

# --- 🔒 THE GATEKEEPER ---
@bot.check
async def global_login_check(ctx):
    if ctx.command.name == 'login': return True
    if ctx.author.id in AUTHORIZED_USERS: return True
    await ctx.send("❌ **Access Denied.** Please use `+login <key>` first.")
    return False

# --- 😊 FRIENDLY ERROR HANDLER ---
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CheckFailure): return
    if isinstance(error, commands.CommandNotFound): return
    
    if isinstance(error, commands.CommandInvokeError):
        original = error.original
        if isinstance(original, discord.Forbidden):
            return await ctx.send("❌ I don't have permission to join/speak in that channel.")
        if isinstance(original, discord.ClientException):
            return await ctx.send(f"⚠️ {str(original)}")
    
    print(f"⚠️ UNHANDLED ERROR: {error}")
    await ctx.send("❌ An error occurred while executing the command.")

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
        await dest_channel.send("🔄 **Merging & Checking Size...**")
        merged_output = "merged_temp.mp3" 
        final_nice_name = f"Conversation_{time_str}.mp3" 
        
        result = await convert_and_merge(temp_wavs, merged_output, total_duration)
        
        if result and os.path.exists(result) and os.path.getsize(result) > 0:
            chunks = await split_audio_if_large(result)
            if len(chunks) > 1:
                await dest_channel.send(f"📦 File > 9MB. Sending {len(chunks)} parts:")
                for idx, chunk in enumerate(chunks):
                    chunk_nice_name = f"Conversation_{time_str}_Part{idx+1}.mp3"
                    await dest_channel.send(f"**Part {idx+1}:**", file=discord.File(chunk, filename=chunk_nice_name))
                    os.remove(chunk)
                os.remove(result)
            else:
                await dest_channel.send("Here is the full conversation:", 
                                      file=discord.File(result, filename=final_nice_name))
                os.remove(result)
        else:
            await dest_channel.send("❌ Merge failed. Sending separate files.")
            MERGE_MODE = False 

    if not MERGE_MODE:
        if temp_wavs:
            await dest_channel.send("Here are the synced recordings:")

        for idx, wav in enumerate(temp_wavs):
            mp3_name = real_names[idx] 
            await convert_wav_to_mp3_padded(wav, mp3_name, total_duration)
            
            if os.path.exists(mp3_name):
                chunks = await split_audio_if_large(mp3_name)
                
                if len(chunks) > 1:
                     for c_idx, chunk in enumerate(chunks):
                        await dest_channel.send(
                            f"**{mp3_name[:-4]} (Part {c_idx+1}):**",
                            file=discord.File(chunk, filename=f"{mp3_name[:-4]}_Part{c_idx+1}.mp3")
                        )
                        os.remove(chunk)
                else:
                    await dest_channel.send(file=discord.File(mp3_name))
                
                if os.path.exists(mp3_name): os.remove(mp3_name)

    for f in temp_wavs:
        if os.path.exists(f): os.remove(f)

# --- REUSABLE RECORDING FUNCTION ---
async def start_recording_logic(ctx, merge_flag):
    if len(bot.voice_clients) == 0:
        return await ctx.send("❌ I am not in a VC.")
    
    vc = bot.voice_clients[0]
    if vc.recording:
        return await ctx.send("⚠️ Already recording.")

    global MERGE_MODE, SESSION_START_TIME
    MERGE_MODE = merge_flag
    SESSION_START_TIME = datetime.datetime.now() 

    vc.start_recording(
        SyncWaveSink(), 
        finished_callback, 
        ctx.channel 
    )
    
    ist = pytz.timezone('Asia/Kolkata')
    start_time = datetime.datetime.now(ist).strftime("%I:%M %p")
    mode_str = "Merged" if merge_flag else "Synced"
    await ctx.send(f"🔴 **Recording Started ({mode_str}) at {start_time} IST!**")

# ==========================================
# 🐕 ROBUST FOLLOW MODE EVENT (Fix v61)
# ==========================================
@bot.event
async def on_voice_state_update(member, before, after):
    # Only if Follow Mode is ON
    if not FOLLOW_MODE: return
    
    # Only follow the Authorized Users (Owner)
    if member.id not in AUTHORIZED_USERS: return
    
    # If user joined/moved to a new channel
    if after.channel is not None and after.channel != before.channel:
        try:
            vc = member.guild.voice_client
            
            # Case 1: Bot is not connected at all -> Connect
            if not vc:
                await after.channel.connect()
                print(f"🐕 Followed to {after.channel.name}")
            
            # Case 2: Bot is connected but in wrong channel -> Move
            elif vc.channel.id != after.channel.id:
                # Note: This will stop music/recording as connection resets
                await vc.move_to(after.channel)
                print(f"🐕 Moved to {after.channel.name}")
                
        except Exception as e:
            print(f"Follow Error: {e}")

# --- COMMANDS ---

@bot.event
async def on_ready():
    print(f'Logged in as "{bot.user.name}"')
    if SECRET_KEY:
        print("✅ Secret Key Loaded.")
    else:
        print("⚠️ Warning: No 'KEY' secret found.")
    print("✅ Nuclear Patch v61 (Stable Master) Active.")

@bot.command()
async def login(ctx, *, key: str):
    try: await ctx.message.delete()
    except: pass
    
    if ctx.author.id in AUTHORIZED_USERS:
        return await ctx.send("✅ You are already logged in.")

    if not SECRET_KEY:
        return await ctx.send("⚠️ **System Error:** KEY Secret is missing.")

    if key.strip() == SECRET_KEY:
        AUTHORIZED_USERS.add(ctx.author.id)
        await ctx.send(f"✅ **Access Granted.** Welcome, {ctx.author.display_name}.")
    else:
        await ctx.send("❌ **Wrong Key.** Access Denied.")

@bot.command()
async def help(ctx):
    msg = (
        "**🎙️ User Recorder**\n"
        "`+login <key>` - Unlock the bot\n"
        "`+join` - Find you and join VC\n"
        "`+joinid <id>` - Join specific Channel ID\n"
        "`+autorec on/off` - Auto Record when joining\n"
        "`+record` - Synced Separate Files\n"
        "`+recordall` - Synced & Merged File\n"
        "`+stop` - Stop & Upload\n"
        "`+dc` - Stop & Disconnect\n"
        "`+m` - Toggle Mute\n"
        "`+deaf` - Toggle Deafen\n"
        "`+follow` - Toggle Auto-Follow Mode\n"
        "\n**🎵 Universal Player**\n"
        "`+play [Song/URL]` - Play/Queue\n"
        "`+skip` - Skip song\n"
        "`+pause` - Pause playback\n"
        "`+resume` - Resume playback\n"
        "`+vol <0-500>` - Set Volume\n"
        "`+bass` - Toggle Deep Bass Mode\n"
        "`+queue` - View Queue\n"
        "`+pstop` - Stop Player"
    )
    await ctx.send(msg)

@bot.command()
async def autorec(ctx, option: str = None, mode: str = None):
    global AUTO_REC_MODE
    
    if option is None:
        current = "OFF" if AUTO_REC_MODE is None else f"ON ({AUTO_REC_MODE})"
        return await ctx.send(f"ℹ️ AutoRec is currently: **{current}**")
    
    option = option.lower()
    
    if option == "off":
        AUTO_REC_MODE = None
        await ctx.send("✅ Auto-Record disabled.")
        return

    if option == "on":
        if mode:
            option = mode.lower() 
        else:
            return await ctx.send("⚠️ Please specify mode: `+autorec separate` or `+autorec merged`")

    if option in ["separate", "normal"]:
        AUTO_REC_MODE = 'separate'
        await ctx.send("✅ Auto-Record set to: **Separate Files**")
    elif option in ["merged", "all"]:
        AUTO_REC_MODE = 'merged'
        await ctx.send("✅ Auto-Record set to: **Merged File**")
    else:
        await ctx.send("❌ Invalid mode. Use `separate`, `merged`, or `off`.")

# --- MUTE/DEAF (Robust v31 Logic) ---
@bot.command()
async def m(ctx):
    if len(bot.voice_clients) == 0:
        return await ctx.send("❌ Not in a VC.")
    vc = bot.voice_clients[0]
    
    try:
        current_mute = vc.guild.me.voice.self_mute
        current_deaf = vc.guild.me.voice.self_deaf
        new_mute = not current_mute
    except:
        new_mute = True
        current_deaf = False
    
    payload = {
        "op": 4,
        "d": {
            "guild_id": vc.channel.guild.id, 
            "channel_id": vc.channel.id,
            "self_mute": new_mute,
            "self_deaf": current_deaf
        }
    }
    await bot.ws.send_as_json(payload)
    status = "🔇 **Muted**" if new_mute else "🎙️ **Unmuted**"
    await ctx.send(f"✅ Mic is now {status}.")

@bot.command()
async def deaf(ctx):
    if len(bot.voice_clients) == 0:
        return await ctx.send("❌ Not in a VC.")
    vc = bot.voice_clients[0]
    
    try:
        current_mute = vc.guild.me.voice.self_mute
        current_deaf = vc.guild.me.voice.self_deaf
        new_deaf = not current_deaf
    except:
        new_deaf = True
        current_mute = False
    
    payload = {
        "op": 4,
        "d": {
            "guild_id": vc.channel.guild.id,
            "channel_id": vc.channel.id,
            "self_mute": current_mute,
            "self_deaf": new_deaf
        }
    }
    await bot.ws.send_as_json(payload)
    status = "🔕 **Deafened**" if new_deaf else "🔔 **Undeafened**"
    await ctx.send(f"✅ Headset is now {status}.")

# -------------------------------------------------------

@bot.command()
async def join(ctx):
    await ctx.send("🔍 Scanning servers...")
    found = False
    for guild in bot.guilds:
        member = guild.get_member(ctx.author.id)
        if member and member.voice:
            await member.voice.channel.connect() 
            await ctx.send(f"👍 Joined **{member.voice.channel.name}** in **{guild.name}**!")
            found = True
            
            if AUTO_REC_MODE:
                await asyncio.sleep(1) 
                is_merge = (AUTO_REC_MODE == 'merged')
                await start_recording_logic(ctx, is_merge)
            break
            
    if not found:
        await ctx.send("❌ I couldn't find you in any Voice Channel.")

@bot.command()
async def joinid(ctx, channel_id: str):
    channel = bot.get_channel(int(channel_id))
    if isinstance(channel, discord.VoiceChannel):
        await channel.connect()
        await ctx.send(f"👍 Joined **{channel.name}**")
        
        if AUTO_REC_MODE:
            await asyncio.sleep(1)
            is_merge = (AUTO_REC_MODE == 'merged')
            await start_recording_logic(ctx, is_merge)
    else:
        await ctx.send("❌ Not a voice channel.")

@bot.command()
async def record(ctx):
    await start_recording_logic(ctx, False)

@bot.command()
async def recordall(ctx):
    await start_recording_logic(ctx, True)

@bot.command()
async def stop(ctx):
    if len(bot.voice_clients) == 0:
        return await ctx.send("Not connected.")
    vc = bot.voice_clients[0]
    
    if vc.recording:
        vc.stop_recording()
        await ctx.send("💾 **Saving & Uploading... (Bot will stay in VC)**")
    else:
        await ctx.send("❓ Not recording.")

@bot.command()
async def dc(ctx):
    if len(bot.voice_clients) == 0:
        return await ctx.send("Not connected.")
    vc = bot.voice_clients[0]
    
    if vc.recording:
        vc.stop_recording()
        await ctx.send("💾 **Saving & Uploading before Disconnect...**")
    
    await asyncio.sleep(1) 
    await vc.disconnect()
    await ctx.send("👋 **Disconnected.**")

# ==========================================
# 🎵 PLAYER (FX ENABLED)
# ==========================================

queues = {}

def get_queue_id(ctx):
    if ctx.guild: return ctx.guild.id
    return ctx.author.id

def play_next_in_queue(ctx):
    q_id = get_queue_id(ctx)
    if q_id in queues and queues[q_id]:
        track = queues[q_id].pop(0)
        coro = ctx.send(f"▶️ **Now Playing:** {track['title']}")
        asyncio.run_coroutine_threadsafe(coro, bot.loop)
        play_audio_core(ctx, track['url'], track['title'])

def play_audio_core(ctx, url, title):
    if len(bot.voice_clients) == 0: return
    vc = bot.voice_clients[0]
    
    # --- AUDIO FX FILTER BUILDER ---
    filters = []
    if VOLUME_LEVEL != 1.0:
        filters.append(f"volume={VOLUME_LEVEL}")
    if BASS_ACTIVE:
        filters.append("bass=g=20")
        
    filter_str = ""
    if filters:
        filter_str = f' -filter:a "{",".join(filters)}"'
    
    ffmpeg_opts = {
        'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
        'options': f'-vn{filter_str}' 
    }
    
    def on_finish(error):
        if error: print(f"Player Error: {error}")
        coro = ctx.send(f"✅ **Finished:** {title}")
        asyncio.run_coroutine_threadsafe(coro, bot.loop)
        play_next_in_queue(ctx)

    try:
        source = discord.FFmpegPCMAudio(url, **ffmpeg_opts)
        vc.play(source, after=on_finish)
    except Exception as e:
        print(f"Play Core Error: {e}")

@bot.command()
async def play(ctx, *, query: str = None):
    try:
        if len(bot.voice_clients) == 0:
             return await ctx.send("❌ **Not in a VC.** Please use `+join` first.")
        vc = bot.voice_clients[0]

        target_url = None
        title = "Unknown Track"
        is_search = False

        if ctx.message.attachments:
            target_url = ctx.message.attachments[0].url
            title = ctx.message.attachments[0].filename
            await ctx.send("📂 **Processing attached file...**")

        elif ctx.message.reference:
            ref = ctx.message.reference
            if ref.cached_message and ref.cached_message.attachments:
                target_url = ref.cached_message.attachments[0].url
                title = ref.cached_message.attachments[0].filename
            if not target_url:
                try:
                    ref_msg = await ctx.channel.fetch_message(ref.message_id)
                    if ref_msg.attachments:
                        target_url = ref_msg.attachments[0].url
                        title = ref_msg.attachments[0].filename
                except: pass
            if target_url: await ctx.send("↩️ **Queuing Replied Audio...**")

        elif query and (query.startswith("http") or query.startswith("www")):
            target_url = query.strip()
            title = "Direct Link"
            await ctx.send("🔗 **Processing Direct Link...**")

        elif query:
            is_search = True
            await ctx.send(f"☁️ **Searching SoundCloud for:** `{query}`...")
        
        else:
            return await ctx.send("❌ **No audio found.** Provide a URL, name, or file.")

        if is_search:
            ydl_opts = {
                'format': 'bestaudio/best', 'noplaylist': True, 
                'quiet': True, 'no_warnings': True, 
                'source_address': '0.0.0.0', 'nocheckcertificate': True
            }
            loop = asyncio.get_event_loop()
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = await loop.run_in_executor(None, lambda: ydl.extract_info(f"scsearch1:{query}", download=False))
                if 'entries' in info and info['entries']:
                    target_url = info['entries'][0]['url']
                    title = info['entries'][0].get('title', 'Unknown Track')
                else:
                    return await ctx.send("❌ No results found.")

        q_id = get_queue_id(ctx)
        if q_id not in queues: queues[q_id] = []

        if vc.is_playing() or vc.is_paused():
            queues[q_id].append({'url': target_url, 'title': title})
            await ctx.send(f"📝 **Added to Queue:** {title}")
        else:
            await ctx.send(f"▶️ **Now Playing:** {title}")
            play_audio_core(ctx, target_url, title)

    except Exception as e:
        await ctx.send(f"❌ **Error:** {e}")

# --- NEW COMMANDS (Volume, Bass, Follow) ---

@bot.command()
async def vol(ctx, volume: int):
    global VOLUME_LEVEL
    if volume < 0: return await ctx.send("❌ Volume cannot be negative.")
    
    # 100 = 1.0, 200 = 2.0
    VOLUME_LEVEL = volume / 100
    await ctx.send(f"🔊 **Volume set to {volume}%.** (Applies to next song)")

@bot.command()
async def bass(ctx):
    global BASS_ACTIVE
    BASS_ACTIVE = not BASS_ACTIVE
    state = "ON 🔥" if BASS_ACTIVE else "OFF"
    await ctx.send(f"🎸 **Bass Boost is {state}.** (Applies to next song)")

@bot.command()
async def follow(ctx):
    global FOLLOW_MODE
    FOLLOW_MODE = not FOLLOW_MODE
    state = "ENABLED 🐕" if FOLLOW_MODE else "DISABLED"
    await ctx.send(f"👣 **Auto-Follow Mode is {state}.**")

@bot.command()
async def skip(ctx):
    if len(bot.voice_clients) == 0: return await ctx.send("❌ Not in VC.")
    vc = bot.voice_clients[0]
    if vc.is_playing() or vc.is_paused():
        vc.stop()
        await ctx.send("⏭️ **Skipped.**")
    else:
        await ctx.send("❓ Nothing to skip.")

@bot.command()
async def pause(ctx):
    if len(bot.voice_clients) == 0: return
    vc = bot.voice_clients[0]
    if vc.is_playing():
        vc.pause()
        await ctx.send("⏸️ **Paused.**")

@bot.command()
async def resume(ctx):
    if len(bot.voice_clients) == 0: return
    vc = bot.voice_clients[0]
    if vc.is_paused():
        vc.resume()
        await ctx.send("▶️ **Resumed.**")

@bot.command()
async def queue(ctx):
    q_id = get_queue_id(ctx)
    if q_id not in queues or not queues[q_id]:
        return await ctx.send("📭 **Queue is empty.**")
    msg = "**🎵 Up Next:**\n"
    for i, track in enumerate(queues[q_id]):
        msg += f"`{i+1}.` {track['title']}\n"
    await ctx.send(msg)

@bot.command()
async def pstop(ctx):
    if len(bot.voice_clients) == 0: return await ctx.send("❌ Not in VC.")
    vc = bot.voice_clients[0]
    q_id = get_queue_id(ctx)
    if q_id in queues: queues[q_id].clear()
    if vc.is_playing() or vc.is_paused():
        vc.stop()
        await ctx.send("⏹️ **Stopped & Queue Cleared.**")
    else:
        await ctx.send("❓ Nothing playing.")

if __name__ == "__main__":
    if not TOKEN:
        print("Error: DISCORD_TOKEN not found.")
    else:
        bot.run(TOKEN)
