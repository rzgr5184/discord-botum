import discord
from discord.ext import commands
import asyncio
import json
import os
from flask import Flask
from threading import Thread
from collections import deque

# ================= KEEP ALIVE =================
app = Flask("")

@app.route("/")
def home():
    return "Bot aktif"

def run():
    app.run(host="0.0.0.0", port=8080)

def keep_alive():
    Thread(target=run).start()

# ================= AYARLAR =================
TOKEN = os.getenv("DISCORD_TOKEN")
DATA_FILE = "perm_roles.json"

DM_DELAY = 6.0
MAX_FAIL = 10

# ================= INTENTS =================
intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ================= ROLE STORAGE =================
def load_roles():
    if not os.path.exists(DATA_FILE):
        return []
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def save_roles(roles):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(roles, f)

allowed_roles = load_roles()

def has_permission(member):
    if member.guild_permissions.administrator:
        return True
    return any(r.id in allowed_roles for r in member.roles)

# ================= DM QUEUE + PROGRESS =================
dm_queue = deque()
dm_running = False
dm_total = 0
dm_sent = 0
progress_message = None

async def dm_worker():
    global dm_running, dm_sent, progress_message
    dm_running = True
    fails = 0

    while dm_queue:
        member, message = dm_queue.popleft()
        try:
            if not member.bot:
                await member.send(message)
                dm_sent += 1
                await asyncio.sleep(DM_DELAY)
        except:
            fails += 1
            if fails >= MAX_FAIL:
                break

        if progress_message:
            await progress_message.edit(
                content=f"📊 **DM Gönderiliyor**\n"
                        f"✅ Gönderilen: {dm_sent}/{dm_total}\n"
                        f"⏳ Kalan: {dm_total - dm_sent}"
            )

    if progress_message:
        await progress_message.edit(
            content=f"🎉 **DM Gönderimi Bitti**\n"
                    f"✅ Toplam: {dm_sent}/{dm_total}"
        )

    dm_running = False
    dm_queue.clear()

# ================= MODAL =================
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
        global dm_total, dm_sent, progress_message

        dm_total = len(self.members)
        dm_sent = 0

        await interaction.response.send_message(
            f"📊 {dm_total} kişi kuyruğa eklendi.",
            ephemeral=True
        )

        for m in self.members:
            dm_queue.append((m, self.message.value))

        progress_message = await interaction.followup.send(
            f"📊 **DM Gönderiliyor**\n"
            f"✅ Gönderilen: 0/{dm_total}\n"
            f"⏳ Kalan: {dm_total}",
            ephemeral=True
        )

        if not dm_running:
            bot.loop.create_task(dm_worker())

# ================= USER SELECT =================
class UserPicker(discord.ui.UserSelect):
    def __init__(self):
        super().__init__(
            placeholder="DM atılacak kişileri seç",
            min_values=1,
            max_values=25
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(
            MessageModal(self.values)
        )

class UserPickerView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
        self.add_item(UserPicker())

# ================= MAIN VIEW =================
class MainView(discord.ui.View):
    def __init__(self, guild):
        super().__init__(timeout=60)
        self.guild = guild

    @discord.ui.button(label="👤 Kişi Seçerek Gönder", style=discord.ButtonStyle.primary)
    async def pick_users(self, interaction: discord.Interaction, button):
        await interaction.response.send_message(
            "Kişileri seç:",
            view=UserPickerView(),
            ephemeral=True
        )

    @discord.ui.button(label="🌍 Herkese Gönder (700)", style=discord.ButtonStyle.danger)
    async def send_all(self, interaction: discord.Interaction, button):
        members = [m for m in self.guild.members if not m.bot]
        await interaction.response.send_modal(
            MessageModal(members)
        )

# ================= KOMUTLAR =================
@bot.tree.command(name="dm", description="DM gönderme paneli")
async def dm(interaction: discord.Interaction):
    if not has_permission(interaction.user):
        await interaction.response.send_message(
            "❌ Yetkin yok.",
            ephemeral=True
        )
        return

    await interaction.response.send_message(
        "📨 **DM Paneli**",
        view=MainView(interaction.guild),
        ephemeral=True
    )

class RolePicker(discord.ui.RoleSelect):
    def __init__(self):
        super().__init__(
            placeholder="DM yetkili roller",
            min_values=1,
            max_values=10
        )

    async def callback(self, interaction: discord.Interaction):
        global allowed_roles
        allowed_roles = [r.id for r in self.values]
        save_roles(allowed_roles)
        await interaction.response.send_message(
            "✅ Roller kaydedildi.",
            ephemeral=True
        )

class RoleView(discord.ui.View):
    def __init__(self):
        super().__init__()
        self.add_item(RolePicker())

@bot.tree.command(name="perm", description="DM yetkisini ayarla")
async def perm(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(
            "❌ Sadece admin.",
            ephemeral=True
        )
        return

    await interaction.response.send_message(
        "🔐 Yetkili roller:",
        view=RoleView(),
        ephemeral=True
    )

# ================= READY =================
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ Bot aktif: {bot.user}")

# ================= RUN =================
if __name__ == "__main__":
    keep_alive()
    bot.run(TOKEN)
