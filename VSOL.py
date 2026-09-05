import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import os
import database  # Make sure database.py is in the same directory

# Configuration IDs
ALLOWED_ROLE_ID = 1474378842520031397
LOG_CHANNEL_ID = 1513182544550690910

# Initialize Bot with Intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# --- Safe Roblox API Handler ---
async def fetch_roblox_info(username: str):
    """Fetches Roblox User ID and Headshot Avatar URL safely without crashing on Cloudflare blocks."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    }
    url = "https://users.roblox.com/v1/usernames/users"
    
    try:
        async with bot.http_session.post(
            url,
            json={"usernames": [username], "excludeBannedUsers": True},
            headers=headers
        ) as resp:
            # Handle Cloudflare blocks or non-200 responses safely
            if resp.status != 200:
                return None, None
                
            data = await resp.json()
            if not data.get("data") or len(data["data"]) == 0:
                return None, None
                
            roblox_id = data["data"][0]["id"]
            avatar_url = f"https://www.roblox.com/headshot-thumbnail/image?userId={roblox_id}&width=420&height=420&format=png"
            return roblox_id, avatar_url
            
    except Exception:
        return None, None

# --- Verification Modal ---
class VerifyModal(discord.ui.Modal, title="Link Roblox Account"):
    roblox_username = discord.ui.TextInput(
        label="Roblox Username",
        placeholder="Enter your exact Roblox username...",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        username = self.roblox_username.value.strip()
        
        roblox_id, avatar_url = await fetch_roblox_info(username)
        
        if not roblox_id:
            await interaction.followup.send(
                "❌ Could not find that Roblox account or the request was temporarily blocked by Cloudflare. Please check the spelling and try again.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="Confirm Roblox Account",
            description=f"Is this your Roblox account?\n\n**Username:** `{username}`\n**Roblox ID:** `{roblox_id}`",
            color=discord.Color.blue()
        )
        embed.set_thumbnail(url=avatar_url)

        view = ConfirmVerifyView(username=username, roblox_id=roblox_id)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

class ConfirmVerifyView(discord.ui.View):
    def __init__(self, username: str, roblox_id: int):
        super().__init__(timeout=120)
        self.username = username
        self.roblox_id = roblox_id

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        database.link_roblox_user(interaction.user.id, self.username, self.roblox_id)
        
        embed = discord.Embed(
            title="✅ Account Linked!",
            description=f"Successfully linked your Discord account to Roblox user **{self.username}** (`{self.roblox_id}`).",
            color=discord.Color.green()
        )
        await interaction.response.edit_message(embed=embed, view=None)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="❌ Verification cancelled.", embed=None, view=None)

class VerifyPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Verify Account", style=discord.ButtonStyle.primary, custom_id="verify_button_persistent")
    async def verify_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(VerifyModal())

# --- Bot Events ---
@bot.event
async def on_ready():
    database.init_db()
    bot.http_session = aiohttp.ClientSession()
    bot.add_view(VerifyPanelView())
    
    try:
        synced = await bot.tree.sync()
        print(f"Logged in as {bot.user} | Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

@bot.event
async def on_close():
    if hasattr(bot, 'http_session'):
        await bot.http_session.close()

# --- Slash Commands ---
@bot.tree.command(name="verifypanel", description="Deploys the Roblox verification panel (Admin only)")
@app_commands.checks.has_permissions(administrator=True)
async def verifypanel(interaction: discord.Interaction):
    embed = discord.Embed(
        title="VSO Roblox Verification",
        description="Click the button below to link your Roblox account to your Discord profile.",
        color=discord.Color.blue()
    )
    await interaction.channel.send(embed=embed, view=VerifyPanelView())
    await interaction.response.send_message("Verification panel deployed successfully!", ephemeral=True)

@bot.tree.command(name="recommend", description="Recommend a player for VSO")
async def recommend(interaction: discord.Interaction, target: discord.User, reason: str):
    # Role Check
    has_role = any(role.id == ALLOWED_ROLE_ID for role in interaction.user.roles)
    if not has_role:
        await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)
        return

    # Cooldown Check (2 minutes)
    remaining_cd = database.get_cooldown_remaining(interaction.user.id)
    if remaining_cd > 0:
        await interaction.response.send_message(f"⏳ Please wait `{int(remaining_cd)}` seconds before recommending again.", ephemeral=True)
        return

    # Weekly Limit Check (5 per week)
    if not database.can_recommend(interaction.user.id):
        await interaction.response.send_message("❌ You have reached your limit of 5 recommendations for this week.", ephemeral=True)
        return

    # Check Roblox Link Data
    roblox_data = database.get_roblox_data(target.id)
    if not roblox_data:
        await interaction.response.send_message(f"❌ {target.mention} has not verified their Roblox account via `/verifypanel` yet.", ephemeral=True)
        return

    rblx_username, rblx_id = roblox_data
    avatar_url = f"https://www.roblox.com/headshot-thumbnail/image?userId={rblx_id}&width=420&height=420&format=png"

    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if not log_channel:
        await interaction.response.send_message("❌ Log channel not found. Contact an administrator.", ephemeral=True)
        return

    # Post Recommendation Embed
    embed = discord.Embed(title="New Player Recommendation", color=discord.Color.gold())
    embed.add_field(name="Recommended User", value=f"{target.mention} (`{target.id}`)", inline=False)
    embed.add_field(name="Recommender", value=f"{interaction.user.mention}", inline=False)
    embed.add_field(name="Roblox Username", value=f"`{rblx_username}`", inline=True)
    embed.add_field(name="Roblox ID", value=f"`{rblx_id}`", inline=True)
    embed.add_field(name="Reason", value=reason, inline=False)
    embed.set_thumbnail(url=avatar_url)

    msg = await log_channel.send(embed=embed)

    # Save tracking data & update user limits
    database.save_recommendation(target.id, interaction.user.id, log_channel.id, msg.id, rblx_username, rblx_id, reason)
    database.update_cooldown(interaction.user.id)
    database.add_recommend_count(interaction.user.id)

    await interaction.response.send_message(f"✅ Successfully submitted recommendation for {target.mention}!", ephemeral=True)

@bot.tree.command(name="accept", description="Accept a player recommendation")
@app_commands.checks.has_permissions(administrator=True)
async def accept(interaction: discord.Interaction, target: discord.User):
    rec_data = database.get_recommendation(target.id)
    if not rec_data:
        await interaction.response.send_message("❌ No active recommendation found for this user.", ephemeral=True)
        return

    recommender_id, channel_id, message_id, rblx_username, rblx_id, reason = rec_data
    channel = bot.get_channel(channel_id)
    
    if channel:
        try:
            msg = await channel.fetch_message(message_id)
            embed = msg.embeds[0]
            embed.color = discord.Color.green()
            embed.title = "Recommendation Accepted"
            embed.add_field(name="Status", value=f"✅ Accepted by {interaction.user.mention}", inline=False)
            await msg.edit(embed=embed)
        except Exception:
            pass

    database.delete_recommendation(target.id)
    await interaction.response.send_message(f"✅ Accepted recommendation for {target.mention}.", ephemeral=True)

@bot.tree.command(name="decline", description="Decline a player recommendation")
@app_commands.checks.has_permissions(administrator=True)
async def decline(interaction: discord.Interaction, target: discord.User):
    rec_data = database.get_recommendation(target.id)
    if not rec_data:
        await interaction.response.send_message("❌ No active recommendation found for this user.", ephemeral=True)
        return

    recommender_id, channel_id, message_id, rblx_username, rblx_id, reason = rec_data
    channel = bot.get_channel(channel_id)

    if channel:
        try:
            msg = await channel.fetch_message(message_id)
            embed = msg.embeds[0]
            embed.color = discord.Color.red()
            embed.title = "Recommendation Declined"
            embed.add_field(name="Status", value=f"❌ Declined by {interaction.user.mention}", inline=False)
            await msg.edit(embed=embed)
        except Exception:
            pass

    database.delete_recommendation(target.id)
    await interaction.response.send_message(f"❌ Declined recommendation for {target.mention}.", ephemeral=True)

@bot.tree.command(name="say", description="Make the bot speak in a channel")
@app_commands.checks.has_permissions(administrator=True)
async def say(interaction: discord.Interaction, message: str, channel: discord.TextChannel = None):
    target_channel = channel or interaction.channel
    await target_channel.send(message)
    await interaction.response.send_message("Message sent!", ephemeral=True)

@bot.tree.command(name="dm", description="Send a direct message to a user")
@app_commands.checks.has_permissions(administrator=True)
async def dm(interaction: discord.Interaction, target: discord.User, message: str):
    try:
        await target.send(message)
        await interaction.response.send_message(f"✅ DM sent to {target.mention}.", ephemeral=True)
    except Exception:
        await interaction.response.send_message(f"❌ Could not DM {target.mention}. Their DMs might be closed.", ephemeral=True)

# Token Execution
bot.run(os.environ.get("BOT_TOKEN"))
