import discord
from discord.ext import commands
import os
import datetime
import pytz 

# --- CONFIGURATION ---
TOKEN = os.getenv('DISCORD_TOKEN')

# ⚠️ PASTE YOUR USER ID HERE
OWNER_ID = 123456789012345678 

# --- SETUP ---
intents = discord.Intents.default()
intents.message_content = True 
# We need 'members' intent to find you in servers
intents.members = True 

bot = commands.Bot(command_prefix='+', intents=intents, help_command=None)

# --- CHECKS ---
def is_owner_check(ctx):
    # REMOVED the check that blocked DMs
    return ctx.author.id == OWNER_ID

# --- HELPER FUNCTIONS ---
async def finished_callback(sink, dest_channel, *args):
    # dest_channel is where we send the file (Your DM)
    await dest_channel.send("✅ **Recording finished.** Processing filenames...")
    
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.datetime.now(ist)
    time_str = now.strftime("%d-%m-%Y_%I-%M-%p")
    
    files = []
    
    for user_id, audio in sink.audio_data.items():
        filename = f"Recording_{user_id}_{time_str}.mp3"
        audio.file.seek(0)
        files.append(discord.File(audio.file, filename))

    if files:
        await dest_channel.send(f"Here are the recordings:", files=files)
    else:
        await dest_channel.send("No audio was recorded (Silence).")

# --- COMMANDS ---

@bot.command()
@commands.check(is_owner_check)
async def help(ctx):
    embed = discord.Embed(title="🎙️ DM Recorder Bot", color=discord.Color.green())
    embed.description = "You can control me from here!"
    embed.add_field(name="+join", value="I will find you in any server and join.", inline=False)
    embed.add_field(name="+joinid <id>", value="Force join a specific channel ID.", inline=False)
    embed.add_field(name="+record", value="Start recording.", inline=False)
    embed.add_field(name="+stop", value="Stop & Upload to DM.", inline=False)
    await ctx.send(embed=embed)

@bot.command()
@commands.check(is_owner_check)
async def join(ctx):
    """Smart Join: Finds you in any server"""
    
    # 1. If command is used INSIDE a server
    if ctx.guild and ctx.author.voice:
        await ctx.author.voice.channel.connect()
        return await ctx.send(f"👍 Joined **{ctx.author.voice.channel.name}**!")

    # 2. If command is used in DM -> Search for user
    await ctx.send("🔍 Searching servers to find you...")
    
    for guild in bot.guilds:
        # Try to find the member in this guild
        member = guild.get_member(ctx.author.id)
        if member and member.voice:
            await member.voice.channel.connect()
            return await ctx.send(f"👍 Found you in **{guild.name}**! Joined **{member.voice.channel.name}**.")

    await ctx.send("❌ I couldn't find you in any Voice Channel. Are you sure you are connected?")

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
    # Find the active voice client (Bot can only be in one place usually)
    vc = None
    
    # If in server, easy find
    if ctx.guild:
        vc = ctx.voice_client
    # If in DM, find the first active connection
    else:
        if len(bot.voice_clients) > 0:
            vc = bot.voice_clients[0]

    if not vc:
        return await ctx.send("❌ I am not connected to any VC.")
    
    if vc.recording:
        return await ctx.send("Already recording!")

    # Start recording and tell it to send files to ctx.channel (Your DM)
    vc.start_recording(
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
    # Find the active voice client
    vc = None
    if ctx.guild:
        vc = ctx.voice_client
    else:
        if len(bot.voice_clients) > 0:
            vc = bot.voice_clients[0]

    if vc:
        if vc.recording:
            vc.stop_recording()
            await ctx.send("🛑 **Stopping...** (Uploading to DM...)")
        
        # Wait a moment before disconnecting to ensure callback runs
        import asyncio
        await asyncio.sleep(1)
        await vc.disconnect()
    else:
        await ctx.send("I am not connected.")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        pass # Ignore strangers
    else:
        print(f"Error: {error}")

if __name__ == "__main__":
    if not TOKEN:
        print("Error: DISCORD_TOKEN not found.")
    else:
        bot.run(TOKEN)
