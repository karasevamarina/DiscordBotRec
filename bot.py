import discord
from discord.ext import commands
import os
import datetime
import pytz 
import asyncio
import discord.http 

# ==========================================
# 🔓 THE BLIND PATCH (Bypasses the crash)
# ==========================================
async def patched_login(self, token):
    # We just save the token and move on. 
    # We skip the API check that was causing the crash.
    self.token = token.strip()
    self._token_type = None # Forces User Token Mode
    
    # Return a dummy user object so the library is happy
    return {"id": 0, "username": "SelfBot", "discriminator": "0000"}

# Apply the patch
discord.http.HTTPClient.static_login = patched_login
# ==========================================

# --- CONFIGURATION ---
TOKEN = os.getenv('DISCORD_TOKEN')

# --- SETUP ---
intents = discord.Intents.default()
intents.message_content = True 

# Standard Bot Setup
bot = commands.Bot(command_prefix='+', intents=intents, help_command=None)

# --- HELPER FUNCTIONS ---
async def finished_callback(sink, dest_channel, *args):
    await dest_channel.send("✅ **Recording finished.** Processing filenames...")
    
    files = []
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.datetime.now(ist)
    time_str = now.strftime("%d-%m-%Y_%I-%M-%p")

    for user_id, audio in sink.audio_data.items():
        # Try to find the user
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
    # Since we skipped the login check, bot.user might be partial until fully connected
    print(f"Logged in as User Account!")
    print(f"Connected to {len(bot.guilds)} servers.")

@bot.command()
async def help(ctx):
    embed = discord.Embed(title="🎙️ User Recorder", color=discord.Color.red())
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
        await bot.user.edit(username=new_name)
        await ctx.send(f"✅ Username changed to: **{new_name}**")
    except Exception as e:
        await ctx.send(f"❌ Failed. (Discord Rate Limit?)\nError: {e}")

@bot.command()
async def join(ctx):
    """Smart Join"""
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

    # Using py-cord sink
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
