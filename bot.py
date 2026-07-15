import discord
from discord import app_commands
from discord.ext import commands
import datetime
import os
import pymongo  # MongoDB üçün lazımdır
from flask import Flask
from threading import Thread

# --- KODUN QURUCUSU (DEVELOPER) ---
DEVELOPER_ID = 1343211875663609878

# --- RENDER 7/24 UPTIME VEB SERVER ---
app = Flask('')

@app.route('/')
def home(): 
    return "Bot Render uzerinde aktivdir!"

def run(): 
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive(): 
    Thread(target=run).start()

# --- MONGODB BAĞLANTISI ---
# Render-da Environment Variables bölməsində MONGO_URI dəyişənini təyin edəcəyik.
MONGO_URI = os.environ.get("MONGO_URI", "SƏNİN_MONGODB_KOPYALADIĞIN_LINK_BURA")

try:
    mongo_client = pymongo.MongoClient(MONGO_URI)
    db = mongo_client["anti_nuke_database"]
    collection = db["guild_settings"]
    print("✅ MongoDB Verilənlər Bazasına uğurla qoşulduq!")
except Exception as e:
    print(f"❌ Verilənlər bazasına qoşularkən xəta: {e}")

# --- MULTI-SERVER MONGODB FUNKSİYALARI (Köhnə JSON yerinə) ---

def get_guild_data(guild_id: int):
    guild_key = str(guild_id)
    
    # Bazadan həmin serverin məlumatını axtarırıq
    data = collection.find_one({"guild_id": guild_key})
    
    # Əgər server ilk dəfə botu işlədirsə (data.json-da yaradıldığı kimi), avtomatik şablon yaradırıq
    if not data:
        default_data = {
            "guild_id": guild_key,
            "whitelist": [],
            "notification_roles": [],
            "log_channel_id": None,
            "is_active": False,
            "limit_ban": 3,
            "limit_kick": 3,
            "limit_role_delete": 3,
            "limit_channel_delete": 3,
            "limit_everyone": 2
        }
        collection.insert_one(default_data)
        return default_data
    
    # Əgər sonradan yeni limit ayarları gəlibsə və köhnə server məlumatında yoxdursa, avtomatik əlavə edirik
    updated = False
    for key, default_val in [
        ("limit_ban", 3), 
        ("limit_kick", 3), 
        ("limit_role_delete", 3), 
        ("limit_channel_delete", 3), 
        ("limit_everyone", 2)
    ]:
        if key not in data:
            data[key] = default_val
            updated = True
            
    if updated:
        collection.replace_one({"guild_id": guild_key}, data)
            
    return data

def update_guild_data(guild_id: int, key: str, value):
    guild_key = str(guild_id)
    
    # Lazımi dəyişən açarı (key) bazada yeniləyirik (yoxdursa yaradırıq)
    collection.update_one(
        {"guild_id": guild_key},
        {"$set": {key: value}},
        upsert=True
    )


intents = discord.Intents.default()
intents.members = True
intents.moderation = True
intents.message_content = True
intents.guilds = True

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
        # Köhnə load_all_data() artıq lazım deyil, çünki hər şey birbaşa MongoDB ilə idarə olunur
        self.tree.add_command(whitelist_group)
        self.tree.add_command(staff_group)
        await self.tree.sync()

bot = AntiNukeBot()


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
            roles_to_remove = [role for role in member.roles if not role.is_default()]
            if roles_to_remove:
                await member.remove_roles(*roles_to_remove, reason=f"Anti-Nuke: {reason}")
                roles_removed = True
        except Exception as e:
            print(f"❌ Rol silərkən xəta baş verdi: {e} (Görünür botun rolu bu istifadəçidən aşağıdadır)")

    try:
        duration = datetime.timedelta(days=duration_days, hours=duration_hours)
        
        if duration.total_seconds() == 0:
            duration = datetime.timedelta(hours=1)
            
        await member.timeout(duration, reason=f"Anti-Nuke: {reason}")
        print(f"✅ {member.name} uğurla {duration} müddətinə səssizliyə atıldı.")
    except Exception as e:
        print(f"❌ Səssizliyə (timeout) atarkən xəta: {e}. Botun 'Moderate Members' icazəsi varmı?")

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
    guild_id = interaction.guild_id
    gdata = get_guild_data(guild_id)
    
    if user.id not in gdata["whitelist"]:
        gdata["whitelist"].append(user.id)
        update_guild_data(guild_id, "whitelist", gdata["whitelist"])
        embed = discord.Embed(description=f"✅ {user.mention} bu server üçün Whitelist-ə əlavə edildi.", color=discord.Color.green())
    else:
        embed = discord.Embed(description=f"ℹ️ {user.mention} artıq bu serverdə whitelist-dədir.", color=discord.Color.blue())
    await interaction.response.send_message(embed=embed, ephemeral=True)

@whitelist_group.command(name="remove", description="Bir istifadəçini whitelist-dən çıxarır.")
@app_commands.checks.has_permissions(administrator=True)
async def wl_remove(interaction: discord.Interaction, user: discord.User):
    guild_id = interaction.guild_id
    gdata = get_guild_data(guild_id)
    
    if user.id in gdata["whitelist"]:
        gdata["whitelist"].remove(user.id)
        update_guild_data(guild_id, "whitelist", gdata["whitelist"])
        embed = discord.Embed(description=f"❌ {user.mention} bu server üçün Whitelist-dən çıxarıldı.", color=discord.Color.red())
    else:
        embed = discord.Embed(description=f"⚠️ {user.mention} bu serverin whitelist-ində yoxdur.", color=discord.Color.orange())
    await interaction.response.send_message(embed=embed, ephemeral=True)


staff_group = app_commands.Group(name="staffrole", description="Anti-nuke bildirişi alacaq server rəhbərliyi rolları")

@staff_group.command(name="add", description="Cəza anında pinglənəcək rolu əlavə edir.")
@app_commands.checks.has_permissions(administrator=True)
async def staff_add(interaction: discord.Interaction, role: discord.Role):
    guild_id = interaction.guild_id
    gdata = get_guild_data(guild_id)
    
    if role.id not in gdata["notification_roles"]:
        gdata["notification_roles"].append(role.id)
        update_guild_data(guild_id, "notification_roles", gdata["notification_roles"])
        embed = discord.Embed(description=f"✅ {role.mention} rolu bu serverin bildiriş siyahısına əlavə olundu.", color=discord.Color.green())
    else:
        embed = discord.Embed(description=f"ℹ️ Bu rol artıq bu server üçün siyahıda var.", color=discord.Color.blue())
    await interaction.response.send_message(embed=embed, ephemeral=True)

@staff_group.command(name="remove", description="Bildiriş alacaq rolu siyahıdan silir.")
@app_commands.checks.has_permissions(administrator=True)
async def staff_remove(interaction: discord.Interaction, role: discord.Role):
    guild_id = interaction.guild_id
    gdata = get_guild_data(guild_id)
    
    if role.id in gdata["notification_roles"]:
        gdata["notification_roles"].remove(role.id)
        update_guild_data(guild_id, "notification_roles", gdata["notification_roles"])
        embed = discord.Embed(description=f"❌ {role.mention} rolu bildiriş siyahısından silindi.", color=discord.Color.red())
    else:
        embed = discord.Embed(description=f"⚠️ Bu rol onsuz da siyahıda yoxdur.", color=discord.Color.orange())
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="panel", description="Anti-Nuke idarəetmə panelini açar (Düyməli).")
@app_commands.guild_only()
@app_commands.checks.has_permissions(administrator=True)
async def open_panel(interaction: discord.Interaction):
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
    
    await interaction.response.send_message(embed=embed, view=ControlPanelView())

@bot.tree.command(name="log", description="Log kanalını təyin edir.")
@app_commands.guild_only()
@app_commands.checks.has_permissions(administrator=True)
async def set_log(interaction: discord.Interaction, channel: discord.TextChannel):
    guild_id = interaction.guild_id
    update_guild_data(guild_id, "log_channel_id", channel.id)
    
    embed = discord.Embed(
        title="📝 Log Kanalı Təyin Edildi",
        description=f"Loglar artıq {channel.mention} kanalına göndəriləcək.",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


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
    guild_id = guild.id
    gdata = get_guild_data(guild_id)
    if not gdata["is_active"]:
        return

    async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.ban):
        moderator = entry.user
        if is_whitelisted(guild_id, moderator.id) or moderator.id == bot.user.id:
            return

        now = datetime.datetime.now(datetime.timezone.utc)
        user_key = (guild_id, moderator.id)
        
        if user_key not in bot.ban_counter:
            bot.ban_counter[user_key] = []
        
        bot.ban_counter[user_key] = [t for t in bot.ban_counter[user_key] if (now - t).total_seconds() < 60]
        bot.ban_counter[user_key].append(now)

        cari_say = len(bot.ban_counter[user_key])
        limit_val = gdata.get("limit_ban", 3)

        if cari_say >= limit_val:
            await punish_user(guild, moderator, f"Ardıcıl {limit_val} nəfəri banlama limiti aşıldı", duration_days=25, duration_hours=0, remove_roles=True)
            bot.ban_counter[user_key].clear()
        else:
            qalan = limit_val - cari_say
            embed = discord.Embed(title="⚠️ WARN (XƏBƏRDARLIQ) - Ban Limiti", color=discord.Color.orange())
            embed.add_field(name="Moderator", value=moderator.mention, inline=True)
            embed.add_field(name="Həyata Keçən Ban", value=f"{cari_say}/{limit_val}", inline=True)
            embed.add_field(name="Qalan Haqqı", value=f"{qalan} ban", inline=True)
            
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

TOKEN = os.environ.get("TOKEN", "BOTA_AİD_TOKENİ_BURA_YAZIN")
bot.run(TOKEN)
