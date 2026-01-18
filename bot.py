import discord
from discord.ext import commands
import os
import datetime
import pytz 
import asyncio
import discord.http 
import aiohttp # NEW: Required for the fix

# ==========================================
# 🔓 THE "ROBUST" USER TOKEN PATCH
# ==========================================
async def patched_login(self, token):
    # Remove whitespace
    token = token.strip()
    
    # 1. Set the token internally so the library has it
    self.token = token
    self._token_type = None # This stops the library from adding "Bot " to requests
    
    # 2. Manually verify the token using a temporary session
    # We do this because the bot's internal session isn't ready yet (Fixes your error)
    async with aiohttp.ClientSession() as session:
        headers = {"Authorization": token} # Send raw token (No "Bot " prefix)
        async with session.get("https://discord.com/api/v10/users/@me", headers=headers) as response:
            if response.status == 401:
                raise discord.LoginFailure("Invalid User Token passed.")
            elif response.status != 200:
                raise discord.HTTPException(response, "Login failed")
            
            # Return the user data so the bot knows who it is
            return await response.json()

# Apply the fix
discord.http.HTTPClient.static_login = patched_login
# ==========================================

# --- CONFIGURATION ---
TOKEN = os.getenv('DISCORD_TOKEN')

# --- SETUP ---
intents = discord.Intents.default()
intents.message_content = True 

# We do NOT use self_bot=True here because py-cord doesn't support it fully.
# The patch above handles the login instead.
bot = commands.Bot(command_prefix='+', intents=intents, help_command=None)

# --- HELPER FUNCTIONS ---
async def finished_callback(sink, dest_channel, *args):
    await dest_channel.send("✅ **Recording finished.** Processing filenames...")
    
    files = []
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.datetime.now(ist)
    time_str = now.strftime("%d-%m-%Y_%I-%M-%p")

    for user_id, audio in sink.audio_data.items():
        # Try to find the user name
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
    print(f"Logged in as {bot.user} (User Mode via Robust Patch)")
    print(f"Connected to {len(bot.guilds)} servers.")

@bot.command()
async def help(ctx):
    embed = discord.Embed(title="🎙️ User Recorder (Final)", color=discord.Color.green())
    embed.description = "Recording ENABLED on User Account!"
    
    embed.add_field(name="+join", value="Finds you and joins.", inline=False)
    embed.add_field(name="+joinid <id>", value="Join specific ID.", inline=False)
    embed.add_field(name="+record", value="Start recording audio.", inline=False)
    embed.add_field(name="+stop", value="Stop and Upload.", inline=False)
    embed.add_field(name="+name <text>", value="Change display name.", inline=False)
    
    await ctx.send(embed=embed)

@bot.command()
async def name(ctx, *, new_name: str):
    """Changes the account name"""
    try:
        # User accounts use 'edit' slightly differently, let's try standard
        await bot.user.edit(username=new_name)
        await ctx.send(f"✅ Username changed to: **{new_name}**")
    except Exception as e:
        await ctx.send(f"❌ Failed. (Discord limits name changes to 2 per hour).\nError: {e}")

@bot.command()
async def join(ctx):
    """Smart Join"""
    await ctx.send("🔍 Scanning servers...")
    
    found = False
    for guild in bot.guilds:
        # Check if the user who sent the command is in this guild
        member = guild.get_member(ctx.author.id)
        
        if member and member.voice:
            try:
                await member.voice.channel.connect() 
                await ctx.send(f"👍 Joined **{member.voice.channel.name}** in **{guild.name}**!")
                found = True
                break
            except Exception as e:
                # If py-cord fails to connect as user, print error
                await ctx.send(f"❌ Connection Error: {e}")
                return

    if not found:
        await ctx.send("❌ I couldn't find you in any Voice Channel.")

@bot.command()
async def joinid(ctx, channel_id: str):
    """Join by ID"""
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

    # py-cord Sinks work here because we are using py-cord library!
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
        # Run normally (The patch at the top handles the User Token)
        bot.run(TOKEN)
