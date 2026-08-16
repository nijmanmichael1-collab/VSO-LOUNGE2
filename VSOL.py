import os
import random
import asyncio
import datetime
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
from aiohttp import web

import database

# Initialize Database
database.init_db()

# Target Config Identifiers
ALLOWED_ROLE_ID = 1474378842520031397
LOG_CHANNEL_ID = 1513182544550690910
PORT = int(os.environ.get("PORT", 8080))

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# --- Web Server for Render & Ping Keep-Alive ---
async def handle_ping(request):
    return web.Response(text="Bot is running!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()

# --- Helper Functions ---
async def safe_delay():
    """Applies a small random delay to avoid rapid rate-limit API triggers."""
    await asyncio.sleep(random.uniform(1.2, 3.5))

async def fetch_roblox_info(username: str):
    """Fetches Roblox User ID and Headshot Avatar URL."""
    async with bot.http_session.post(
        "https://users.roblox.com/v1/usernames/users",
        json={"usernames": [username], "excludeBannedUsers": True}
    ) as resp:
        if resp.status != 200:
            return None, None
        data = await resp.json()
        if not data.get("data"):
            return None, None
        roblox_id = data["data"][0]["id"]

    avatar_url = f"https://www.roblox.com/headshot-thumbnail/image?userId={roblox_id}&width=420&height=420&format=png"
    return roblox_id, avatar_url

# --- Interactive Roblox Verification UI ---
class RobloxConfirmView(discord.ui.View):
    def __init__(self, roblox_username: str, roblox_id: str):
        super().__init__(timeout=120)
        self.roblox_username = roblox_username
        self.roblox_id = roblox_id

    @discord.ui.button(label="Yes", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Acknowledge immediately to avoid 404 Unknown interaction errors
        await interaction.response.defer()
        
        await safe_delay()
        database.link_roblox_user(interaction.user.id, self.roblox_username, self.roblox_id)
        
        for child in self.children:
            child.disabled = True
            
        await interaction.edit_original_response(content="Roblox account linked successfully.", embed=None, view=self)

    @discord.ui.button(label="No", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        
        for child in self.children:
            child.disabled = True
            
        await interaction.edit_original_response(content="Verification cancelled.", embed=None, view=self)

class RobloxInputModal(discord.ui.Modal, title="Link Roblox Account"):
    rblx_input = discord.ui.TextInput(
        label="Roblox Username",
        placeholder="Enter your exact Roblox username...",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await safe_delay()

        username = self.rblx_input.value.strip()
        r_id, avatar_url = await fetch_roblox_info(username)

        if not r_id:
            await interaction.followup.send("Roblox user not found. Please try again.", ephemeral=True)
            return

        embed = discord.Embed(title="Is this you?", color=discord.Color.blue())
        embed.add_field(name="Roblox Username", value=username, inline=False)
        embed.add_field(name="Profile Link", value=f"https://www.roblox.com/users/{r_id}/profile", inline=False)
        embed.set_thumbnail(url=avatar_url)

        view = RobloxConfirmView(username, r_id)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

class VerifyPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="LINK", style=discord.ButtonStyle.green, custom_id="vso_link_btn")
    async def link_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RobloxInputModal())

# --- Bot Events ---
@bot.event
async def on_ready():
    import aiohttp
    bot.http_session = aiohttp.ClientSession()
    bot.add_view(VerifyPanelView())
    await start_web_server()
    await bot.tree.sync()

# --- Command 1: /verifypanel ---
@bot.tree.command(name="verifypanel", description="Send verification panel")
@app_commands.checks.has_permissions(administrator=True)
async def verifypanel(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    await safe_delay()

    embed = discord.Embed(
        title="Verification",
        description="Link roblox",
        color=discord.Color.blue()
    )
    view = VerifyPanelView()
    await interaction.channel.send(embed=embed, view=view)
    await interaction.followup.send("Panel created.", ephemeral=True)

# --- Command 2: /recommend ---
@bot.tree.command(name="recommend", description="Recommend a member")
@app_commands.describe(user="The member to recommend", reason="Reason for recommendation")
async def recommend(interaction: discord.Interaction, user: discord.Member, reason: str):
    await interaction.response.defer(ephemeral=True)
    await safe_delay()

    role = interaction.guild.get_role(ALLOWED_ROLE_ID)
    if role not in interaction.user.roles:
        await interaction.followup.send("You cannot use this command.", ephemeral=True)
        return

    # Check 2-minute spam cooldown
    remaining_cooldown = database.get_cooldown_remaining(interaction.user.id)
    if remaining_cooldown > 0:
        await interaction.followup.send(f"Please wait {int(remaining_cooldown)} seconds before making another recommendation.", ephemeral=True)
        return

    # Check 5 per week limit
    if not database.can_recommend(interaction.user.id):
        await interaction.followup.send("You reached your limit of 5 recommendations this week.", ephemeral=True)
        return

    rec_rblx = database.get_roblox_data(interaction.user.id)
    target_rblx = database.get_roblox_data(user.id)

    if not rec_rblx or not target_rblx:
        await interaction.followup.send("Both users must link Roblox before using this command.", ephemeral=True)
        return

    target_rblx_user, target_rblx_id = target_rblx
    avatar_url = f"https://www.roblox.com/headshot-thumbnail/image?userId={target_rblx_id}&width=420&height=420&format=png"
    now_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    embed = discord.Embed(
        title=f"📩 Recommendation Request by {interaction.user.name} (@{interaction.user.name})",
        color=discord.Color.blue()
    )
    embed.add_field(name="Roblox user", value=target_rblx_user, inline=False)
    embed.add_field(name="Roblox Profile link", value=f"https://www.roblox.com/users/{target_rblx_id}/profile", inline=False)
    embed.add_field(name="recommender", value=interaction.user.mention, inline=True)
    embed.add_field(name="recommended", value=user.mention, inline=True)
    embed.add_field(name="reason", value=reason, inline=False)
    embed.set_thumbnail(url=avatar_url)
    embed.set_footer(text=f"{now_str} | Virtual Soccer Organization")

    target_channel = bot.get_channel(LOG_CHANNEL_ID)
    sent_msg = await target_channel.send(embed=embed)

    database.save_recommendation(
        recommended_id=user.id,
        recommender_id=interaction.user.id,
        channel_id=target_channel.id,
        message_id=sent_msg.id,
        rblx_user=target_rblx_user,
        rblx_id=target_rblx_id,
        reason=reason
    )
    database.add_recommend_count(interaction.user.id)
    database.update_cooldown(interaction.user.id)

    try:
        await user.send(embed=embed)
    except discord.HTTPException:
        pass

    await interaction.followup.send("Recommendation sent.", ephemeral=True)

# --- Command 3: /accept ---
@bot.tree.command(name="accept", description="Accept a recommended user")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(user="The member to accept")
async def accept(interaction: discord.Interaction, user: discord.Member):
    await interaction.response.defer(ephemeral=True)
    await safe_delay()

    rec_data = database.get_recommendation(user.id)
    if rec_data:
        recommender_id, channel_id, message_id, rblx_user, rblx_id, reason = rec_data
        channel = bot.get_channel(channel_id)
        if channel:
            try:
                msg = await channel.fetch_message(message_id)
                now_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                avatar_url = f"https://www.roblox.com/headshot-thumbnail/image?userId={rblx_id}&width=420&height=420&format=png"

                green_embed = discord.Embed(
                    title=f"Accepted by {interaction.user.name}",
                    color=discord.Color.green()
                )
                green_embed.add_field(name="Roblox user", value=rblx_user, inline=False)
                green_embed.add_field(name="Roblox Profile link", value=f"https://www.roblox.com/users/{rblx_id}/profile", inline=False)
                green_embed.add_field(name="recommender", value=f"<@{recommender_id}>", inline=True)
                green_embed.add_field(name="recommended", value=user.mention, inline=True)
                green_embed.add_field(name="reason", value=reason, inline=False)
                green_embed.set_thumbnail(url=avatar_url)
                green_embed.set_footer(text=f"{now_str} | Virtual Soccer Organization")

                await msg.edit(embed=green_embed)
            except discord.HTTPException:
                pass

        database.delete_recommendation(user.id)

    try:
        await user.send("🎉 You have been accepted into VSO!")
    except discord.HTTPException:
        pass

    await interaction.followup.send("User accepted.", ephemeral=True)

# --- Command 4: /decline ---
@bot.tree.command(name="decline", description="Decline a user")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(user="The member to decline")
async def decline(interaction: discord.Interaction, user: discord.Member):
    await interaction.response.defer(ephemeral=True)
    await safe_delay()

    try:
        await user.send("❌ You have been declined into VSO.")
    except discord.HTTPException:
        pass

    database.delete_recommendation(user.id)
    await interaction.followup.send("User declined.", ephemeral=True)

# --- Command 5: /say ---
@bot.tree.command(name="say", description="Send a message as the bot")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    channel="Target channel",
    message="Normal message content",
    embed_message="Embed body content",
    embed_title="Embed title",
    embed_footer="Embed footer text"
)
async def say(
    interaction: discord.Interaction,
    channel: Optional[discord.TextChannel] = None,
    message: Optional[str] = None,
    embed_message: Optional[str] = None,
    embed_title: Optional[str] = None,
    embed_footer: Optional[str] = None
):
    await interaction.response.defer(ephemeral=True)
    await safe_delay()

    target_channel = channel or interaction.channel
    embed = None

    if embed_message or embed_title or embed_footer:
        embed = discord.Embed(
            title=embed_title if embed_title else "",
            description=embed_message if embed_message else "",
            color=discord.Color.blue()
        )
        if embed_footer:
            embed.set_footer(text=embed_footer)

    if not message and not embed:
        await interaction.followup.send("Please provide a message or embed content.", ephemeral=True)
        return

    await target_channel.send(content=message, embed=embed)
    await interaction.followup.send("Message sent.", ephemeral=True)

# --- Command 6: /dm ---
@bot.tree.command(name="dm", description="Send a direct message to a user")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(user="Target user", message="Direct message text")
async def dm(interaction: discord.Interaction, user: discord.Member, message: str):
    await interaction.response.defer(ephemeral=True)
    await safe_delay()

    try:
        await user.send(message)
        await interaction.followup.send("Message sent.", ephemeral=True)
    except discord.HTTPException:
        await interaction.followup.send("Failed to send direct message.", ephemeral=True)

# --- Error Handlers ---
@say.error
@accept.error
@decline.error
@dm.error
@verifypanel.error
async def admin_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        if not interaction.response.is_done():
            await interaction.response.send_message("You cannot use this command.", ephemeral=True)
        else:
            await interaction.followup.send("You cannot use this command.", ephemeral=True)

# Run the Bot using the BOT_TOKEN environment variable
bot.run(os.environ.get("BOT_TOKEN"))
