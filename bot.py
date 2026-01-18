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
intents.members = True 
intents.guilds = True
intents.voice_states = True

# self_bot=True enables User Token mode
bot = commands.Bot(command_prefix='+', intents=intents, help_command=None, self_bot=True)

# --- HELPER FUNCTIONS ---
async def finished_callback(sink, dest_channel, *args):
    await dest_channel.send("✅ **Recording finished.** Processing filenames...")
    
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.datetime.now(ist)
    time_str = now.strftime("%d-%m-%Y_%I-%M-%p") 

    files = []
    for user_id, audio in sink.audio_data.items():
        user = bot.get_user(user_id)
        if not user:
            try:
                user = await bot.fetch_user(user_id)
            except:
                user = None

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
        await dest_channel.send("No audio was recorded (Silence or Connection Error).")

# --- COMMANDS ---

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (User Account)")
    print(f"I am in {len(bot.guilds)} servers.")

@bot.command()
async def help(ctx):
    """Shows the full list of commands"""
    embed = discord.Embed(title="🎙️ User Recorder Help", color=discord.Color.blue())
    embed.description = "Control this User Account Recorder:"
    
    embed.add_field(name="+join", value="Scans shared servers to find where you are.", inline=False)
    embed.add_field(name="+joinid <id>", value="Join a specific Channel ID.", inline=False)
    embed.add_field(name="+record", value="Start recording audio.", inline=False)
    embed.add_field(name="+stop", value="Stop recording and upload.", inline=False)
    embed.add_field(name="+name <text>", value="Change the account's display name.", inline=False)
    
    embed.set_footer(text="Running in Self-Bot Mode")
    await ctx.send(embed=embed)

@bot.command()
async def name(ctx, *, new_name: str):
    """Changes the account name"""
    try:
        # Tries to change the Global Display Name (Modern Discord name)
        await bot.user.edit(global_name=new_name)
        await ctx.send(f"✅ Display Name changed to: **{new_name}**")
    except:
        try:
            # Fallback: Tries to change the Username (Classic Discord name)
            # Note: This has a strict rate limit (usually 2 times per hour)
            await bot.user.edit(username=new_name)
            await ctx.send(f"✅ Username changed to: **{new_name}**")
        except Exception as e:
            await ctx.send(f"❌ Failed to change name. Discord rate limit or password requirement.\nError: {e}")

@bot.command()
async def status(ctx):
    await ctx.send(f"📊 **Status:** Connected to {len(bot.guilds)} servers.")

@bot.command()
async def join(ctx):
    """Smart Join scanning shared servers"""
    await ctx.send("🔍 Scanning servers...")
    
    found_guild = False
    
    for guild in bot.guilds:
        member = guild.get_member(ctx.author.id)
        if not member:
            try:
                member = await guild.fetch_member(ctx.author.id)
            except:
                continue

        if member and member.voice:
            found_guild = True
            vc_channel = member.voice.channel
            
            perms = vc_channel.permissions_for(guild.me)
            if not perms.connect:
                return await ctx.send(f"❌ Found you in **{guild.name}**, but I don't have permission to **Connect**!")
            
            try:
                await vc_channel.connect(timeout=10.0, reconnect=True)
                return await ctx.send(f"👍 Joined **{vc_channel.name}** in **{guild.name}**!")
            except Exception as e:
                return await ctx.send(f"❌ **Connection Error:** {e}")

    if not found_guild:
        await ctx.send("❌ I scanned all servers but couldn't find you in any Voice Channel.")

@bot.command()
async def joinid(ctx, channel_id: str):
    """Join by ID"""
    clean_id = channel_id.strip()
    
    if not clean_id.isdigit():
        return await ctx.send("❌ ID must be a number.")
    
    c_id = int(clean_id)
    await ctx.send(f"🔄 Searching for Channel ID: `{c_id}`...")

    channel = bot.get_channel(c_id)
    if channel is None:
        try:
            channel = await bot.fetch_channel(c_id)
        except:
            return await ctx.send("❌ **Error:** Channel ID not found.")

    if not isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
        return await ctx.send(f"❌ **{channel.name}** is not a Voice Channel.")

    try:
        if ctx.voice_client:
            await ctx.voice_client.move_to(channel)
        else:
            await channel.connect(timeout=10.0)
        
        await ctx.send(f"👍 **Success!** Joined **{channel.name}**.")

    except Exception as e:
        await ctx.send(f"❌ **Connection Error:** {e}")

@bot.command()
async def record(ctx):
    if len(bot.voice_clients) == 0:
        return await ctx.send("❌ I am not in a VC.")
    
    vc = bot.voice_clients[0]
    if vc.recording:
        return await ctx.send("Already recording.")

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
        # bot=False ensures User Token login works
        bot.run(TOKEN, bot=False)
