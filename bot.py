import discord
from discord.ext import commands
import os
import datetime
import pytz 
import asyncio

# --- CONFIGURATION ---
TOKEN = os.getenv('DISCORD_TOKEN')

# --- SETUP ---
# self_bot=True is REQUIRED for User Tokens
bot = commands.Bot(command_prefix='+', self_bot=True, help_command=None)

# --- COMMANDS ---

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (User Account)")
    print(f"I am in {len(bot.guilds)} servers.")

@bot.command()
async def help(ctx):
    embed = discord.Embed(title="🎙️ User Account Bot", color=discord.Color.blue())
    embed.description = "User Token Mode (Recording Disabled)"
    
    embed.add_field(name="+join", value="Join your voice channel.", inline=False)
    embed.add_field(name="+joinid <id>", value="Join a specific Channel ID.", inline=False)
    embed.add_field(name="+stop", value="Leave the channel.", inline=False)
    embed.add_field(name="+name <text>", value="Change display name.", inline=False)
    embed.add_field(name="+record", value="❌ Not available on User Accounts.", inline=False)
    
    await ctx.send(embed=embed)

@bot.command()
async def name(ctx, *, new_name: str):
    """Changes the account name"""
    try:
        await bot.user.edit(global_name=new_name)
        await ctx.send(f"✅ Display Name changed to: **{new_name}**")
    except:
        await ctx.send("❌ Failed. You might be changing names too fast (Rate Limit).")

@bot.command()
async def status(ctx):
    await ctx.send(f"📊 **Status:** Connected to {len(bot.guilds)} servers.")

@bot.command()
async def join(ctx):
    """Smart Join"""
    await ctx.send("🔍 Scanning servers...")
    
    found = False
    for guild in bot.guilds:
        member = guild.get_member(ctx.author.id)
        if member and member.voice:
            try:
                # self_deaf=False makes it look like you are listening
                await member.voice.channel.connect(self_deaf=False) 
                await ctx.send(f"👍 Joined **{member.voice.channel.name}** in **{guild.name}**!")
                found = True
                break
            except Exception as e:
                await ctx.send(f"❌ Error joining: {e}")
                return

    if not found:
        await ctx.send("❌ I couldn't find you in any Voice Channel.")

@bot.command()
async def joinid(ctx, channel_id: str):
    """Join by ID"""
    try:
        channel = bot.get_channel(int(channel_id))
        if isinstance(channel, discord.VoiceChannel):
            await channel.connect(self_deaf=False)
            await ctx.send(f"👍 Joined **{channel.name}**")
        else:
            await ctx.send("❌ Not a voice channel.")
    except Exception as e:
        await ctx.send(f"❌ Error: {e}")

@bot.command()
async def record(ctx):
    # This logic was removed because discord.py-self (User Lib) does not support Sinks
    await ctx.send("❌ **Recording is unavailable.**\nYou are using a User Token. To record audio, you must switch back to a Bot Token (and lose the +name command).")

@bot.command()
async def stop(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("🛑 Disconnected.")
    else:
        await ctx.send("I am not connected.")

if __name__ == "__main__":
    if not TOKEN:
        print("Error: DISCORD_TOKEN not found.")
    else:
        # Standard run() works for User Tokens in discord.py-self
        bot.run(TOKEN)
