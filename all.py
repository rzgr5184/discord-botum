import discord
from discord.ext import commands
from discord import app_commands
import os, json, asyncio, datetime
from flask import Flask
from threading import Thread

# ================= 7/24 =================
app = Flask("")

@app.route("/")
def home():
    return "Ticket Bot Aktif"

def keep_alive():
    Thread(target=lambda: app.run(host="0.0.0.0", port=8080)).start()

# ================= AYAR =================
TOKEN = os.getenv("DISCORD_TOKEN")
DATA_FILE = "ticket_data.json"
AUTO_CLOSE_MINUTES = 60

TICKET_CATEGORIES = {
    "ekip": "👥 Ekip Alım",
    "ally": "🤝 Ally / Merge",
    "partner": "🤝 Partnerlik",
    "destek": "💬 Genel Destek"
}

# ================= INTENTS =================
intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ================= DATA =================
if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, "w") as f:
        json.dump({
            "roles": {},
            "log_channel": None,
            "ticket_count": 0
        }, f)

def load():
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

# ================= TRANSCRIPT =================
async def create_transcript(channel):
    messages = []
    async for msg in channel.history(limit=None, oldest_first=True):
        time = msg.created_at.strftime("%Y-%m-%d %H:%M")
        messages.append(f"<p><b>[{time}] {msg.author}:</b> {msg.content}</p>")

    html = f"""
    <html><body>
    <h2>Transcript: {channel.name}</h2>
    {''.join(messages)}
    </body></html>
    """

    path = f"transcript-{channel.id}.html"
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)

    return path

# ================= UI =================
class CloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 Kapat", style=discord.ButtonStyle.secondary)
    async def close(self, interaction: discord.Interaction, button):
        await interaction.response.send_message("⏳ Ticket kapatılıyor...", ephemeral=True)
        await auto_close(interaction.channel)

    @discord.ui.button(label="🗑️ Sil", style=discord.ButtonStyle.danger)
    async def delete(self, interaction: discord.Interaction, button):
        await interaction.channel.delete()

async def auto_close(channel):
    data = load()
    log_id = data["log_channel"]
    transcript = await create_transcript(channel)

    if log_id:
        log = channel.guild.get_channel(log_id)
        if log:
            await log.send(
                f"📑 Ticket kapandı: {channel.name}",
                file=discord.File(transcript)
            )

    await asyncio.sleep(5)
    await channel.delete()

class CategorySelect(discord.ui.Select):
    def __init__(self):
        super().__init__(
            placeholder="Kategori seç",
            options=[discord.SelectOption(label=v, value=k) for k, v in TICKET_CATEGORIES.items()]
        )

    async def callback(self, interaction: discord.Interaction):
        data = load()
        data["ticket_count"] += 1
        save(data)

        guild = interaction.guild
        roles = data["roles"].get(self.values[0], [])
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True)
        }

        mentions = []
        for rid in roles:
            role = guild.get_role(rid)
            if role:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True)
                mentions.append(role.mention)

        channel = await guild.create_text_channel(
            f"ticket-{data['ticket_count']}",
            overwrites=overwrites
        )

        await channel.send(
            f"{interaction.user.mention} ticket açtı\n{' '.join(mentions)}",
            view=CloseView()
        )

        await interaction.response.send_message(
            f"✅ Ticket oluşturuldu: {channel.mention}",
            ephemeral=True
        )

        bot.loop.create_task(auto_timeout(channel))

async def auto_timeout(channel):
    await asyncio.sleep(AUTO_CLOSE_MINUTES * 60)
    if channel:
        await auto_close(channel)

class PanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎫 Ticket Aç", style=discord.ButtonStyle.primary)
    async def open(self, interaction: discord.Interaction, button):
        await interaction.response.send_message(
            "Kategori seç:",
            view=discord.ui.View().add_item(CategorySelect()),
            ephemeral=True
        )

# ================= KOMUTLAR =================
@bot.tree.command(name="main")
async def main(interaction: discord.Interaction, channel: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Yetkin yok", ephemeral=True)

    await channel.send("🎟️ **Ticket Sistemi**", view=PanelView())
    await interaction.response.send_message("✅ Panel kuruldu", ephemeral=True)

@bot.tree.command(name="add")
async def add(interaction: discord.Interaction, category: str):
    if category not in TICKET_CATEGORIES:
        return await interaction.response.send_message("❌ Geçersiz kategori", ephemeral=True)

    class RoleSelect(discord.ui.RoleSelect):
        async def callback(self, interaction):
            data = load()
            data["roles"][category] = [r.id for r in self.values]
            save(data)
            await interaction.response.send_message("✅ Roller kaydedildi", ephemeral=True)

    view = discord.ui.View()
    view.add_item(RoleSelect())
    await interaction.response.send_message("Rolleri seç:", view=view, ephemeral=True)

@bot.tree.command(name="log")
async def log(interaction: discord.Interaction, channel: discord.TextChannel):
    data = load()
    data["log_channel"] = channel.id
    save(data)
    await interaction.response.send_message("✅ Log kanalı ayarlandı", ephemeral=True)

# ================= READY =================
@bot.event
async def on_ready():
    await bot.tree.sync()
    print("Ticket Bot Aktif")

if __name__ == "__main__":
    keep_alive()
    bot.run(TOKEN)
