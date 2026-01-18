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

bot = commands.Bot(command_prefix='+', intents=intents, help_command=None)

# --- HELPER FUNCTIONS ---
async def finished_callback(sink, dest_channel, *args):
    await dest_channel.send("✅ **Recording finished.** Processing filenames...")
    
    files = []
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.datetime.now(ist)
    time_str = now.strftime("%d-%m-%Y_%I-%M-%p")

    for user_id, audio in sink.audio_data.items():
        filename = f"Rec_{user_id}_{time_str}.mp3"
        audio.file.seek(0)
        files.append(discord.File(audio.file, filename))

    if files:
        await dest_channel.send(f"Here are the recordings:", files=files)
    else:
        await dest_channel.send("No audio was recorded (Silence or Connection Error).")

# --- COMMANDS ---

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    print(f"I am in {len(bot.guilds)} servers.")

@bot.command()
async def help(ctx):
    await ctx.send("✅ **Bot is Online.** Use `+join` or `+joinid`.")

@bot.command()
async def status(ctx):
    """Debug command to check what the bot can see"""
    await ctx.send(f"📊 **Status:**\nI am connected to: {len(bot.guilds)} servers.\nMy latency is: {round(bot.latency * 1000)}ms")

@bot.command()
async def join(ctx):
    """Smart Join with explicit error reporting"""
    await ctx.send("🔍 Scanning servers...")
    
    found_guild = False
    
    for guild in bot.guilds:
        # Try to find member
        member = guild.get_member(ctx.author.id)
        if not member:
            try:
                member = await guild.fetch_member(ctx.author.id)
            except:
                continue

        if member and member.voice:
            found_guild = True
            vc_channel = member.voice.channel
            
            # Check Permissions before joining
            perms = vc_channel.permissions_for(guild.me)
            if not perms.connect:
                return await ctx.send(f"❌ Found you in **{guild.name}**, but I don't have permission to **Connect** to the voice channel!")
            
            if not perms.speak:
                return await ctx.send(f"⚠️ Found you, but I don't have permission to **Speak** (I need this to join properly).")

            try:
                await vc_channel.connect(timeout=10.0, reconnect=True)
                return await ctx.send(f"👍 Joined **{vc_channel.name}** in **{guild.name}**!")
            except Exception as e:
                return await ctx.send(f"❌ **Connection Error:** {e}")

    if not found_guild:
        await ctx.send("❌ I scanned all servers but couldn't find you in any Voice Channel.")

@bot.command()
async def joinid(ctx, channel_id: str):
    """Join by ID with FULL DEBUGGING"""
    clean_id = channel_id.strip()
    
    # 1. Validation
    if not clean_id.isdigit():
        return await ctx.send("❌ ID must be a number.")
    
    c_id = int(clean_id)
    await ctx.send(f"🔄 Searching for Channel ID: `{c_id}`...")

    # 2. Search Cache
    channel = bot.get_channel(c_id)
    
    # 3. Search API (Deep Search) if cache missed
    if channel is None:
        try:
            channel = await bot.fetch_channel(c_id)
        except discord.NotFound:
            return await ctx.send("❌ **Error 404:** Discord says this Channel ID does not exist.")
        except discord.Forbidden:
            return await ctx.send("❌ **Error 403:** I am not allowed to see this channel.")
        except Exception as e:
            return await ctx.send(f"❌ **Fetch Error:** {e}")

    # 4. Verify Type
    if not isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
        return await ctx.send(f"❌ Found channel **{channel.name}**, but it is a Text Channel, not Voice.")

    # 5. Check Permissions
    perms = channel.permissions_for(channel.guild.me)
    if not perms.connect:
        return await ctx.send(f"❌ I found **{channel.name}**, but I lack **Connect** permissions.")

    # 6. Attempt Connection
    try:
        if ctx.voice_client:
            await ctx.send("⚠️ I was already connected somewhere else. Moving...")
            await ctx.voice_client.move_to(channel)
        else:
            await channel.connect(timeout=10.0)
        
        await ctx.send(f"👍 **Success!** Joined **{channel.name}**.")

    except Exception as e:
        # THIS IS THE IMPORTANT PART: It will print the real error
        await ctx.send(f"❌ **CRITICAL ERROR:** {e}")

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
    await ctx.send("🔴 **Recording!**")

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
    bot.run(TOKEN)
