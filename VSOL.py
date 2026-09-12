import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
import discord
from discord import app_commands
from discord.ext import commands
import aiohttp
import database

# Initialize Database
database.init_db()

# --- Built-in HTTP Server to satisfy Render's Port Scan ---
class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot is online and running!")

    def log_message(self, format, *args):
        # Silence console HTTP log spam
        return

def run_port_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), SimpleHTTPRequestHandler)
    server.serve_forever()

# Start port server in background thread
threading.Thread(target=run_port_server, daemon=True).start()

# --- Discord Bot Setup ---
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

ALLOWED_ROLE_ID = 1474378842520031397
RECOMMEND_CHANNEL_ID = 1513182544550690910

# Helper Roblox API Functions
async def fetch_roblox_user(username: str):
    url = "https://users.roblox.com/v1/usernames/users"
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json={"usernames": [username], "excludeBannedUsers": True}) as resp:
            if resp.status == 200:
                data = await resp.json()
                if data.get("data"):
                    user_data = data["data"][0]
                    return user_data["id"], user_data["name"]
    return None, None

async def fetch_roblox_avatar(roblox_id: int):
    url = f"https://thumbnails.roblox.com/v1/users/avatar-headshot?userIds={roblox_id}&size=150x150&format=Png&isCircular=false"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                data = await resp.json()
                if data.get("data"):
                    return data["data"][0].get("imageUrl")
    return None

# UI Components
class ConfirmView(discord.ui.View):
    def __init__(self, roblox_username: str, roblox_id: int):
        super().__init__(timeout=60)
        self.roblox_username = roblox_username
        self.roblox_id = roblox_id

    @discord.ui.button(label="Yes", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        database.save_user(interaction.user.id, self.roblox_username, self.roblox_id)
        await interaction.response.send_message(
            f"You are now linked to Roblox account: **{self.roblox_username}**!", 
            ephemeral=True
        )
        self.stop()

    @discord.ui.button(label="No", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Verification cancelled. Please try again.", ephemeral=True)
        self.stop()

class VerifyModal(discord.ui.Modal, title="Link Roblox Account"):
    username_input = discord.ui.TextInput(
        label="Roblox Username",
        placeholder="Enter your exact Roblox username here...",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        roblox_username = self.username_input.value
        roblox_id, real_name = await fetch_roblox_user(roblox_username)

        if not roblox_id:
            await interaction.followup.send("Roblox user not found. Check spelling and try again.")
            return

        avatar_url = await fetch_roblox_avatar(roblox_id)

        embed = discord.Embed(
            title="Is this you?",
            description=f"**Roblox Username:** {real_name}\n**ID:** {roblox_id}",
            color=discord.Color.blue()
        )
        if avatar_url:
            embed.set_thumbnail(url=avatar_url)

        view = ConfirmView(real_name, roblox_id)
        await interaction.followup.send(embed=embed, view=view)

class VerifyPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Link Roblox", style=discord.ButtonStyle.green, custom_id="link_roblox_btn")
    async def link_roblox(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(VerifyModal())

# Commands
@bot.event
async def on_ready():
    bot.add_view(VerifyPanelView())
    await bot.tree.sync()
    print(f"Logged in as {bot.user}")

@bot.tree.command(name="verify", description="...")
@app_commands.checks.has_permissions(administrator=True)
async def verify(interaction: discord.Interaction):
    embed = discord.Embed(
        title="VSO VERIFICATION",
        description="Link Roblox account to get a reccomendation to VSO",
        color=discord.Color.blue()
    )
    embed.set_footer(text="") 

    view = VerifyPanelView()
    await interaction.channel.send(embed=embed, view=view)
    await interaction.response.send_message("Verification panel created!", ephemeral=True)

@verify.error
async def verify_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("You need admin rights to use this command.", ephemeral=True)

@bot.tree.command(name="recommend", description="...")
async def recommend(interaction: discord.Interaction, recommended: discord.Member, reason: str):
    await interaction.response.defer(ephemeral=True)

    user_role_ids = [role.id for role in interaction.user.roles]
    if ALLOWED_ROLE_ID not in user_role_ids:
        await interaction.followup.send("You do not have permission to use this command.")
        return

    target_data = database.get_user(recommended.id)
    if not target_data:
        await interaction.followup.send("This user has not linked their Roblox account yet!")
        return

    roblox_username, roblox_id = target_data
    profile_link = f"https://www.roblox.com/users/{roblox_id}/profile"

    embed = discord.Embed(
        title=f"📩 Recommendation Request by {interaction.user.name} (@{interaction.user.name})",
        color=discord.Color.blue()
    )
    embed.add_field(name="Roblox user", value=roblox_username, inline=False)
    embed.add_field(name="Roblox Profile link", value=profile_link, inline=False)
    embed.add_field(name="recommender", value=interaction.user.mention, inline=True)
    embed.add_field(name="recommended", value=recommended.mention, inline=True)
    embed.add_field(name="reason", value=reason, inline=False)

    current_time = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    embed.set_footer(text=f"{current_time} | Virtual Soccer Organization")

    channel = bot.get_channel(RECOMMEND_CHANNEL_ID)
    if channel:
        await channel.send(embed=embed)
    else:
        await interaction.followup.send("Recommendation channel not found.")
        return

    try:
        await recommended.send(embed=embed)
    except discord.Forbidden:
        pass

    await interaction.followup.send("Recommendation submitted successfully!")

TOKEN = os.environ.get("DISCORD_TOKEN", "YOUR_BOT_TOKEN_HERE")
bot.run(TOKEN)
