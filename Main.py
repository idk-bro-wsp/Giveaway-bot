import os
import discord
from discord.ext import commands
from discord import app_commands
import json
import asyncio
import uvicorn
import threading
import requests
import random

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

# -----------------------------
# Load config
# -----------------------------
with open("config.json", "r") as f:
    config = json.load(f)

TOKEN = os.getenv("TOKEN")  # Railway will use environment variable

PORT = int(os.getenv("PORT", 3015))

# -----------------------------
# Discord Bot Setup
# -----------------------------
intents = discord.Intents.default()
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
giveaways = {}

# -----------------------------
# Giveaway Buttons
# -----------------------------
class GiveawayView(discord.ui.View):
    def __init__(self, gid):
        super().__init__(timeout=None)
        self.gid = gid

    @discord.ui.button(label="Enter Giveaway", style=discord.ButtonStyle.green)
    async def enter(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = giveaways.get(self.gid)
        if not data:
            return await interaction.response.send_message("Giveaway not found.", ephemeral=True)

        if interaction.user.id in data["entries"]:
            return await interaction.response.send_message("You already entered.", ephemeral=True)

        data["entries"][interaction.user.id] = True
        await interaction.response.send_message("You entered the giveaway!", ephemeral=True)

# -----------------------------
# Giveaway Slash Command
# -----------------------------
@bot.tree.command(name="giveaway", description="Create a giveaway")
@app_commands.describe(duration="Seconds", prize="Prize")
async def giveaway(interaction: discord.Interaction, duration: int, prize: str):
    await interaction.response.defer(ephemeral=True)

    embed = discord.Embed(
        title="🎉 Giveaway",
        description=f"Prize: **{prize}**\nClick the button to enter!",
        color=discord.Color.green()
    )

    gid = interaction.id
    view = GiveawayView(gid)

    message = await interaction.channel.send(embed=embed, view=view)

    giveaways[gid] = {
        "message": message,
        "prize": prize,
        "entries": {}
    }

    await interaction.followup.send("Giveaway created!", ephemeral=True)

    await asyncio.sleep(duration)

    data = giveaways.get(gid)
    if not data:
        return

    if not data["entries"]:
        await interaction.channel.send("No one entered the giveaway.")
    else:
        winner_id = random.choice(list(data["entries"].keys()))
        await interaction.channel.send(f"🎉 Winner: <@{winner_id}> — {prize}")

    giveaways.pop(gid, None)

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Bot ready as {bot.user}")

# -----------------------------
# FastAPI Dashboard
# -----------------------------
app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=config["sessionSecret"])

def discord_oauth_url():
    return (
        "https://discord.com/api/oauth2/authorize"
        f"?client_id={config['clientId']}"
        "&response_type=code"
        f"&redirect_uri={config['redirectUri']}"
        "&scope=identify%20guilds"
    )

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    if "user" in request.session:
        return RedirectResponse("/dashboard")

    return HTMLResponse(f"""
    <html>
    <body style="background:#0f172a;color:white;font-family:sans-serif;text-align:center;padding-top:100px;">
        <h1>Giveaway Dashboard</h1>
        <a href="{discord_oauth_url()}" 
        style="padding:12px 20px;background:#5865F2;color:white;border-radius:8px;text-decoration:none;">
        Login with Discord
        </a>
    </body>
    </html>
    """)

@app.get("/callback")
async def callback(request: Request, code: str):
    data = {
        "client_id": config["clientId"],
        "client_secret": config["clientSecret"],
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": config["redirectUri"],
    }

    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    r = requests.post("https://discord.com/api/oauth2/token", data=data, headers=headers)
    token = r.json()

    access_token = token.get("access_token")
    if not access_token:
        return HTMLResponse("OAuth failed.", status_code=400)

    user = requests.get(
        "https://discord.com/api/users/@me",
        headers={"Authorization": f"Bearer {access_token}"}
    ).json()

    request.session["user"] = user
    return RedirectResponse("/dashboard")

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    if "user" not in request.session:
        return RedirectResponse("/")

    user = request.session["user"]

    return HTMLResponse(f"""
    <html>
    <body style="background:#0f172a;color:white;font-family:sans-serif;padding:30px;">
        <h2>Welcome {user['username']}</h2>
        <p>Your giveaway bot is running.</p>
    </body>
    </html>
    """)

# -----------------------------
# Run both bot and dashboard
# -----------------------------
def run_dashboard():
    uvicorn.run(app, host="0.0.0.0", port=PORT)

async def main():
    threading.Thread(target=run_dashboard, daemon=True).start()
    await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
