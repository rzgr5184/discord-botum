import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import json
import os
from flask import Flask
from threading import Thread

# ================= 7/24 AKTİF TUTMA (FLASK) =================
app = Flask('')

@app.route('/')
def home():
    return "Bot 7/24 Aktif!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# ================= BOT AYARLARI =================
# Render panelinde Environment Variables kısmına DISCORD_TOKEN eklemeyi unutma!
TOKEN = os.getenv("DISCORD_TOKEN") or "TOKEN_BURAYA_GELECEK"

DATA_FILE = "perm_roles.json"
DM_DELAY = 2.0
MAX_ALL_DM = 618
MAX_FAIL = 5

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ================= ROL DEPOLAMA =================
def load_roles():
    if not os.path.exists(DATA_FILE):
        return []
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def save_roles(role_ids):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(role_ids, f)

allowed_roles = load_roles()

def has_permission(member: discord.Member):
    if member.guild_permissions.administrator:
        return True
    return any(role.id in allowed_roles for role in member.roles)

# ================= MODAL VE MENÜLER =================
class MessageModal(discord.ui.Modal, title="DM Mesajı"):
    message = discord.ui.TextInput(
        label="Gönderilecek mesaj",
        style=discord.TextStyle.paragraph,
        max_length=1500
    )

    def __init__(self, members):
        super().__init__()
        self.members = members

    async def on_submit(self, interaction: discord.Interaction):
        sent = 0
        failed = 0
        await interaction.response.send_message("⏳ DM gönderimi başladı...", ephemeral=True)

        for member in self.members:
            if member.bot: continue
            try:
                await member.send(self.message.value)
                sent += 1
                await asyncio.sleep(DM_DELAY)
            except:
                failed += 1
                if failed >= MAX_FAIL: break

        await interaction.followup.send(f"✅ Gönderilen: {sent}\n❌ Başarısız: {failed}", ephemeral=True)

class UserPicker(discord.ui.UserSelect):
    def __init__(self):
        super().__init__(placeholder="DM atılacak kişileri seç", min_values=1, max_values=25)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(MessageModal(self.values))

class UserPickerView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
        self.add_item(UserPicker())

class MainView(discord.ui.View):
    def __init__(self, guild):
        super().__init__(timeout=60)
        self.guild = guild

    @discord.ui.button(label="👤 Kişi Seç", style=discord.ButtonStyle.primary)
    async def pick_users(self, interaction, button):
        await interaction.response.send_message("Kişileri seç:", view=UserPickerView(), ephemeral=True)

    @discord.ui.button(label="🌍 Herkese Gönder", style=discord.ButtonStyle.danger)
    async def send_all(self, interaction, button):
        members = [m for m in self.guild.members if not m.bot][:MAX_ALL_DM]
        await interaction.response.send_modal(MessageModal(members))

# ================= KOMUTLAR =================
@bot.tree.command(name="dm", description="DM gönderme paneli")
async def dm(interaction: discord.Interaction):
    if not has_permission(interaction.user):
        await interaction.response.send_message("❌ Yetkin yok.", ephemeral=True)
        return
    await interaction.response.send_message("📨 **DM Menüsü**", view=MainView(interaction.guild), ephemeral=True)

class RolePicker(discord.ui.RoleSelect):
    def __init__(self):
        super().__init__(placeholder="Rol seçin", min_values=1, max_values=10)

    async def callback(self, interaction: discord.Interaction):
        global allowed_roles
        allowed_roles = [role.id for role in self.values]
        save_roles(allowed_roles)
        await interaction.response.send_message("✅ Roller kaydedildi.", ephemeral=True)

class RolePickerView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
        self.add_item(RolePicker())

@bot.tree.command(name="perm", description="Yetkili rollerini ayarla")
async def perm(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Sadece admin.", ephemeral=True)
        return
    await interaction.response.send_message("🔐 **Rol Ayarı**", view=RolePickerView(), ephemeral=True)

# ================= BAŞLATMA =================
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ Bot aktif: {bot.user}")

if __name__ == "__main__":
    keep_alive() # Web sunucusunu yan kolda başlatır
    bot.run(TOKEN) # Botu ana kolda başlatır