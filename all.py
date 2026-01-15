import discord
from discord.ext import commands
from discord import app_commands
import json
import os
from datetime import datetime
from flask import Flask
from threading import Thread

# ================= 7/24 AKTİF TUTMA (FLASK) =================
app = Flask('')

@app.route('/')
def home():
    return "Ticket Botu 7/24 Aktif!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# ================= AYARLAR =================
# Güvenlik için TOKEN'ı Render panelinden DISCORD_TOKEN adıyla ekle!
TOKEN = os.getenv("DISCORD_TOKEN") or "MTQ1OTk5Mzk0NzY1NTkwMTI0Nw.GcBMjD.FQVCHtz1oLSVj1rBNV7AtFqW_rBFxKSTSPz4d8"

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

DATA_FILE = "data.json"
TRANSCRIPT_DIR = "transcripts"

os.makedirs(TRANSCRIPT_DIR, exist_ok=True)

# Data dosyası yoksa oluştur (Hata vermemesi için eklendi)
if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump({"roles": {"ekip_alim": [], "ally_merge": [], "partnerlik": [], "genel_destek": []}}, f)

def load():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

# ---------------- TRANSCRIPT ----------------
async def create_transcript(channel: discord.TextChannel):
    messages = [m async for m in channel.history(limit=None, oldest_first=True)]
    html = f"<html><head><meta charset='utf-8'><title>Transcript - {channel.name}</title></head><body><h2>{channel.name}</h2><hr>"
    for msg in messages:
        time = msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
        html += f"<p><b>{msg.author}</b> [{time}]: {msg.content}</p>"
    html += "</body></html>"
    path = f"{TRANSCRIPT_DIR}/{channel.name}.html"
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path

# ---------------- UI ----------------
class CloseButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="🔒 Ticket Kapat", style=discord.ButtonStyle.danger)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message("📄 Transcript oluşturuluyor...", ephemeral=True)
        path = await create_transcript(interaction.channel)
        await interaction.channel.send("📄 **Transcript:**", file=discord.File(path))
        await asyncio.sleep(3) # Silinmeden önce kısa bir bekleme
        await interaction.channel.delete()

class CloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(CloseButton())

class TicketSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Ekip Alım", value="ekip_alim", emoji="🧑‍💻"),
            discord.SelectOption(label="Ally.Merge", value="ally_merge", emoji="🤝"),
            discord.SelectOption(label="Partnerlik", value="partnerlik", emoji="📢"),
            discord.SelectOption(label="Genel Destek", value="genel_destek", emoji="🆘")
        ]
        super().__init__(placeholder="Kategori seç", options=options)

    async def callback(self, interaction: discord.Interaction):
        guild = interaction.guild
        user = interaction.user
        category = self.values[0]

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True)
        }

        channel = await guild.create_text_channel(f"ticket-{user.name}", overwrites=overwrites)
        data = load()
        mentions = [guild.get_role(r).mention for r in data["roles"].get(category, []) if guild.get_role(r)]

        embed = discord.Embed(
            title="🎫 Ticket Açıldı",
            description=f"**Kategori:** {category.replace('_',' ').title()}\n**Açan:** {user.mention}",
            color=discord.Color.blurple()
        )
        await channel.send(content=" ".join(mentions) if mentions else None, embed=embed, view=CloseView())
        await interaction.response.send_message(f"✅ Ticket oluşturuldu: {channel.mention}", ephemeral=True)

class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketSelect())

class TicketButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="🎫 Ticket Aç", style=discord.ButtonStyle.success)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message("Kategori seç:", view=TicketView(), ephemeral=True)

class MainView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketButton())

# ---------------- COMMANDS ----------------
@bot.event
async def on_ready():
    await bot.tree.sync()
    # Bot kapandığında butonların çalışmaya devam etmesi için (Persistent Views)
    bot.add_view(MainView())
    bot.add_view(CloseView())
    print(f"✅ {bot.user} olarak giriş yapıldı ve Ticket sistemi hazır!")

@bot.tree.command(name="main", description="Ticket panelini seçilen kanala gönder")
@app_commands.checks.has_permissions(administrator=True)
async def main(interaction: discord.Interaction, channel: discord.TextChannel):
    embed = discord.Embed(
        title="🎫 Destek Sistemi",
        description="Ticket açmak için aşağıdaki butona bas",
        color=discord.Color.green()
    )
    await channel.send(embed=embed, view=MainView())
    await interaction.response.send_message("✅ Panel gönderildi", ephemeral=True)

@bot.tree.command(name="add", description="Kategoriye rol ekle")
@app_commands.checks.has_permissions(administrator=True)
async def add(interaction: discord.Interaction, category: str, role: discord.Role):
    data = load()
    if category not in data["roles"]:
        await interaction.response.send_message("❌ Geçersiz kategori", ephemeral=True)
        return
    if role.id not in data["roles"][category]:
        data["roles"][category].append(role.id)
        save(data)
    await interaction.response.send_message(f"✅ {role.mention} → **{category.replace('_',' ').title()}**", ephemeral=True)

@add.autocomplete("category")
async def cat_auto(interaction: discord.Interaction, current: str):
    cats = {"Ekip Alım": "ekip_alim", "Ally.Merge": "ally_merge", "Partnerlik": "partnerlik", "Genel Destek": "genel_destek"}
    return [app_commands.Choice(name=k, value=v) for k, v in cats.items() if current.lower() in k.lower()]

# ---------------- ÇALIŞTIRMA ----------------
if __name__ == "__main__":
    keep_alive() # Render uyanık tutma sunucusu
    bot.run(TOKEN)
