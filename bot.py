import discord
from discord import app_commands
from discord.ext import commands
import datetime
import os
import psycopg2  # PostgreSQL qoşulması üçün
from psycopg2.extras import RealDictCursor
from flask import Flask
from threading import Thread

# --- KODUN QURUCUSU (DEVELOPER) ---
DEVELOPER_ID = 1343211875663609878

# --- RENDER 7/24 UPTIME VEB SERVER ---
app = Flask('')

@app.route('/')
def home(): 
    return "Bot PostgreSQL bazası ilə Render üzərində aktivdir!"

def run(): 
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive(): 
    Thread(target=run).start()

# --- POSTGRESQL BAĞLANTISI (Aiven-ə Uyğun) ---
def get_db_connection():
    try:
        connection = psycopg2.connect(
            host=os.environ.get("PGHOST"),
            user=os.environ.get("PGUSER"),
            password=os.environ.get("PGPASSWORD"),
            database=os.environ.get("PGDATABASE"),
            port=int(os.environ.get("PGPORT", 5432)),
            sslmode="require",  # Aiven SSL mütləq tələb edir
            cursor_factory=RealDictCursor  # Məlumatları dict formasında almaq üçün
        )
        return connection
    except Exception as e:
        print(f"❌ PostgreSQL-ə qoşularkən xəta baş verdi: {e}")
        return None

# --- TABEL YARADILMASI (PostgreSQL formatında) ---
def init_db():
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cursor:
                # Server parametrləri cədvəli
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS guild_settings (
                        guild_id VARCHAR(50) PRIMARY KEY,
                        log_channel_id VARCHAR(50) DEFAULT NULL,
                        is_active BOOLEAN DEFAULT FALSE,
                        limit_ban INT DEFAULT 3,
                        limit_kick INT DEFAULT 3,
                        limit_role_delete INT DEFAULT 3,
                        limit_channel_delete INT DEFAULT 3,
                        limit_everyone INT DEFAULT 2
                    )
                """)
                # Whitelist istifadəçiləri cədvəli
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS guild_whitelist (
                        guild_id VARCHAR(50),
                        user_id VARCHAR(50),
                        PRIMARY KEY (guild_id, user_id)
                    )
                """)
                # Bildiriş alacaq rəhbərlik rolları cədvəli
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS guild_notification_roles (
                        guild_id VARCHAR(50),
                        role_id VARCHAR(50),
                        PRIMARY KEY (guild_id, role_id)
                    )
                """)
                conn.commit()
            print("✅ PostgreSQL Cədvəlləri uğurla yoxlanıldı/yaradıldı!")
        except Exception as e:
            print(f"❌ Cədvəllər yaradılanda xəta: {e}")
        finally:
            conn.close()

# Verilənlər bazasını yoxlayaq
init_db()

# --- MULTI-SERVER POSTGRESQL FUNKSİYALARI ---

def get_guild_data(guild_id: int):
    guild_key = str(guild_id)
    conn = get_db_connection()
    
    default_data = {
        "guild_id": guild_key, "whitelist": [], "notification_roles": [], 
        "log_channel_id": None, "is_active": False, "limit_ban": 3, 
        "limit_kick": 3, "limit_role_delete": 3, "limit_channel_delete": 3, "limit_everyone": 2
    }
    
    if not conn:
        return default_data

    try:
        with conn.cursor() as cursor:
            # 1. Server əsas parametrlərini çəkirik
            cursor.execute("SELECT * FROM guild_settings WHERE guild_id = %s", (guild_key,))
            row = cursor.fetchone()
            
            if not row:
                cursor.execute("INSERT INTO guild_settings (guild_id) VALUES (%s)", (guild_key,))
                conn.commit()
                row = {
                    "guild_id": guild_key, "log_channel_id": None, "is_active": False,
                    "limit_ban": 3, "limit_kick": 3, "limit_role_delete": 3,
                    "limit_channel_delete": 3, "limit_everyone": 2
                }
            
            data = {
                "guild_id": row["guild_id"],
                "log_channel_id": int(row["log_channel_id"]) if row["log_channel_id"] else None,
                "is_active": bool(row["is_active"]),
                "limit_ban": row["limit_ban"],
                "limit_kick": row["limit_kick"],
                "limit_role_delete": row["limit_role_delete"],
                "limit_channel_delete": row["limit_channel_delete"],
                "limit_everyone": row["limit_everyone"],
                "whitelist": [],
                "notification_roles": []
            }
            
            # 2. Whitelist siyahısını çəkirik
            cursor.execute("SELECT user_id FROM guild_whitelist WHERE guild_id = %s", (guild_key,))
            data["whitelist"] = [int(r["user_id"]) for r in cursor.fetchall()]
            
            # 3. Bildiriş rollarını çəkirik
            cursor.execute("SELECT role_id FROM guild_notification_roles WHERE guild_id = %s", (guild_key,))
            data["notification_roles"] = [int(r["role_id"]) for r in cursor.fetchall()]
            
            return data
    except Exception as e:
        print(f"⚠️ Məlumat çəkilərkən xəta: {e}")
        return default_data
    finally:
        conn.close()

def update_guild_data(guild_id: int, key: str, value):
    conn = get_db_connection()
    if not conn:
        return
    
    guild_key = str(guild_id)
    try:
        with conn.cursor() as cursor:
            if key == "whitelist":
                cursor.execute("DELETE FROM guild_whitelist WHERE guild_id = %s", (guild_key,))
                for user_id in value:
                    cursor.execute("INSERT INTO guild_whitelist (guild_id, user_id) VALUES (%s, %s)", (guild_key, str(user_id)))
            elif key == "notification_roles":
                cursor.execute("DELETE FROM guild_notification_roles WHERE guild_id = %s", (guild_key,))
                for role_id in value:
                    cursor.execute("INSERT INTO guild_notification_roles (guild_id, role_id) VALUES (%s, %s)", (guild_key, str(role_id)))
            else:
                cursor.execute(f"UPDATE guild_settings SET {key} = %s WHERE guild_id = %s", (value, guild_key))
            conn.commit()
    except Exception as e:
        print(f"⚠️ Verilənlər bazası yenilənərkən xəta: {e}")
    finally:
        conn.close()


# --- INTENTS (İCAZƏLƏR) YENİLƏNMƏSİ ---
intents = discord.Intents.default()
intents.members = True          # Üzvlərin giriş/çıxışını izləmək üçün (Mütləqdir!)
intents.moderation = True       # Ban hadisələrini (on_member_ban) eşitmək üçün (Mütləqdir!)
intents.guilds = True           # Server kanalları və rollarını izləmək üçün
intents.message_content = True  # Mesajları oxuyub spam qorumaq üçün

# --- POP-UP MODAL (LİMİTLƏRİ AYARLAMAQ ÜÇÜN PƏNCƏRƏ) ---

class LimitSettingsModal(discord.ui.Modal, title="⚙️ Anti-Nuke Limitlərini Ayarla"):
    ban_input = discord.ui.TextInput(
        label="Ban Limiti (60 saniyədə maksimum)", 
        placeholder="Nümunə: 3", 
        default="3", 
        min_length=1, 
        max_length=2
    )
    kick_input = discord.ui.TextInput(
        label="Kick Limiti (60 saniyədə maksimum)", 
        placeholder="Nümunə: 3", 
        default="3", 
        min_length=1, 
        max_length=2
    )
    role_input = discord.ui.TextInput(
        label="Rol Silmə Limiti (60 saniyədə maksimum)", 
        placeholder="Nümunə: 3", 
        default="3", 
        min_length=1, 
        max_length=2
    )
    channel_input = discord.ui.TextInput(
        label="Kanal Silmə Limiti (60 saniyədə)", 
        placeholder="Nümunə: 3", 
        default="3", 
        min_length=1, 
        max_length=2
    )
    everyone_input = discord.ui.TextInput(
        label="@everyone / @here Limiti (60 saniyədə)", 
        placeholder="Nümunə: 2", 
        default="2", 
        min_length=1, 
        max_length=2
    )

    def __init__(self, current_limits):
        super().__init__()
        self.ban_input.default = str(current_limits.get("limit_ban", 3))
        self.kick_input.default = str(current_limits.get("limit_kick", 3))
        self.role_input.default = str(current_limits.get("limit_role_delete", 3))
        self.channel_input.default = str(current_limits.get("limit_channel_delete", 3))
        self.everyone_input.default = str(current_limits.get("limit_everyone", 2))

    async def on_submit(self, interaction: discord.Interaction):
        try:
            b_lim = int(self.ban_input.value)
            k_lim = int(self.kick_input.value)
            r_lim = int(self.role_input.value)
            c_lim = int(self.channel_input.value)
            e_lim = int(self.everyone_input.value)
            
            if b_lim <= 0 or k_lim <= 0 or r_lim <= 0 or c_lim <= 0 or e_lim <= 0:
                await interaction.response.send_message("❌ Limit dəyərləri 0-dan böyük olmalıdır!", ephemeral=True)
                return
                
            guild_id = interaction.guild_id
            update_guild_data(guild_id, "limit_ban", b_lim)
            update_guild_data(guild_id, "limit_kick", k_lim)
            update_guild_data(guild_id, "limit_role_delete", r_lim)
            update_guild_data(guild_id, "limit_channel_delete", c_lim)
            update_guild_data(guild_id, "limit_everyone", e_lim)
            
            embed = discord.Embed(
                title="✅ Limitlər Yeniləndi",
                description="Bu server üçün qorunma limitləri uğurla yadda saxlanıldı!",
                color=discord.Color.green()
            )
            embed.add_field(name="Ban Limiti", value=f"{b_lim} dəfə / dəq", inline=True)
            embed.add_field(name="Kick Limiti", value=f"{k_lim} dəfə / dəq", inline=True)
            embed.add_field(name="Rol Silmə Limiti", value=f"{r_lim} dəfə / dəq", inline=True)
            embed.add_field(name="Kanal Silmə Limiti", value=f"{c_lim} dəfə / dəq", inline=True)
            embed.add_field(name="@everyone Limiti", value=f"{e_lim} dəfə / dəq", inline=True)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except ValueError:
            await interaction.response.send_message("❌ Zəhmət olmasa yalnız düzgün rəqəmlər daxil edin!", ephemeral=True)


# --- INTERAKTİV UI DÜYMƏLƏRİ (PANEL VIEW) ---

class ControlPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Sistemi Aktiv Et", style=discord.ButtonStyle.success, emoji="🛡️", custom_id="btn_activate")
    async def activate_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != DEVELOPER_ID and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Bu düyməni yalnız İdarəçilər istifadə edə bilər!", ephemeral=True)
            return
        
        guild_id = interaction.guild_id
        update_guild_data(guild_id, "is_active", True)
        
        embed = discord.Embed(
            title="🛡️ Anti-Nuke Statusu",
            description="Sistem bu server üçün uğurla **AKTİVLƏŞDİRİLDİ**.\nServer artıq tam qoruma altındadır!",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Sistemi Deaktiv Et", style=discord.ButtonStyle.danger, emoji="🔓", custom_id="btn_deactivate")
    async def deactivate_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != DEVELOPER_ID and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Bu düyməni yalnız İdarəçilər istifadə edə bilər!", ephemeral=True)
            return
        
        guild_id = interaction.guild_id
        update_guild_data(guild_id, "is_active", False)
        
        embed = discord.Embed(
            title="🔓 Anti-Nuke Statusu",
            description="Sistem bu server üçün **DEAKTİV EDİLDİ**.\nServer hazırda qorunmur!",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Limitləri Ayarla", style=discord.ButtonStyle.primary, emoji="⚙️", custom_id="btn_set_limits")
    async def set_limits_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != DEVELOPER_ID and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Limitləri yalnız İdarəçilər dəyişə bilər!", ephemeral=True)
            return
        
        gdata = get_guild_data(interaction.guild_id)
        await interaction.response.send_modal(LimitSettingsModal(current_limits=gdata))

    @discord.ui.button(label="Whitelist Göstər", style=discord.ButtonStyle.secondary, emoji="📋", custom_id="btn_whitelist")
    async def whitelist_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        gdata = get_guild_data(interaction.guild_id)
        users_mentions = [f"<@{uid}> (`{uid}`)" for uid in gdata["whitelist"]]
        
        embed = discord.Embed(
            title="📋 Whitelist (Güvənli Siyahı)",
            description="\n".join(users_mentions) if users_mentions else "*Bu server üçün hələ ki whitelist-ə heç kim əlavə edilməyib.*",
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class AntiNukeBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        
        self.ban_counter = {}          
        self.kick_counter = {}         
        self.role_delete_counter = {}  
        self.channel_delete_counter = {} 
        self.everyone_counter = {}     
        self.join_tracker = {}         

    async def setup_hook(self):
        self.add_view(ControlPanelView())
        print("✅ Düyməli İdarəetmə Paneli (Persistent View) aktivdir!")
        
        self.tree.add_command(whitelist_group)
        self.tree.add_command(staff_group)
        
        await self.tree.sync()
        print("✅ Bütün komandalar uğurla sinxronizasiya edildi!")

bot = AntiNukeBot()


# --- KÖMƏKÇİ FUNKSİYALAR ---

def is_whitelisted(guild_id: int, user_id: int) -> bool:
    if user_id == DEVELOPER_ID:
        return True
    gdata = get_guild_data(guild_id)
    return user_id in gdata["whitelist"]


async def punish_user(guild: discord.Guild, member: discord.Member, reason: str, duration_days: int = 25, duration_hours: int = 0, remove_roles: bool = True):
    if member.id == DEVELOPER_ID or member.id == guild.owner_id or is_whitelisted(guild.id, member.id):
        return

    roles_removed = False
    if remove_roles:
        try:
            roles_to_remove = [role for role in member.roles if not role.is_default() and role.position < guild.me.top_role.position]
            if roles_to_remove:
                await member.remove_roles(*roles_to_remove, reason=f"Anti-Nuke: {reason}")
                roles_removed = True
        except Exception as e:
            print(f"❌ Rol silərkən xəta baş verdi: {e}")

    try:
        duration = datetime.timedelta(days=duration_days, hours=duration_hours)
        if duration.total_seconds() == 0:
            duration = datetime.timedelta(hours=1)
            
        await member.timeout(duration, reason=f"Anti-Nuke: {reason}")
        print(f"✅ {member.name} uğurla {duration} müddətinə səssizliyə atıldı.")
    except Exception as e:
        print(f"❌ Səssizliyə atarkən xəta: {e}")

    embed = discord.Embed(
        title="🚨 CƏZA TƏTBİQ EDİLDİ",
        description=f"İstifadəçi anti-raid qaydalarını pozduğu üçün cəzalandırıldı.",
        color=discord.Color.dark_red(),
        timestamp=datetime.datetime.now(datetime.timezone.utc)
    )
    embed.add_field(name="👤 İstifadəçi", value=f"{member.mention} ({member.id})", inline=True)
    embed.add_field(name="🧠 Səbəb", value=reason, inline=True)
    
    cəza_mətni = "🛡️ Bütün rolları alındı və 25 gün susduruldu." if roles_removed else "🔇 1 saatlıq səssizliyə atıldı (Rollar alınmadı)."
    embed.add_field(name="🔨 Tətbiq Edilən Cəza", value=cəza_mətni, inline=False)
    embed.set_thumbnail(url=member.display_avatar.url)

    await send_log(
        guild, 
        embed=embed, 
        ping_staff=roles_removed, 
        ping_user=None if roles_removed else member
    )

async def send_log(guild: discord.Guild, embed: discord.Embed, ping_staff: bool = False, ping_user: discord.Member = None):
    gdata = get_guild_data(guild.id)
    log_id = gdata.get("log_channel_id")
    if not log_id:
        return
    channel = guild.get_channel(log_id)
    if channel:
        prefixes = []
        if ping_staff and gdata["notification_roles"]:
            prefixes.append(" ".join([f"<@&{role_id}>" for role_id in gdata["notification_roles"]]))
        if ping_user:
            prefixes.append(ping_user.mention)
            
        content_str = " ".join(prefixes) if prefixes else None
        await channel.send(content=content_str, embed=embed)


# --- SLAŞ KOMANDALARI ---

whitelist_group = app_commands.Group(name="whitelist", description="Bu server üçün Whitelist komandaları")

@whitelist_group.command(name="add", description="Bir istifadəçini whitelist-ə əlavə edir.")
@app_commands.checks.has_permissions(administrator=True)
async def wl_add(interaction: discord.Interaction, user: discord.User):
    await interaction.response.defer(ephemeral=True)
    guild_id = interaction.guild_id
    gdata = get_guild_data(guild_id)
    
    if user.id not in gdata["whitelist"]:
        gdata["whitelist"].append(user.id)
        update_guild_data(guild_id, "whitelist", gdata["whitelist"])
        embed = discord.Embed(description=f"✅ {user.mention} bu server üçün Whitelist-ə əlavə edildi.", color=discord.Color.green())
    else:
        embed = discord.Embed(description=f"ℹ️ {user.mention} artıq bu serverdə whitelist-dədir.", color=discord.Color.blue())
    await interaction.followup.send(embed=embed)

@whitelist_group.command(name="remove", description="Bir istifadəçini whitelist-dən çıxarır.")
@app_commands.checks.has_permissions(administrator=True)
async def wl_remove(interaction: discord.Interaction, user: discord.User):
    await interaction.response.defer(ephemeral=True)
    guild_id = interaction.guild_id
    gdata = get_guild_data(guild_id)
    
    if user.id in gdata["whitelist"]:
        gdata["whitelist"].remove(user.id)
        update_guild_data(guild_id, "whitelist", gdata["whitelist"])
        embed = discord.Embed(description=f"❌ {user.mention} bu server üçün Whitelist-dən çıxarıldı.", color=discord.Color.red())
    else:
        embed = discord.Embed(description=f"⚠️ {user.mention} bu serverin whitelist-ində yoxdur.", color=discord.Color.orange())
    await interaction.followup.send(embed=embed)


staff_group = app_commands.Group(name="staffrole", description="Anti-nuke bildirişi alacaq server rəhbərliyi rolları")

@staff_group.command(name="add", description="Cəza anında pinglənəcək rolu əlavə edir.")
@app_commands.checks.has_permissions(administrator=True)
async def staff_add(interaction: discord.Interaction, role: discord.Role):
    await interaction.response.defer(ephemeral=True)
    guild_id = interaction.guild_id
    gdata = get_guild_data(guild_id)
    
    if role.id not in gdata["notification_roles"]:
        gdata["notification_roles"].append(role.id)
        update_guild_data(guild_id, "notification_roles", gdata["notification_roles"])
        embed = discord.Embed(description=f"✅ {role.mention} rolu bu serverin bildiriş siyahısına əlavə olundu.", color=discord.Color.green())
    else:
        embed = discord.Embed(description=f"ℹ️ Bu rol artıq bu server üçün siyahıda var.", color=discord.Color.blue())
    await interaction.followup.send(embed=embed)

@staff_group.command(name="remove", description="Bildiriş alacaq rolu siyahıdan silir.")
@app_commands.checks.has_permissions(administrator=True)
async def staff_remove(interaction: discord.Interaction, role: discord.Role):
    await interaction.response.defer(ephemeral=True)
    guild_id = interaction.guild_id
    gdata = get_guild_data(guild_id)
    
    if role.id in gdata["notification_roles"]:
        gdata["notification_roles"].remove(role.id)
        update_guild_data(guild_id, "notification_roles", gdata["notification_roles"])
        embed = discord.Embed(description=f"❌ {role.mention} rolu bildiriş siyahısından silindi.", color=discord.Color.red())
    else:
        embed = discord.Embed(description=f"⚠️ Bu rol onsuz da siyahıda yoxdur.", color=discord.Color.orange())
    await interaction.followup.send(embed=embed)


@bot.tree.command(name="panel", description="Anti-Nuke idarəetmə panelini açar (Düyməli).")
@app_commands.guild_only()
@app_commands.checks.has_permissions(administrator=True)
async def open_panel(interaction: discord.Interaction):
    # Dondurmamaq üçün əvvəlcədən dərhal defer edirik
    await interaction.response.defer(ephemeral=True)
    
    guild_id = interaction.guild_id
    gdata = get_guild_data(guild_id)
    
    embed = discord.Embed(
        title="⚙️ Anti-Nuke İdarəetmə Paneli",
        description="Aşağıdakı düymələrdən istifadə edərək qoruma sistemini idarə edə bilərsiniz.",
        color=discord.Color.blurple()
    )
    embed.add_field(name="Sistem Statusu", value="🟢 Aktiv" if gdata["is_active"] else "🔴 Deaktiv", inline=True)
    embed.add_field(name="Log Kanalı", value=f"<#{gdata['log_channel_id']}>" if gdata["log_channel_id"] else "❌ Təyin edilməyib", inline=True)
    
    limit_info = (
        f"🔨 **Ban Limiti:** {gdata.get('limit_ban', 3)}/dəq\n"
        f"👢 **Kick Limiti:** {gdata.get('limit_kick', 3)}/dəq\n"
        f"🏷️ **Rol Silmə:** {gdata.get('limit_role_delete', 3)}/dəq\n"
        f"📁 **Kanal Silmə:** {gdata.get('limit_channel_delete', 3)}/dəq\n"
        f"📢 **@everyone:** {gdata.get('limit_everyone', 2)}/dəq"
    )
    embed.add_field(name="📊 Cari Limitlər", value=limit_info, inline=False)
    
    # Defer etdiyimiz üçün mütləq followup ilə göndəririk
    await interaction.followup.send(embed=embed, view=ControlPanelView())


@bot.tree.command(name="log", description="Log kanalını təyin edir.")
@app_commands.guild_only()
@app_commands.checks.has_permissions(administrator=True)
async def set_log(interaction: discord.Interaction, channel: discord.TextChannel):
    await interaction.response.defer(ephemeral=True)
    
    guild_id = interaction.guild_id
    update_guild_data(guild_id, "log_channel_id", channel.id)
    
    embed = discord.Embed(
        title="📝 Log Kanalı Təyin Edildi",
        description=f"Loglar artıq {channel.mention} kanalına göndəriləcək.",
        color=discord.Color.green()
    )
    await interaction.followup.send(embed=embed)


# --- HADİSƏLƏR (EVENTS) ---

@bot.event
async def on_message(message: discord.Message):
    if not message.guild or message.author.bot:
        return
        
    guild_id = message.guild.id
    gdata = get_guild_data(guild_id)
    
    if not gdata["is_active"] or is_whitelisted(guild_id, message.author.id):
        return

    # A) @everyone / @here Limiti
    everyone_count = message.content.count("@everyone") + message.content.count("@here")
    if everyone_count > 0:
        now = datetime.datetime.now(datetime.timezone.utc)
        user_key = (guild_id, message.author.id)
        
        if user_key not in bot.everyone_counter:
            bot.everyone_counter[user_key] = []
        
        bot.everyone_counter[user_key] = [t for t in bot.everyone_counter[user_key] if (now - t).total_seconds() < 60]
        for _ in range(everyone_count):
            bot.everyone_counter[user_key].append(now)

        cari_say = len(bot.everyone_counter[user_key])
        limit_val = gdata.get("limit_everyone", 2)
        
        if cari_say >= limit_val:
            try:
                await message.delete()
            except:
                pass
            await punish_user(message.guild, message.author, "Sürətli @everyone/@here limitini aşmaq", duration_days=25, duration_hours=0, remove_roles=True)
            bot.everyone_counter[user_key].clear()
            return
        else:
            qalan = limit_val - cari_say
            embed = discord.Embed(
                title="⚠️ WARN (XƏBƏRDARLIQ)",
                description=f"Hey! Sən indicə `@everyone` və ya `@here` işlətdin. Zəhmət olmasa limiti aşma!",
                color=discord.Color.gold()
            )
            embed.add_field(name="Təhlükəli Səviyyə", value=f"{cari_say}/{limit_val}", inline=True)
            embed.add_field(name="Qalan Haqqın", value=f"{qalan} dəfə", inline=True)
            
            await send_log(message.guild, embed=embed, ping_staff=False, ping_user=message.author)

    # B) Mass Mention Ping Qoruması
    mentions = message.mentions
    if message.reference and message.reference.cached_message:
        replied_to_user = message.reference.cached_message.author
        mentions = [m for m in mentions if m.id != replied_to_user.id]

    if len(mentions) > 1:
        try:
            await message.delete()
        except:
            pass
        await punish_user(
            guild=message.guild, 
            member=message.author, 
            reason=f"Mesaj daxilində çoxlu ping atmaq ({len(mentions)} nəfər)", 
            duration_days=0, 
            duration_hours=1, 
            remove_roles=False
        )
        return


@bot.event
async def on_member_ban(guild: discord.Guild, user: discord.User):
    # 1. Sistem aktivdirmi yoxlayırıq
    gdata = get_guild_data(guild.id)
    if not gdata.get("is_active"):
        return

    # 2. Banı kimin atdığını tapmaq üçün Audit Log-u çəkirik
    moderator = None
    try:
        async for entry in guild.audit_logs(limit=3, action=discord.AuditLogAction.ban):
            if entry.target.id == user.id:
                moderator = entry.user
                break
    except Exception as e:
        print(f"⚠️ Audit log oxunarkən xəta: {e}")

    # Əgər moderator tapılmadısa və ya banı bot özü atıbsa, dayanırıq
    if not moderator or moderator.id == bot.user.id:
        return

    # 3. İdarəçi, dev və ya whitelist-dirsə toxunmuruq (Sınaq zamanı buna mütləq diqqət et!)
    if moderator.id == guild.owner_id or moderator.id == DEVELOPER_ID or is_whitelisted(guild.id, moderator.id):
        return

    now = datetime.datetime.now(datetime.timezone.utc)
    key = (guild.id, moderator.id)

    if key not in bot.ban_counter:
        bot.ban_counter[key] = []

    # Son 60 saniyədən köhnələri təmizləyirik
    bot.ban_counter[key] = [
        t for t in bot.ban_counter[key]
        if (now - t).total_seconds() < 60
    ]

    # Cari banı siyahıya əlavə edirik
    bot.ban_counter[key].append(now)

    cari_say = len(bot.ban_counter[key])
    limit_val = gdata.get("limit_ban", 3)

    # 4. Limit aşımı və cəza
    if cari_say >= limit_val:
        member = guild.get_member(moderator.id)
        if not member:
            try:
                member = await guild.fetch_member(moderator.id)
            except:
                pass

        if member:
            await punish_user(
                guild=guild, 
                member=member, 
                reason=f"Ban limiti aşıldı! (60 saniyədə {cari_say} ban atıldı)",
                duration_days=25,
                duration_hours=0,
                remove_roles=True
            )
        bot.ban_counter[key].clear()
    
    # 5. Limit aşılmayıbsa, log kanalına dərhal xəbərdarlıq atırıq (Hər ban atılanda bura işləyəcək!)
    else:
        qalan = limit_val - cari_say
        embed = discord.Embed(
            title="⚠️ WARN (XƏBƏRDARLIQ) - Ban Limiti", 
            color=discord.Color.orange(),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        embed.add_field(name="Moderator", value=moderator.mention, inline=True)
        embed.add_field(name="Banlanan İstifadəçi", value=f"{user.name} ({user.id})", inline=True)
        embed.add_field(name="Həyata Keçən Ban", value=f"{cari_say}/{limit_val}", inline=True)
        embed.add_field(name="Qalan Ban Haqqı", value=f"{qalan} ban", inline=True)
        
        await send_log(guild, embed=embed, ping_staff=False, ping_user=moderator)


@bot.event
async def on_member_remove(member: discord.Member):
    guild = member.guild
    guild_id = guild.id
    gdata = get_guild_data(guild_id)
    if not gdata["is_active"]:
        return

    async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.kick):
        if entry.target.id == member.id:
            moderator = entry.user
            if is_whitelisted(guild_id, moderator.id) or moderator.id == bot.user.id:
                return

            now = datetime.datetime.now(datetime.timezone.utc)
            user_key = (guild_id, moderator.id)
            
            if user_key not in bot.kick_counter:
                bot.kick_counter[user_key] = []
            
            bot.kick_counter[user_key] = [t for t in bot.kick_counter[user_key] if (now - t).total_seconds() < 60]
            bot.kick_counter[user_key].append(now)

            cari_say = len(bot.kick_counter[user_key])
            limit_val = gdata.get("limit_kick", 3)

            if cari_say >= limit_val:
                await punish_user(guild, moderator, f"Ardıcıl {limit_val} nəfəri kickləmə limiti aşıldı", duration_days=25, duration_hours=0, remove_roles=True)
                bot.kick_counter[user_key].clear()
            else:
                qalan = limit_val - cari_say
                embed = discord.Embed(title="⚠️ WARN (XƏBƏRDARLIQ) - Kick Limiti", color=discord.Color.orange())
                embed.add_field(name="Moderator", value=moderator.mention, inline=True)
                embed.add_field(name="Həyata Keçən Kick", value=f"{cari_say}/{limit_val}", inline=True)
                embed.add_field(name="Qalan Haqqı", value=f"{qalan} kick", inline=True)
                
                await send_log(guild, embed=embed, ping_staff=False, ping_user=moderator)


@bot.event
async def on_guild_role_delete(role: discord.Role):
    guild = role.guild
    guild_id = guild.id
    gdata = get_guild_data(guild_id)
    if not gdata["is_active"]:
        return

    async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.role_delete):
        moderator = entry.user
        if is_whitelisted(guild_id, moderator.id) or moderator.id == bot.user.id:
            return

        now = datetime.datetime.now(datetime.timezone.utc)
        user_key = (guild_id, moderator.id)
        
        if user_key not in bot.role_delete_counter:
            bot.role_delete_counter[user_key] = []
        
        bot.role_delete_counter[user_key] = [t for t in bot.role_delete_counter[user_key] if (now - t).total_seconds() < 60]
        bot.role_delete_counter[user_key].append(now)

        cari_say = len(bot.role_delete_counter[user_key])
        limit_val = gdata.get("limit_role_delete", 3)

        if cari_say >= limit_val:
            await punish_user(guild, moderator, f"Ardıcıl {limit_val} rol silmə limiti aşıldı", duration_days=25, duration_hours=0, remove_roles=True)
            bot.role_delete_counter[user_key].clear()
        else:
            qalan = limit_val - cari_say
            embed = discord.Embed(title="⚠️ WARN (XƏBƏRDARLIQ) - Rol Silindi", color=discord.Color.orange())
            embed.add_field(name="Moderator", value=moderator.mention, inline=True)
            embed.add_field(name="Silinən Rol", value=role.name, inline=True)
            embed.add_field(name="Limit", value=f"{cari_say}/{limit_val} (Qalan: {qalan})", inline=False)
            
            await send_log(guild, embed=embed, ping_staff=False, ping_user=moderator)


@bot.event
async def on_guild_channel_delete(channel: discord.abc.GuildChannel):
    guild = channel.guild
    guild_id = guild.id
    gdata = get_guild_data(guild_id)
    if not gdata["is_active"]:
        return

    async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_delete):
        moderator = entry.user
        if is_whitelisted(guild_id, moderator.id) or moderator.id == bot.user.id:
            return

        now = datetime.datetime.now(datetime.timezone.utc)
        user_key = (guild_id, moderator.id)
        
        if user_key not in bot.channel_delete_counter:
            bot.channel_delete_counter[user_key] = []
        
        bot.channel_delete_counter[user_key] = [t for t in bot.channel_delete_counter[user_key] if (now - t).total_seconds() < 60]
        bot.channel_delete_counter[user_key].append(now)

        cari_say = len(bot.channel_delete_counter[user_key])
        limit_val = gdata.get("limit_channel_delete", 3)

        if cari_say >= limit_val:
            await punish_user(guild, moderator, f"Ardıcıl {limit_val} kanal silmə limiti aşıldı", duration_days=25, duration_hours=0, remove_roles=True)
            bot.channel_delete_counter[user_key].clear()
        else:
            qalan = limit_val - cari_say
            embed = discord.Embed(title="⚠️ WARN (XƏBƏRDARLIQ) - Kanal Silindi", color=discord.Color.orange())
            embed.add_field(name="Moderator", value=moderator.mention, inline=True)
            embed.add_field(name="Silinən Kanal", value=channel.name, inline=True)
            embed.add_field(name="Limit", value=f"{cari_say}/{limit_val} (Qalan: {qalan})", inline=False)
            
            await send_log(guild, embed=embed, ping_staff=False, ping_user=moderator)


@bot.event
async def on_member_join(member: discord.Member):
    guild = member.guild
    guild_id = guild.id
    gdata = get_guild_data(guild_id)
    if not gdata["is_active"]:
        return

    if member.bot:
        async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.bot_add):
            inviter = entry.user
            if not is_whitelisted(guild_id, inviter.id):
                try:
                    await member.ban(reason="İcazəsiz bot girişi.")
                except Exception as e:
                    print(f"Bot banlana bilmədi: {e}")
                
                await punish_user(guild, inviter, f"Servere icazəsiz bot əlavə etdi ({member.name})", duration_days=25, duration_hours=0, remove_roles=True)
                return

    now = datetime.datetime.now(datetime.timezone.utc)
    if guild_id not in bot.join_tracker:
        bot.join_tracker[guild_id] = []
        
    bot.join_tracker[guild_id] = [t for t in bot.join_tracker[guild_id] if (now - t).total_seconds() < 10]
    bot.join_tracker[guild_id].append(now)

    if len(bot.join_tracker[guild_id]) > 10:
        embed = discord.Embed(
            title="🚨 TƏCİLİ: RAID SİQNALI!",
            description="Serverə son 10 saniyədə 10-dan çox yeni hesab daxil oldu. Raid hücumu baş vermiş ola bilər!",
            color=discord.Color.red()
        )
        embed.set_footer(text="Qoruyucu heyət dərhal serveri yoxlamalıdır.")
        await send_log(guild, embed=embed, ping_staff=True)
        bot.join_tracker[guild_id].clear()


# --- BOTU VƏ VEB SERVERİ BAŞLATMAQ ---
keep_alive()

TOKEN = os.environ.get("TOKEN")
if not TOKEN:
    print("❌ XƏTA: Render panelində TOKEN ətraf mühit dəyişəni tapılmadı!")
else:
    bot.run(TOKEN)
