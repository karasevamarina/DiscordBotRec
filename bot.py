import discord
from discord.ext import commands
import os
import datetime
import pytz 

# --- CONFIGURATION ---
TOKEN = os.getenv('DISCORD_TOKEN')

# ⚠️ REPLACE WITH YOUR USER ID (NUMBERS ONLY)
OWNER_ID = ENTER_YOUR_ID_HERE

# --- SETUP ---
intents = discord.Intents.default()
intents.message_content = True 

bot = commands.Bot(command_prefix='+', intents=intents, help_command=None)

# --- CHECKS ---
def is_owner_check(ctx):
    # Only allow command if in a Server (not DM) and user is Owner
    if ctx.guild is None:
        return False
    return ctx.author.id == OWNER_ID

# --- HELPER FUNCTION ---
async def finished_callback(sink, channel: discord.TextChannel, *args):
    await channel.send("✅ **Recording finished.** Processing filenames...")
    
    # Set Timezone to IST (Indian Standard Time)
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.datetime.now(ist)
    time_str = now.strftime("%d-%m-%Y_%I-%M-%p") # e.g. 18-01-2026_08-30-PM
    
    files = []
    
    for user_id, audio in sink.audio_data.items():
        # Get User Name
        user = channel.guild.get_member(user_id)
        if user:
            username = user.display_name
        else:
            username = f"User_{user_id}"
            
        # Clean username (remove special chars that break filenames)
        safe_username = "".join(x for x in username if x.isalnum() or x in "._- ")
        
        # Create Filename: Super_18-01-2026_08-30-PM_IST.mp3
        filename = f"{safe_username}__{time_str}_IST.mp3"
        
        audio.file.seek(0)
        files.append(discord.File(audio.file, filename))

    if files:
        await channel.send(f"Here are the recordings:", files=files)
    else:
        await channel.send("No audio was recorded.")

# --- COMMANDS ---

@bot.command()
@commands.check(is_owner_check)
async def help(ctx):
    embed = discord.Embed(title="🎙️ Recorder Bot", color=discord.Color.red())
    embed.add_field(name="+join", value="Join your current VC", inline=False)
    embed.add_field(name="+joinid <id>", value="Join a VC by ID", inline=False)
    embed.add_field(name="+record", value="Start recording", inline=False)
    embed.add_field(name="+stop", value="Stop & Upload", inline=False)
    await ctx.send(embed=embed)

@bot.command()
@commands.check(is_owner_check)
async def join(ctx):
    if ctx.author.voice:
        channel = ctx.author.voice.channel
        await channel.connect()
        await ctx.send(f"👍 Joined **{channel.name}**!")
    else:
        await ctx.send("❌ You are not in a VC.")

@bot.command()
@commands.check(is_owner_check)
async def joinid(ctx, channel_id: str):
    try:
        c_id = int(channel_id)
        channel = bot.get_channel(c_id)
        if channel and isinstance(channel, discord.VoiceChannel):
            await channel.connect()
            await ctx.send(f"👍 Joined **{channel.name}**")
        else:
            await ctx.send("❌ Channel not found or not a VC.")
    except:
        await ctx.send("❌ Invalid ID.")

@bot.command()
@commands.check(is_owner_check)
async def record(ctx):
    if not ctx.voice_client:
        return await ctx.send("❌ I am not in a VC.")
    
    if ctx.voice_client.recording:
        return await ctx.send("Already recording!")

    ctx.voice_client.start_recording(
        discord.sinks.MP3Sink(), 
        finished_callback, 
        ctx.channel
    )
    
    ist = pytz.timezone('Asia/Kolkata')
    start_time = datetime.datetime.now(ist).strftime("%I:%M %p")
    await ctx.send(f"🔴 **Recording Started at {start_time} IST!**")

@bot.command()
@commands.check(is_owner_check)
async def stop(ctx):
    if ctx.voice_client:
        if ctx.voice_client.recording:
            ctx.voice_client.stop_recording()
            await ctx.send("🛑 **Stopping...** (Uploading...)")
        await ctx.voice_client.disconnect()
    else:
        await ctx.send("I am not connected.")

@bot.event
async def on_command_error(ctx, error):
    # Silently ignore errors from non-owners
    if isinstance(error, commands.CheckFailure):
        return
    print(error)

if __name__ == "__main__":
    if not TOKEN:
        print("Error: DISCORD_TOKEN not found.")
    else:
        bot.run(TOKEN)
