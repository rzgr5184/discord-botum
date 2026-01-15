import discord
from discord import app_commands
from discord.ui import View, Button, UserSelect
import asyncio
import json
import os
from typing import List, Optional
from threading import Thread
from flask import Flask

# ═══════════════════════════════════════════════════════════════════════════
# 🔧 AYARLAR
# ═══════════════════════════════════════════════════════════════════════════
DM_DELAY = 2.5  # Saniye (Discord ban riskine karşı güvenli)
MAX_ERRORS = 50  # Bu kadar hata olursa durdur
PERMISSIONS_FILE = "dm_permissions.json"

# ═══════════════════════════════════════════════════════════════════════════
# 🌐 FLASK KEEP-ALIVE (Render/Replit için)
# ═══════════════════════════════════════════════════════════════════════════
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Bot çalışıyor!"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    thread = Thread(target=run_flask, daemon=True)
    thread.start()

# ═══════════════════════════════════════════════════════════════════════════
# 🤖 BOT SETUP
# ═══════════════════════════════════════════════════════════════════════════
intents = discord.Intents.default()
intents.members = True  # Üye listesi için ZORUNLU
intents.message_content = False  # DM botu için gereksiz

class DMBot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.dm_queue = asyncio.Queue()
        self.worker_running = False
        self.permissions = self.load_permissions()

    def load_permissions(self) -> dict:
        """İzinli rolleri yükle"""
        if os.path.exists(PERMISSIONS_FILE):
            with open(PERMISSIONS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def save_permissions(self):
        """İzinli rolleri kaydet"""
        with open(PERMISSIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.permissions, f, ensure_ascii=False, indent=2)

    def has_dm_permission(self, interaction: discord.Interaction) -> bool:
        """Kullanıcının DM yetkisi var mı kontrol et"""
        if interaction.user.guild_permissions.administrator:
            return True
        
        guild_id = str(interaction.guild_id)
        if guild_id not in self.permissions:
            return False
        
        allowed_roles = self.permissions[guild_id]
        user_role_ids = [role.id for role in interaction.user.roles]
        
        return any(role_id in allowed_roles for role_id in user_role_ids)

client = DMBot()

# ═══════════════════════════════════════════════════════════════════════════
# 📬 DM WORKER (KUYRUK İŞLEYİCİ)
# ═══════════════════════════════════════════════════════════════════════════
async def dm_worker(interaction: discord.Interaction, total: int):
    """DM kuyruğunu işle"""
    print(f"🚀 DM Worker başlatıldı | Toplam: {total}")
    
    sent = 0
    failed = 0
    progress_msg = None
    
    try:
        # İlerleme mesajı oluştur
        progress_msg = await interaction.followup.send(
            "📨 DM Gönderimi Başlatılıyor...",
            ephemeral=True,
            wait=True
        )
        
        while not client.dm_queue.empty():
            # Kuyruğun gerçekten boş olup olmadığını kontrol et
            try:
                member, message = await asyncio.wait_for(
                    client.dm_queue.get(),
                    timeout=1.0
                )
            except asyncio.TimeoutError:
                # Queue gerçekten boş
                break
            
            try:
                # DM gönder
                await member.send(message)
                sent += 1
                print(f"✅ DM gönderildi: {member.name} ({sent}/{total})")
                
            except discord.Forbidden:
                failed += 1
                print(f"❌ DM kapalı: {member.name}")
                
            except discord.HTTPException as e:
                failed += 1
                print(f"⚠️ HTTP Hatası: {member.name} - {e}")
                
            except Exception as e:
                failed += 1
                print(f"❌ Bilinmeyen hata: {member.name} - {e}")
            
            # İlerleme güncelle
            progress = int((sent + failed) / total * 100)
            bar_filled = int(progress / 10)
            bar_empty = 10 - bar_filled
            progress_bar = "█" * bar_filled + "░" * bar_empty
            
            await progress_msg.edit(content=
                f"📨 **DM Gönderiliyor**\n"
                f"{progress_bar} {progress}%\n\n"
                f"✅ Gönderilen: **{sent}**\n"
                f"❌ Başarısız: **{failed}**\n"
                f"📦 Toplam: **{total}**"
            )
            
            # Hata limiti kontrolü
            if failed >= MAX_ERRORS:
                await progress_msg.edit(content=
                    f"🛑 **DM Gönderimi Durduruldu**\n\n"
                    f"Çok fazla hata oluştu ({failed} hata)\n"
                    f"✅ Gönderilen: {sent}\n"
                    f"📦 Toplam: {total}"
                )
                print(f"🛑 Hata limiti aşıldı: {failed}/{MAX_ERRORS}")
                break
            
            # Rate limit koruması
            await asyncio.sleep(DM_DELAY)
            client.dm_queue.task_done()
        
        # Tamamlandı mesajı
        if failed < MAX_ERRORS:
            await progress_msg.edit(content=
                f"✅ **DM Gönderimi Tamamlandı!**\n\n"
                f"✅ Başarılı: **{sent}**\n"
                f"❌ Başarısız: **{failed}**\n"
                f"📦 Toplam: **{total}**"
            )
            print(f"✅ DM Worker tamamlandı | Başarılı: {sent}/{total}")
    
    except Exception as e:
        print(f"❌ Worker hatası: {e}")
        if progress_msg:
            await progress_msg.edit(content=f"❌ Kritik hata oluştu: {e}")
    
    finally:
        client.worker_running = False
        print("🔴 DM Worker durduruldu")

# ═══════════════════════════════════════════════════════════════════════════
# 📝 MODAL (DM Mesajı Yazma)
# ═══════════════════════════════════════════════════════════════════════════
class DMModal(discord.ui.Modal, title="DM Mesajı Yaz"):
    message = discord.ui.TextInput(
        label="Mesaj",
        placeholder="Göndermek istediğiniz mesajı yazın...",
        style=discord.TextStyle.long,
        required=True,
        max_length=2000
    )
    
    def __init__(self, members: List[discord.Member]):
        super().__init__()
        self.members = members
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        # Botları filtrele
        valid_members = [m for m in self.members if not m.bot]
        
        if not valid_members:
            await interaction.followup.send(
                "❌ Seçilen kullanıcılar arasında bot olmayan kimse yok!",
                ephemeral=True
            )
            return
        
        # Kuyruğa ekle
        for member in valid_members:
            await client.dm_queue.put((member, self.message.value))
        
        # Worker başlat
        if not client.worker_running:
            client.worker_running = True
            asyncio.create_task(dm_worker(interaction, len(valid_members)))
        else:
            await interaction.followup.send(
                f"➕ {len(valid_members)} kişi kuyruğa eklendi!",
                ephemeral=True
            )

# ═══════════════════════════════════════════════════════════════════════════
# 👥 USER SELECT (Çoklu Kişi Seçimi)
# ═══════════════════════════════════════════════════════════════════════════
class UserSelectView(View):
    def __init__(self):
        super().__init__(timeout=180)
    
    @discord.ui.select(
        cls=UserSelect,
        placeholder="DM göndermek istediğiniz kişileri seçin...",
        min_values=1,
        max_values=25  # Discord limiti
    )
    async def user_select_callback(
        self, 
        interaction: discord.Interaction, 
        select: UserSelect
    ):
        # User'ları Member'a dönüştür
        members = []
        for user in select.values:
            try:
                member = await interaction.guild.fetch_member(user.id)
                if not member.bot:  # Botları filtrele
                    members.append(member)
            except discord.NotFound:
                print(f"⚠️ Kullanıcı sunucuda değil: {user.name}")
        
        if not members:
            await interaction.response.send_message(
                "❌ Geçerli kullanıcı bulunamadı!",
                ephemeral=True
            )
            return
        
        # Modal aç
        modal = DMModal(members)
        await interaction.response.send_modal(modal)

# ═══════════════════════════════════════════════════════════════════════════
# 🎛️ DM PANELİ (Ana Butonlar)
# ═══════════════════════════════════════════════════════════════════════════
class DMPanelView(View):
    def __init__(self):
        super().__init__(timeout=180)
    
    @discord.ui.button(
        label="Tek Tek Kişi Seç",
        emoji="👤",
        style=discord.ButtonStyle.primary
    )
    async def select_users_button(
        self, 
        interaction: discord.Interaction, 
        button: Button
    ):
        view = UserSelectView()
        await interaction.response.send_message(
            "👥 **DM göndermek istediğiniz kişileri seçin:**",
            view=view,
            ephemeral=True
        )
    
    @discord.ui.button(
        label="Sunucudaki Herkese Gönder",
        emoji="🌍",
        style=discord.ButtonStyle.danger
    )
    async def everyone_button(
        self, 
        interaction: discord.Interaction, 
        button: Button
    ):
        # Tüm üyeleri al (bot olmayanlar)
        members = [m for m in interaction.guild.members if not m.bot]
        
        if not members:
            await interaction.response.send_message(
                "❌ Sunucuda bot olmayan üye yok!",
                ephemeral=True
            )
            return
        
        # Modal aç
        modal = DMModal(members)
        await interaction.response.send_modal(modal)

# ═══════════════════════════════════════════════════════════════════════════
# 🎮 KOMUTLAR
# ═══════════════════════════════════════════════════════════════════════════
@client.tree.command(
    name="dm",
    description="DM gönderme panelini açar"
)
async def dm_command(interaction: discord.Interaction):
    """DM panelini aç"""
    if not client.has_dm_permission(interaction):
        await interaction.response.send_message(
            "❌ Bu komutu kullanma yetkiniz yok!",
            ephemeral=True
        )
        return
    
    view = DMPanelView()
    await interaction.response.send_message(
        "📬 **DM Gönderme Paneli**\n\n"
        "Aşağıdaki butonlardan birini seçin:",
        view=view,
        ephemeral=True
    )

@client.tree.command(
    name="perm",
    description="DM yetkisi verilecek rolleri ayarla"
)
@app_commands.describe(
    roller="DM komutu kullanabilecek roller (virgülle ayırın)"
)
async def perm_command(
    interaction: discord.Interaction,
    roller: str
):
    """DM yetkilerini ayarla"""
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(
            "❌ Bu komutu sadece yöneticiler kullanabilir!",
            ephemeral=True
        )
        return
    
    await interaction.response.defer(ephemeral=True)
    
    # Rol ID'lerini ayıkla
    role_ids = []
    role_mentions = roller.replace(" ", "").split(",")
    
    for mention in role_mentions:
        # @Rol veya ID formatını destekle
        role_id = mention.replace("<@&", "").replace(">", "")
        try:
            role_id = int(role_id)
            role = interaction.guild.get_role(role_id)
            if role:
                role_ids.append(role_id)
        except ValueError:
            continue
    
    if not role_ids:
        await interaction.followup.send(
            "❌ Geçerli rol bulunamadı!\n\n"
            "**Kullanım:** `/perm roller: @Rol1, @Rol2` veya rol ID'leri",
            ephemeral=True
        )
        return
    
    # Kaydet
    guild_id = str(interaction.guild_id)
    client.permissions[guild_id] = role_ids
    client.save_permissions()
    
    role_names = [interaction.guild.get_role(r).name for r in role_ids]
    
    await interaction.followup.send(
        f"✅ **DM Yetkileri Güncellendi!**\n\n"
        f"Yetkili Roller:\n" + "\n".join(f"• {name}" for name in role_names),
        ephemeral=True
    )

# ═══════════════════════════════════════════════════════════════════════════
# 🚀 BOT BAŞLATMA
# ═══════════════════════════════════════════════════════════════════════════
@client.event
async def on_ready():
    await client.tree.sync()
    print(f"✅ Bot hazır: {client.user.name}")
    print(f"📊 Sunucu sayısı: {len(client.guilds)}")
    print(f"🔐 Yetkili sunucular: {len(client.permissions)}")

# ═══════════════════════════════════════════════════════════════════════════
# 🎯 MAIN
# ═══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    keep_alive()  # Flask'ı başlat
    
    TOKEN = os.getenv("DISCORD_TOKEN")
    if not TOKEN:
        print("❌ DISCORD_TOKEN environment variable bulunamadı!")
        exit(1)
    
    client.run(TOKEN)
