import discord
from discord.ext import commands
import os
import datetime
import pytz 
import asyncio

# --- CONFIGURATION ---
TOKEN = os.getenv('DISCORD_TOKEN')

# --- SETUP ---
intents = discord.Intents.default()
intents.message_content = True 
intents.members = True # REQUIRED to find you in servers

bot = commands.Bot(command_prefix='+', intents=intents, help_command=None)

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

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    print("Bot is ready and unlocked!")

@bot.command()
async def help(ctx):
    embed = discord.Embed(title="🎙️ Unlocked Recorder Bot", color=discord.Color.green())
    embed.description = "Control me from DMs or Servers!"
    embed.add_field(name="+join", value="I'll search for you in servers and join.", inline=False)
    embed.add_field(name="+joinid <id>", value="Force join a Channel ID.", inline=False)
    embed.add_field(name="+record", value="Start recording.", inline=False)
    embed.add_field(name="+stop", value="Stop & Upload here.", inline=False)
    await ctx.send(embed=embed)

@bot.command()
async def join(ctx):
    """Smart Join: Finds you in any server"""
    await ctx.send("🔍 Scanning servers to find you...")
    
    # Loop through every server the bot is in
    found = False
    for guild in bot.guilds:
        # Check if the user who sent the command is in this guild
        member = guild.get_member(ctx.author.id)
        
        # If found AND you are in a voice channel
        if member and member.voice:
            await member.voice.channel.connect()
            await ctx.send(f"👍 Found you in **{guild.name}**! Joined **{member.voice.channel.name}**.")
            found = True
            break

    if not found:
        await ctx.send("❌ I couldn't find you in any Voice Channel. Make sure you are connected first!")

@bot.command()
async def joinid(ctx, channel_id: str):
    """Force join a specific channel ID"""
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
async def record(ctx):
    # Find the active voice connection
    if len(bot.voice_clients) == 0:
        return await ctx.send("❌ I am not connected to any VC.")
    
    vc = bot.voice_clients[0]
    
    if vc.recording:
        return await ctx.send("Already recording!")

    # Start recording and tell it to send files to wherever you typed the command (DM)
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
        return await ctx.send("I am not connected.")

    vc = bot.voice_clients[0]

    if vc.recording:
        vc.stop_recording()
        await ctx.send("🛑 **Stopping...** (Uploading...)")
        
    # Wait 1 second before leaving so the file upload doesn't get cut off
    await asyncio.sleep(1)
    await vc.disconnect()

@bot.event
async def on_command_error(ctx, error):
    print(f"Error: {error}")

if __name__ == "__main__":
    if not TOKEN:
        print("Error: DISCORD_TOKEN not found.")
    else:
        bot.run(TOKEN)
