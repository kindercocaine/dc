import os
import sys
import json
import time
import re
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv

# Windows konsolunda Türkçe karakter ve emoji desteği
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# .env dosyasındaki ayarları yükle
load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))  # Eski uyumluluk için tutuldu
ALLAH_ID = 416978259557744640                # En üst yetki - Allah
UNREGISTERED_ROLE_ID = 1544443560571576380   # Kayıtsız Rolü ID
REGISTERED_ROLE_ID = 1544413431409410058     # Kayıtlı Rolü ID

# Ayar ve yetki dosyaları yolları
BASE_DIR = os.path.dirname(__file__)
AUTH_FILE = os.path.join(BASE_DIR, "authorized.json")       # Yetkili listesi (.yt)
KURUCU_FILE = os.path.join(BASE_DIR, "kurucu.json")         # Kurucu listesi
SESYT_FILE = os.path.join(BASE_DIR, "sesyt.json")           # Ses yetkilisi listesi (.sesyt)
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

# Hız için Bellek İçi (In-Memory) Önbellekler
_cached_config = None
_cached_auth = None
_cached_kurucu = None
_cached_sesyt = None


def load_config() -> dict:
    """Genel ayarları (welcome_channel_id, exit_channel_id) önbellekten/diskten hızlıca yükler."""
    global _cached_config
    if _cached_config is not None:
        return _cached_config
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                _cached_config = json.load(f)
                return _cached_config
        except Exception:
            _cached_config = {}
            return _cached_config
    _cached_config = {}
    return _cached_config


def save_config(cfg: dict):
    """Genel ayarları kaydeder ve önbelleği günceller."""
    global _cached_config
    _cached_config = cfg
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def load_authorized() -> list[int]:
    """Yetkili ID listesini önbellekten/diskten hızlıca yükler."""
    global _cached_auth
    if _cached_auth is not None:
        return _cached_auth
    if os.path.exists(AUTH_FILE):
        try:
            with open(AUTH_FILE, "r", encoding="utf-8") as f:
                _cached_auth = json.load(f)
                return _cached_auth
        except Exception:
            _cached_auth = []
            return _cached_auth
    _cached_auth = []
    return _cached_auth


def save_authorized(ids: list[int]):
    """Yetkili ID listesini kaydeder ve önbelleği günceller."""
    global _cached_auth
    _cached_auth = ids
    with open(AUTH_FILE, "w", encoding="utf-8") as f:
        json.dump(ids, f, indent=2)


def load_kurucu() -> list[int]:
    """Kurucu ID listesini önbellekten/diskten hızlıca yükler."""
    global _cached_kurucu
    if _cached_kurucu is not None:
        return _cached_kurucu
    if os.path.exists(KURUCU_FILE):
        try:
            with open(KURUCU_FILE, "r", encoding="utf-8") as f:
                _cached_kurucu = json.load(f)
                return _cached_kurucu
        except Exception:
            _cached_kurucu = []
            return _cached_kurucu
    _cached_kurucu = []
    return _cached_kurucu


def save_kurucu(ids: list[int]):
    """Kurucu ID listesini kaydeder ve önbelleği günceller."""
    global _cached_kurucu
    _cached_kurucu = ids
    with open(KURUCU_FILE, "w", encoding="utf-8") as f:
        json.dump(ids, f, indent=2)


def load_sesyt() -> list[int]:
    """Ses yetkilisi (.sesyt) ID listesini önbellekten/diskten hızlıca yükler."""
    global _cached_sesyt
    if _cached_sesyt is not None:
        return _cached_sesyt
    if os.path.exists(SESYT_FILE):
        try:
            with open(SESYT_FILE, "r", encoding="utf-8") as f:
                _cached_sesyt = json.load(f)
                return _cached_sesyt
        except Exception:
            _cached_sesyt = []
            return _cached_sesyt
    _cached_sesyt = []
    return _cached_sesyt


def save_sesyt(ids: list[int]):
    """Ses yetkilisi ID listesini kaydeder ve önbelleği günceller."""
    global _cached_sesyt
    _cached_sesyt = ids
    with open(SESYT_FILE, "w", encoding="utf-8") as f:
        json.dump(ids, f, indent=2)


def is_allah(user_id: int) -> bool:
    """Allah mı?"""
    return user_id == ALLAH_ID


def is_kurucu(user_id: int) -> bool:
    """Kurucu mu? (Allah dahil)"""
    if is_allah(user_id):
        return True
    return user_id in load_kurucu()


def is_full_authorized(user_id: int) -> bool:
    """Tam yetkili mi? (Allah + Kurucu + .yt)"""
    if is_allah(user_id) or is_kurucu(user_id):
        return True
    return user_id in load_authorized()


def is_sesyt(user_id: int) -> bool:
    """Ses yetkisi var mı? (Allah + Kurucu + .yt + .sesyt)"""
    if is_full_authorized(user_id):
        return True
    return user_id in load_sesyt()


def is_authorized(user_id: int) -> bool:
    """Herhangi bir yetkisi var mı?"""
    return is_sesyt(user_id)


def member_has_perm(member: discord.Member) -> bool:
    """Üyenin botta veya sunucuda herhangi bir yetkisi/rolü var mı?"""
    if is_authorized(member.id) or member.guild_permissions.administrator or member.guild_permissions.manage_guild or member.guild_permissions.manage_roles or member.guild_permissions.ban_members or member.guild_permissions.kick_members or member.guild_permissions.manage_channels:
        return True
    # Default @everyone rolü haricinde özel bir rolü var mı? (Kayıtsız hariç)
    special_roles = [r for r in member.roles if r != member.guild.default_role and r.id != UNREGISTERED_ROLE_ID]
    return len(special_roles) > 0


# Gerekli bot yetkileri (Intents)
intents = discord.Intents.default()
intents.members = True          # Üye katılma/ayrılma için ZORUNLU
intents.message_content = True  # Mesaj okuma için

bot = commands.Bot(command_prefix=[".", "!"], intents=intents)


# ──────────────────────────────────────────────
# YARDIMCI FONKSİYONLAR
# ──────────────────────────────────────────────

def create_welcome_embed(member: discord.Member) -> discord.Embed:
    """Sol şeritsiz sade katıldı embed'i."""
    embed = discord.Embed(
        description=f"{member.mention} sunucuya katıldı",
        color=0x242429
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text=f"ID: {member.id}")
    return embed


def parse_member_id_from_embed(embed: discord.Embed):
    """Welcome embed'inden hedef üye ID'sini çözer."""
    if embed.footer and embed.footer.text and "ID:" in embed.footer.text:
        try:
            return int(embed.footer.text.replace("ID:", "").strip())
        except ValueError:
            pass
    if embed.description:
        match = re.search(r"<@!?(\d+)>", embed.description)
        if match:
            return int(match.group(1))
    return None


async def register_member(guild: discord.Guild, target_member: discord.Member, registrar_id: int):
    """Kayıtsız rolünü alır, kayıtlı rolü varsa verir."""
    unreg_role = guild.get_role(UNREGISTERED_ROLE_ID)
    roles_to_remove = [unreg_role] if unreg_role and unreg_role in target_member.roles else []

    roles_to_add = []
    cfg = load_config()
    reg_role_id = cfg.get("registered_role_id") or REGISTERED_ROLE_ID
    if reg_role_id:
        try:
            reg_role = guild.get_role(int(reg_role_id))
        except (TypeError, ValueError):
            reg_role = None
        if reg_role and reg_role not in target_member.roles:
            roles_to_add.append(reg_role)

    if not roles_to_remove and not roles_to_add:
        return False, "Bu üye zaten kayıtlı."

    reason = f"{registrar_id} tarafından kayıt edildi."
    if roles_to_remove:
        await target_member.remove_roles(*roles_to_remove, reason=reason)
    if roles_to_add:
        await target_member.add_roles(*roles_to_add, reason=reason)
    return True, "Kayıt tamamlandı."


class KayitView(discord.ui.View):
    """Hoş geldin mesajının altına kalıcı kayıt butonu."""

    def __init__(self, *, disabled: bool = False):
        super().__init__(timeout=None)
        if disabled:
            for item in self.children:
                item.disabled = True

    @discord.ui.button(
        label="⠀⠀⠀",
        style=discord.ButtonStyle.success,
        custom_id="welcome_kayit_btn",
    )
    async def kayit_et(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_full_authorized(interaction.user.id):
            if not interaction.response.is_done():
                try:
                    await interaction.response.defer()
                except (discord.NotFound, discord.InteractionResponded):
                    pass
            return

        guild = interaction.guild
        if not guild or not interaction.message or not interaction.message.embeds:
            await interaction.response.send_message("❌ Kayıt bilgisi bulunamadı.", ephemeral=True)
            return

        target_id = parse_member_id_from_embed(interaction.message.embeds[0])
        if not target_id:
            await interaction.response.send_message("❌ Hedef üye çözülemedi.", ephemeral=True)
            return

        target_member = guild.get_member(target_id)
        if not target_member:
            try:
                target_member = await guild.fetch_member(target_id)
            except Exception:
                await interaction.response.send_message("❌ Üye sunucuda bulunamadı.", ephemeral=True)
                return

        try:
            ok, msg = await register_member(guild, target_member, interaction.user.id)
        except Exception as e:
            print(f"⚠️ Butonla kayıt işlemi sırasında hata: {e}", flush=True)
            await interaction.response.send_message(f"❌ Kayıt sırasında hata: {e}", ephemeral=True)
            return

        if not ok:
            await interaction.response.send_message(f"⚠️ {msg}", ephemeral=True)
            return

        button.disabled = True
        embed_log = discord.Embed(
            title="📝 Üye Kayıt Edildi",
            description=(
                f"**Kayıt Edilen:** {target_member.mention} (`{target_member.id}`)\n"
                f"**Kayıt Eden Yetkili:** {interaction.user.mention}\n"
                f"**Kaldırılan Rol:** Kayıtsız Rolü (`{UNREGISTERED_ROLE_ID}`)"
            ),
            color=0x57F287,
            timestamp=discord.utils.utcnow(),
        )
        embed_log.set_thumbnail(url=target_member.display_avatar.url)
        await send_audit_log(guild, embed_log)
        print(
            f"✅ {target_member.name} ({target_member.id}) yetkili ({interaction.user.id}) butonuyla kayıt edildi.",
            flush=True,
        )
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(
            f"✅ {target_member.mention} kayıt edildi.",
            ephemeral=True,
        )


def create_exit_embed(member: discord.Member) -> discord.Embed:
    """Sol şeritsiz sade ayrıldı embed'i."""
    embed = discord.Embed(
        description=f"{member.mention} sunucudan ayrıldı",
        color=0x242429
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    return embed


async def lock_and_grant_channel(channel: discord.TextChannel):
    """
    Welcome Kanalı:
    Kanalı kilitler (@everyone ve yetkililer dahil kimse mesaj yazamaz, butonla kayıt ve bot mesajı için temiz kalır),
    Herkes sadece görebilir ve okuyabilir.
    """
    auth_ids = set(load_authorized()) | set(load_kurucu())
    auth_ids.add(ALLAH_ID)

    everyone_overwrite = channel.overwrites_for(channel.guild.default_role)
    everyone_overwrite.send_messages = False
    everyone_overwrite.add_reactions = False
    everyone_overwrite.view_channel = True  # Herkes gelen/gideni görebilir ama yazamaz
    try:
        await channel.set_permissions(channel.guild.default_role, overwrite=everyone_overwrite)
    except Exception as e:
        print(f"⚠️ @everyone kilitlenemedi: {e}", flush=True)

    for uid in auth_ids:
        member = channel.guild.get_member(uid)
        if member:
            overwrite = channel.overwrites_for(member)
            overwrite.view_channel = True
            # Welcome dışı her yere yazabilsinler dediği için welcome'da mesaj yazma kapalı
            overwrite.send_messages = False
            overwrite.read_message_history = True
            # Welcome kanalında SADECE ALLAH mesaj silebilir
            overwrite.manage_messages = is_allah(uid)
            try:
                await channel.set_permissions(member, overwrite=overwrite)
            except Exception as e:
                print(f"⚠️ Kanal yetkisi verilemedi ({channel.name} -> {member.name}): {e}", flush=True)


async def lock_and_grant_private_channel(channel: discord.TextChannel):
    """
    ÖZEL Kanallar (Exit / Log vb.):
    @everyone için kanalı GİZLER (view_channel = False).
    Sadece Allah, Kurucu ve Yetkililere görünür ve mesaj yazma/okuma hakkı verir.
    """
    auth_ids = set(load_authorized()) | set(load_kurucu())
    auth_ids.add(ALLAH_ID)

    # 1. @everyone için tamamen görünmez yap
    everyone_overwrite = channel.overwrites_for(channel.guild.default_role)
    everyone_overwrite.view_channel = False
    everyone_overwrite.send_messages = False
    everyone_overwrite.read_message_history = False
    try:
        await channel.set_permissions(channel.guild.default_role, overwrite=everyone_overwrite)
    except Exception as e:
        print(f"⚠️ Özel kanalda @everyone kısıtlanamadı: {e}", flush=True)

    # 2. Yetkili olanlara tam erişim (görme + okuma + yazma) ver
    cfg = load_config()
    exit_id = cfg.get("exit_channel_id")
    is_exit_channel = (exit_id and str(channel.id) == str(exit_id))
    ch_name_lower = channel.name.lower()
    can_delete_msg_names = ("chat", "sohbet", "genel", "uwu")

    for uid in auth_ids:
        member = channel.guild.get_member(uid)
        if member:
            overwrite = channel.overwrites_for(member)
            overwrite.view_channel = True
            overwrite.send_messages = True
            overwrite.read_message_history = True

            # Exit kanalında SADECE ALLAH mesaj silebilir
            if is_exit_channel:
                overwrite.manage_messages = is_allah(uid)
            elif is_allah(uid) or is_kurucu(uid):
                overwrite.manage_messages = True
            else:
                overwrite.manage_messages = any(k in ch_name_lower for k in can_delete_msg_names)

            try:
                await channel.set_permissions(member, overwrite=overwrite)
            except Exception as e:
                print(f"⚠️ Özel kanal yetkisi verilemedi ({channel.name} -> {member.name}): {e}", flush=True)


async def configure_unregistered_role_permissions(guild: discord.Guild):
    """
    Kayıtsız Rolü (1544413431409410058) Kanal İzinleri:
    - Sadece #welcome ve #rules kanallarını görebilir ve okuyabilir.
    - Diğer TÜM kanallar (metin, ses, kategoriler) kayıtsız rolüne tamamen gizlenir.
    """
    unreg_role = guild.get_role(UNREGISTERED_ROLE_ID)
    if not unreg_role:
        return

    cfg = load_config()
    allowed_channel_ids = set()
    w_id = cfg.get("welcome_channel_id")
    r_id = cfg.get("rules_channel_id")
    if w_id:
        try: allowed_channel_ids.add(int(w_id))
        except ValueError: pass
    if r_id:
        try: allowed_channel_ids.add(int(r_id))
        except ValueError: pass

    # 1. Kategoriler için izinler (Kayıtsızlar kategoriyi görebilir ama içindeki kilitli kanalları göremez)
    for category in guild.categories:
        try:
            cat_over = category.overwrites_for(unreg_role)
            cat_over.view_channel = True
            await category.set_permissions(unreg_role, overwrite=cat_over)
        except Exception:
            pass

    # 2. Metin kanalları için izinler
    for channel in guild.text_channels:
        try:
            over = channel.overwrites_for(unreg_role)
            if channel.id in allowed_channel_ids:
                over.view_channel = True
                over.read_message_history = True
                over.send_messages = False
                over.add_reactions = False
            else:
                over.view_channel = False
                over.send_messages = False
            await channel.set_permissions(unreg_role, overwrite=over)
        except Exception:
            pass

    # 3. Ses kanalları için izinler:
    # İçinde üye olan ses kanalını kayıtsızlar görebilir (view_channel=True) ama giremez (connect=False)
    # Boş olan ses kanallarını kayıtsızlar kesinlikle göremez (view_channel=False)
    for channel in guild.voice_channels:
        try:
            over = channel.overwrites_for(unreg_role)
            if len(channel.members) > 0:
                over.view_channel = True
                over.connect = False
            else:
                over.view_channel = False
                over.connect = False
            await channel.set_permissions(unreg_role, overwrite=over)
        except Exception:
            pass


async def configure_registered_role_permissions(guild: discord.Guild):
    """
    Kayıtlı Rolü (1544413431409410058) Kanal İzinleri:
    - Sunucudaki genel kategori, metin ve ses kanallarını görebilir ve yazabilir/bağlanabilir.
    - Sadece özel yetkili kanalları (exit, log) gizli kalır.
    - Welcome kanalı mesaj yazmaya kilitlidir ama okunabilir.
    """
    reg_role = guild.get_role(REGISTERED_ROLE_ID)
    if not reg_role:
        return

    cfg = load_config()
    private_channel_ids = set()
    e_id = cfg.get("exit_channel_id")
    l_id = cfg.get("log_channel_id")
    w_id = cfg.get("welcome_channel_id")
    if e_id:
        try: private_channel_ids.add(int(e_id))
        except ValueError: pass
    if l_id:
        try: private_channel_ids.add(int(l_id))
        except ValueError: pass

    # 1. Kategoriler için izinler
    for category in guild.categories:
        try:
            cat_over = category.overwrites_for(reg_role)
            cat_over.view_channel = True
            await category.set_permissions(reg_role, overwrite=cat_over)
        except Exception:
            pass

    # 2. Metin kanalları için izinler
    for channel in guild.text_channels:
        try:
            over = channel.overwrites_for(reg_role)
            if channel.id in private_channel_ids:
                over.view_channel = False
                over.send_messages = False
            elif w_id and str(channel.id) == str(w_id):
                over.view_channel = True
                over.read_message_history = True
                over.send_messages = False
            else:
                over.view_channel = True
                over.read_message_history = True
                over.send_messages = True
            await channel.set_permissions(reg_role, overwrite=over)
        except Exception:
            pass

    # 3. Ses kanalları için izinler
    for channel in guild.voice_channels:
        try:
            over = channel.overwrites_for(reg_role)
            over.view_channel = True
            over.connect = True
            over.speak = True
            await channel.set_permissions(reg_role, overwrite=over)
        except Exception:
            pass


PROTECTED_CATEGORY_ID = 1021779804023947366  # Dokunulmaz Kategori ID'si


async def sync_voice_permissions(guild: discord.Guild):
    """
    Ses ve metin kanallarını tarar:
    - Allah ve Kurucular tüm metin kanallarında mesaj silme (manage_messages) yetkisine sahiptir.
    - Yetkililer (.yt) sadece 'chat', 'sohbet', 'genel' ve 'uwu' kanallarında mesaj silebilir (diğerlerinde sadece yazabilir/okuyabilir).
    - .sesyt yetkililerine ses kanallarında mute, deafen, move (bağlantı kesme/taşıma) izinleri verir.
    - Welcome kanalı mesaj yazmaya kilitli kalır.
    """
    await configure_unregistered_role_permissions(guild)
    await configure_registered_role_permissions(guild)

    full_auth_ids = set(load_authorized()) | set(load_kurucu())
    full_auth_ids.add(ALLAH_ID)
    sesyt_ids = set(load_sesyt())

    all_voice_auths = full_auth_ids | sesyt_ids

    # Kategorileri kontrol et (Sadece tam yetkililer kategori üzerinden ses açabilir)
    for category in guild.categories:
        is_protected = (category.id == PROTECTED_CATEGORY_ID)
        for uid in full_auth_ids:
            if is_allah(uid) or is_kurucu(uid):
                continue
            member = guild.get_member(uid)
            if member:
                cat_over = category.overwrites_for(member)
                old_pair = cat_over.pair()
                if is_protected:
                    cat_over.manage_channels = False
                    cat_over.manage_permissions = False
                else:
                    cat_over.manage_channels = True
                if cat_over.pair() != old_pair:
                    try:
                        await category.set_permissions(member, overwrite=cat_over)
                    except Exception:
                        pass

    # Ses kanallarını denetle
    for channel in guild.voice_channels:
        is_in_protected = (channel.category_id == PROTECTED_CATEGORY_ID)
        for uid in all_voice_auths:
            member = guild.get_member(uid)
            if member:
                overwrite = channel.overwrites_for(member)
                old_pair = overwrite.pair()
                # .sesyt ve .yt için mute, deafen, move (bağlantı kesme)
                overwrite.mute_members = True
                overwrite.deafen_members = True
                overwrite.move_members = True
                
                # Sadece full_auth (.yt) olanlar kanal yönetebilir (eğer korumalı alanda değilse)
                if uid in full_auth_ids and not is_in_protected:
                    overwrite.manage_channels = True
                else:
                    overwrite.manage_channels = False

                if is_allah(uid) or is_kurucu(uid):
                    overwrite.manage_channels = True

                if overwrite.pair() != old_pair:
                    try:
                        await channel.set_permissions(member, overwrite=overwrite)
                    except Exception as e:
                        print(f"⚠️ Ses izni verilemedi ({channel.name} -> {member.name}): {e}", flush=True)

    # Metin kanallarını denetle
    cfg = load_config()
    welcome_id = cfg.get("welcome_channel_id")
    can_delete_names = ("chat", "sohbet", "genel", "uwu")
    for channel in guild.text_channels:
        if welcome_id and str(channel.id) == str(welcome_id):
            continue  # Welcome kanalı lock_and_grant_channel tarafından kilitli kalır
        ch_name = channel.name.lower()
        for uid in full_auth_ids:
            member = guild.get_member(uid)
            if member:
                overwrite = channel.overwrites_for(member)
                old_pair = overwrite.pair()
                overwrite.view_channel = True
                overwrite.send_messages = True
                overwrite.read_message_history = True
                
                # Kurucular ve Allah her yerde mesaj silebilir ve @everyone atabilir; Yetkililer sadece chat ve uwu kanallarında silebilir
                if is_allah(uid) or is_kurucu(uid):
                    overwrite.manage_messages = True
                    overwrite.mention_everyone = True
                else:
                    overwrite.manage_messages = any(k in ch_name for k in can_delete_names)
                    overwrite.mention_everyone = False

                if overwrite.pair() != old_pair:
                    try:
                        await channel.set_permissions(member, overwrite=overwrite)
                    except Exception:
                        pass


# ──────────────────────────────────────────────
# OLAYLAR (EVENTS)
# ──────────────────────────────────────────────

# Orijinal ses kanalları veritabanı (ID -> {name, category_id, position, bitrate, user_limit, ...})
SNAPSHOT_FILE = os.path.join(BASE_DIR, "channels_snapshot.json")

# İsim değişiklikleri için bekleyen kanallar: {channel_id: {"original_name": str, "target_time": float, "pending_restore": bool}}
pending_name_reverts = {}

# Yeni oluşturulan geçici kanallar için takip: {channel_id: {"created_at": float, "is_temp": True}}
temp_channels = {}


def load_snapshots() -> dict:
    if os.path.exists(SNAPSHOT_FILE):
        try:
            with open(SNAPSHOT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_snapshots(data: dict):
    with open(SNAPSHOT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def record_voice_snapshot(guild: discord.Guild, overwrite: bool = False):
    """
    Mevcut tüm ses kanallarını ve korumalı kategorideki metin kanallarını kaydeder.
    overwrite=True olduğunda eski ses kanallarını silip sunucudaki güncel ses kanallarını hafızaya kazır.
    """
    data = {} if overwrite else load_snapshots()
    
    if overwrite:
        # Eski text/rules/log kanallarını koru, ses kanallarını sıfırdan kaydet
        old_data = load_snapshots()
        for k, v in old_data.items():
            if v.get("type") == "text":
                data[k] = v

    for ch in guild.channels:
        # Geçici kanalları snapshot'a alma
        if ch.id in temp_channels:
            continue
        sid = str(ch.id)
        if overwrite or sid not in data:
            data[sid] = {
                "name": ch.name,
                "type": "voice" if isinstance(ch, discord.VoiceChannel) else "text",
                "guild_id": ch.guild.id,
                "category_id": ch.category_id,
                "position": ch.position,
                "bitrate": getattr(ch, "bitrate", 64000) if isinstance(ch, discord.VoiceChannel) else 0,
                "user_limit": getattr(ch, "user_limit", 0) if isinstance(ch, discord.VoiceChannel) else 0
            }
    save_snapshots(data)


def handle_channel_name_change(channel: discord.VoiceChannel, original_name: str):
    """
    Kanalın ismi değiştiğinde:
    Kanalda kimse yoksa anında eski adına döndürür,
    biri varsa sesten çıktığı anda döndürmek üzere kuyruğa alır.
    """
    if len(channel.members) == 0:
        asyncio.create_task(do_revert_channel_name(channel.id, original_name))
    else:
        pending_name_reverts[channel.id] = original_name
        print(f"⏳ [Kanal Koruma] '{channel.name}' ismi değişti. Seste üyeler var, sesten çıktıkları anda '{original_name}' adına geri döndürülecek.", flush=True)


async def do_revert_channel_name(channel_id: int, original_name: str):
    """Kanal adını orijinal adına döndürür."""
    try:
        channel = bot.get_channel(channel_id)
        if channel and isinstance(channel, discord.VoiceChannel):
            if channel.name != original_name:
                await channel.edit(name=original_name)
                print(f"🔄 [Kanal Koruma] {channel_id} kanalı boş olduğu için hemen '{original_name}' adına geri döndürüldü.", flush=True)
        pending_name_reverts.pop(channel_id, None)
    except Exception as e:
        print(f"⚠️ Kanal adı geri döndürülemedi: {e}", flush=True)


async def check_and_delete_temp_channel(channel_id: int, delay_seconds: int = 300):
    """5 dakika sonra kanalda kimse yoksa siler, varsa çıkana kadar bekler."""
    try:
        await asyncio.sleep(delay_seconds)
        channel = bot.get_channel(channel_id)
        if channel and isinstance(channel, discord.VoiceChannel):
            if len(channel.members) == 0:
                await channel.delete(reason="5 dakika içinde sese kimse girmediği için otomatik silindi.")
                temp_channels.pop(channel_id, None)
                print(f"🗑️ [Geçici Kanal] {channel.name} 5 dakika boş kaldığı için silindi.", flush=True)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"⚠️ Geçici kanal silinemedi: {e}", flush=True)


async def restore_server_integrity(guild: discord.Guild):
    """
    VDS kapansa veya bot offline kalsa bile bot açıldığında veya periyodik olarak:
    1. Tüm ses kanallarını snapshot'a kaydeder ve yetkileri senkronize eder.
    2. Ayarlanmış Hoş Geldin ve Çıkış kanallarını kilitler, sadece yetkililere açık tutar.
    3. Silinen veya bozulan kanal izinlerini otomatik onarır.
    """
    print(f"🛡️ {guild.name} için sunucu koruma ve otomatik onarım başlatıldı...", flush=True)

    # 1. Ses kanallarını snapshot al & yetkilendir
    record_voice_snapshot(guild)
    await sync_voice_permissions(guild)

    # 2. Hoş geldin ve Çıkış kanallarını onar & kitle
    cfg = load_config()
    w_id = cfg.get("welcome_channel_id")
    e_id = cfg.get("exit_channel_id")

    if w_id:
        try:
            w_ch = guild.get_channel(int(w_id))
            if w_ch and isinstance(w_ch, discord.TextChannel):
                await lock_and_grant_channel(w_ch)
        except Exception as e:
            print(f"⚠️ Welcome kanalı onarılamadı: {e}", flush=True)

    if e_id:
        try:
            e_ch = guild.get_channel(int(e_id))
            if e_ch and isinstance(e_ch, discord.TextChannel):
                await lock_and_grant_private_channel(e_ch)
        except Exception as e:
            print(f"⚠️ Exit kanalı onarılamadı: {e}", flush=True)

    # 3. Denetim Kaydı (Log) kanalını onar & yetkililere özel tut
    l_id = cfg.get("log_channel_id")
    if l_id:
        try:
            l_ch = guild.get_channel(int(l_id))
            if l_ch and isinstance(l_ch, discord.TextChannel):
                await lock_and_grant_private_channel(l_ch)
        except Exception as e:
            print(f"⚠️ Log kanalı onarılamadı: {e}", flush=True)

    # 4. Kayıtsız rol izinlerini EN SON uygula (lock_and_grant_channel'ın üstüne yazmasın diye)
    await configure_unregistered_role_permissions(guild)

    # 5. Bot kapalıyken (AFK) sunucuya girenleri kontrol et:
    # Kayıtlı rolü olmayan ve Kayıtsız rolü de verilmemiş üyelere Kayıtsız rolü verip welcome mesajı at
    await check_and_fix_unregistered_members(guild)

    print(f"✅ {guild.name} sunucusundaki tüm izinler ve ayarlar otomatik olarak onarıldı ve eşitlendi.", flush=True)


async def check_and_fix_unregistered_members(guild: discord.Guild):
    """
    Kayıt Kontrol & AFK Telafi:
    - Sunucuda hiçbir yetkisi veya özel rolü olmayan üyeleri Kayıtsız Rolü'ne (1544443560571576380) geçirir.
    - Sadece kayıtsız rolü eksik olanlara rol verip tek seferlik welcome butonu atar.
    """
    unreg_role = guild.get_role(UNREGISTERED_ROLE_ID)
    if not unreg_role:
        return

    cfg = load_config()
    reg_role_id = cfg.get("registered_role_id") or REGISTERED_ROLE_ID
    reg_role = guild.get_role(int(reg_role_id)) if reg_role_id else None

    # Welcome kanalı tespiti
    w_id = cfg.get("welcome_channel_id")
    welcome_channel = guild.get_channel(int(w_id)) if w_id else None
    if not welcome_channel or not isinstance(welcome_channel, discord.TextChannel):
        welcome_channel = guild.system_channel

    for member in guild.members:
        if member.bot:
            continue
        # Üzerinde yetki veya özel rol olanları KESİNLİKLE atla
        if member_has_perm(member):
            continue

        has_reg_role = (reg_role and reg_role in member.roles)
        has_unreg_role = (unreg_role in member.roles)

        # 1. Eğer üzerinde kayıtlı rolü varsa kaldır
        if has_reg_role:
            try:
                await member.remove_roles(reg_role, reason="Yetkisiz üye: Kayıtlı rolü alındı.")
            except Exception as e:
                print(f"⚠️ Kayıtlı rolü alınamadı ({member.name}): {e}", flush=True)

        # 2. Kayıtsız rolü yoksa ver ve welcome mesajı gönder
        if not has_unreg_role:
            try:
                await member.add_roles(unreg_role, reason="Yetkisi olmayan üyeye Kayıtsız Rolü verildi.")
                print(f"🔒 [Kayıtsız Sıfırlama] {member.name} ({member.id}) kullanıcısına Kayıtsız Rolü verildi.", flush=True)
            except Exception as e:
                print(f"⚠️ Kayıtsız rolü verilemedi ({member.name}): {e}", flush=True)

            # Welcome kanalına kayıt butonu mesajı gönder
            if welcome_channel:
                try:
                    embed = create_welcome_embed(member)
                    view = KayitView()
                    await welcome_channel.send(embed=embed, view=view)
                    print(f"👋 [Kayıtsız Sıfırlama] {member.name} ({member.id}) için welcome kayıt butonu gönderildi.", flush=True)
                except Exception as e:
                    print(f"⚠️ Welcome mesajı gönderilemedi ({member.name}): {e}", flush=True)


DYNAMIC_SONG_NAMES = [
    "01000110010001100100000100100001",
    "01001101010010010100000100101010",
    "01000100010100000101001100101011",
    "01010011010010010100111000101110",
    "00101111010011010100100101000001",
    "01101001001111000010111100110011",
    "01010010010001010101001100100001",
    "01001011010001000100000100101011",
    "01000111001100100100011100101110",
    "01010101010100100100110000111111",
    "00101110011000100110000101110100"
]

status_song_index = 0

from discord.ext import tasks

@tasks.loop(seconds=17)
async def rotate_status_loop():
    """Her 17 saniyede bir botun durumunu (activity) şarkı isimleriyle günceller."""
    global status_song_index
    if not bot.is_ready():
        return
    try:
        current_name = DYNAMIC_SONG_NAMES[status_song_index % len(DYNAMIC_SONG_NAMES)]
        status_song_index += 1
        await bot.change_presence(
            activity=discord.CustomActivity(name=current_name)
        )
    except Exception as e:
        print(f"⚠️ Durum güncellenemedi: {e}", flush=True)


@tasks.loop(minutes=10)
async def auto_repair_loop():
    """Her 10 dakikada bir arka planda sessizce sunucu ayarlarını kontrol edip onarır."""
    for guild in bot.guilds:
        await restore_server_integrity(guild)


STAY_VOICE_CHANNEL_ID = 1532596503447867434  # Botun 7/24 kalacağı ses kanalı

async def ensure_voice_connection():
    """Bot hiçbir seste değilse 7/24 kalacağı odaya bağlanır. Asla odayı zorla değiştirmez."""
    try:
        channel = bot.get_channel(STAY_VOICE_CHANNEL_ID)
        if channel and isinstance(channel, discord.VoiceChannel):
            guild = channel.guild
            vc = guild.voice_client
            
            # Bot şu an herhangi bir ses kanalına bağlıysa (hangi kanal olursa olsun) ASLA taşıma/dokunma!
            if vc and vc.is_connected():
                return

            # Bot sesten tamamen düştüyse veya hiç bağlanmadıysa odaya gir
            await channel.connect(self_deaf=True, self_mute=False)
            print(f"🔊 [Ses Odası] Bot #{channel.name} (`{channel.id}`) kanalına bağlandı.", flush=True)
    except Exception as e:
        print(f"⚠️ Ses kanalına bağlanırken hata: {e}", flush=True)


@tasks.loop(seconds=30)
async def voice_keepalive_loop():
    """Bot sesten tamamen düşerse kontrol edip odaya sokar."""
    if bot.is_ready():
        await ensure_voice_connection()


@bot.event
async def on_ready():
    bot.add_view(KayitView())
    print(f"✅ Bot başarıyla giriş yaptı: {bot.user} (ID: {bot.user.id})", flush=True)
    print(f"👑 Sahip ID: {OWNER_ID}", flush=True)

    if bot.guilds:
        print(f"🏰 Botun bulunduğu sunucular ({len(bot.guilds)} adet):", flush=True)
        for guild in bot.guilds:
            print(f" - {guild.name} (ID: {guild.id})", flush=True)
            bot.tree.copy_global_to(guild=guild)
            await bot.tree.sync(guild=guild)
            # VDS yeniden açıldığında tüm sunucu ayarlarını ve izinlerini anında otomatik düzelt
            await restore_server_integrity(guild)
        print("⚡ Slash (/) komutları, ses yetkileri ve kanal kilitleri anında eşitlendi.", flush=True)
    else:
        print("⚠️ Bot henüz hiçbir sunucuya eklenmemiş!", flush=True)

    # 17 saniyede bir dönen durum döngüsünü başlat
    if not rotate_status_loop.is_running():
        rotate_status_loop.start()

    # Otomatik periyodik onarım döngüsünü başlat
    if not auto_repair_loop.is_running():
        auto_repair_loop.start()

    # Belirlenen ses kanalına bağlan ve 7/24 seste kalmasını sağla
    await ensure_voice_connection()
    if not voice_keepalive_loop.is_running():
        voice_keepalive_loop.start()

    try:
        synced = await bot.tree.sync()
        print(f"🔄 {len(synced)} adet genel eğik çizgi (/) komutu senkronize edildi.", flush=True)
    except Exception as e:
        print(f"Komutlar senkronize edilirken hata: {e}", flush=True)


@bot.event
async def on_guild_channel_update(before: discord.abc.GuildChannel, after: discord.abc.GuildChannel):
    """Ses kanalı ismi değişirse seste kimse yoksa anında, varsa sesten çıktığı an eski haline döndür."""
    if isinstance(after, discord.VoiceChannel) and before.name != after.name:
        snapshots = load_snapshots()
        orig = snapshots.get(str(after.id))
        if orig:
            orig_name = orig["name"]
            if after.name != orig_name:
                handle_channel_name_change(after, orig_name)


@bot.event
async def on_guild_channel_delete(channel: discord.abc.GuildChannel):
    """
    1. Eğer kanalı Allah (ALLAH_ID) sildiyse ASLA geri açılmaz, snapshot'tan kalıcı olarak kaldırılır.
    2. Yetkililer veya başkası orijinal bir ses kanalını veya korunan kategorideki kanalı silerse anında geri açılır.
    """
    await asyncio.sleep(1)
    deleter_id = None
    try:
        async for entry in channel.guild.audit_logs(limit=5, action=discord.AuditLogAction.channel_delete):
            if entry.target and entry.target.id == channel.id:
                deleter_id = entry.user.id
                break
    except Exception as e:
        print(f"⚠️ Audit log channel_delete okunamadı: {e}", flush=True)

    snapshots = load_snapshots()

    # 👑 ALLAH SİLDİYSE VEYA DÜZENLEME MODU AKTİFSE KALICI OLARAK SİLİNSİN, GERİ AÇILMASIN!
    cfg = load_config()
    edit_mode_active = cfg.get("edit_mode", False)

    if is_allah(deleter_id) or (edit_mode_active and isinstance(channel, discord.VoiceChannel)):
        snapshots.pop(str(channel.id), None)
        temp_channels.pop(channel.id, None)
        save_snapshots(snapshots)
        print(f"🔧 [Düzenleme Modu / Allah Silme] '{channel.name}' ses kanalı silindi ve geri açılmadı.", flush=True)
        return

    # 📜 RULES (KURALLAR) KANALI KORUMASI: Kurucu dahil Allah hariç KİMSE silemez!
    cfg = load_config()
    rules_id = cfg.get("rules_channel_id")
    if rules_id and str(channel.id) == str(rules_id):
        guild = channel.guild
        try:
            new_rules_ch = await guild.create_text_channel(
                name=channel.name,
                category=channel.category,
                position=channel.position,
                reason="📜 [Kural Koruması] Kurallar kanalı silindiği için otomatik yeniden oluşturuldu (Sadece Allah silebilir)."
            )
            cfg["rules_channel_id"] = str(new_rules_ch.id)
            save_config(cfg)
            await configure_unregistered_role_permissions(guild)
            print(f"🚨 [Rules Koruma] Kurallar kanalı '{channel.name}' yetkili ({deleter_id}) tarafından silinmeye çalışıldı! Anında geri açıldı (Yeni ID: {new_rules_ch.id}).", flush=True)
            
            # Denetim logu bildirimi
            deleter_user = guild.get_member(deleter_id)
            deleter_str = deleter_user.mention if deleter_user else f"`{deleter_id}`"
            log_embed = discord.Embed(
                title="🛡️ Korunan Kurallar Kanalı Kurtarıldı",
                description=(
                    f"**Kanal:** #{new_rules_ch.name} (`{new_rules_ch.id}`)\n"
                    f"**Silmeye Çalışan:** {deleter_str}\n"
                    f"**Sonuç:** Kurallar kanalı silinemez! Anında geri oluşturuldu."
                ),
                color=0xFF0000,
                timestamp=discord.utils.utcnow()
            )
            await send_audit_log(guild, log_embed)
            return
        except Exception as e:
            print(f"❌ Rules kanalı geri açılamadı: {e}", flush=True)

    orig = snapshots.get(str(channel.id))

    # Korunan kategorideki kanalların veya orijinal ses kanallarının geri açılması
    if (isinstance(channel, discord.VoiceChannel) or channel.category_id == PROTECTED_CATEGORY_ID) and orig:
        # Geçici bir kanalsa geri açma
        if channel.id in temp_channels:
            temp_channels.pop(channel.id, None)
            return

        guild = channel.guild
        category = guild.get_channel(orig.get("category_id")) if orig.get("category_id") else None
        try:
            if isinstance(channel, discord.VoiceChannel):
                new_ch = await guild.create_voice_channel(
                    name=orig["name"],
                    category=category,
                    bitrate=orig.get("bitrate", 64000),
                    user_limit=orig.get("user_limit", 0),
                    position=orig.get("position", channel.position),
                    reason="Silinen orijinal kanal otomatik geri oluşturuldu."
                )
            else:
                new_ch = await guild.create_text_channel(
                    name=orig["name"],
                    category=category,
                    position=orig.get("position", channel.position),
                    reason="Korumalı kategoride silinen metin kanalı otomatik geri oluşturuldu."
                )

            # Snapshot'ı yeni ID ile güncelle
            snapshots.pop(str(channel.id), None)
            snapshots[str(new_ch.id)] = {
                "name": new_ch.name,
                "guild_id": guild.id,
                "category_id": new_ch.category_id,
                "position": new_ch.position,
                "bitrate": getattr(new_ch, "bitrate", 64000) if isinstance(new_ch, discord.VoiceChannel) else 0,
                "user_limit": getattr(new_ch, "user_limit", 0) if isinstance(new_ch, discord.VoiceChannel) else 0
            }
            save_snapshots(snapshots)

            # Eğer silinen kanal botun bulunduğu ses kanalıysa yeni açılan kanala anında bağlan
            global STAY_VOICE_CHANNEL_ID
            if str(channel.id) == str(STAY_VOICE_CHANNEL_ID):
                STAY_VOICE_CHANNEL_ID = new_ch.id
                cfg = load_config()
                cfg["stay_voice_channel_id"] = str(new_ch.id)
                save_config(cfg)
                await ensure_voice_connection()
                print(f"🔊 [Ses Odası Koruma] Botun ses odası yeniden açıldı ve bot yeni kanala ({new_ch.name}) bağlandı.", flush=True)

            await restore_server_integrity(guild)
            print(f"🚨 [Kanal Koruma] Silinen kanal '{orig['name']}' anında yeniden oluşturuldu! (Yeni ID: {new_ch.id})", flush=True)
        except Exception as e:
            print(f"❌ Silinen kanal geri açılamadı: {e}", flush=True)


@bot.event
async def on_guild_channel_create(channel: discord.abc.GuildChannel):
    """
    1. Allah (ALLAH_ID) veya Bot tarafından açılan kanallara ASLA dokunulmaz, snapshot'a eklenir.
    2. Korumalı kategori (1021779804023947366) altında yetkililer kanal açarsa anında silinir.
    3. Yetkililer metin kanalı açarsa anında silinir.
    4. Yetkililer ses kanalı açarsa 5 dakika süre tanınır, boş kalırsa veya sesten çıkılınca silinir.
    """
    await asyncio.sleep(1)  # Audit logun Discord'a düşmesi için 1 sn bekle
    creator_id = None
    try:
        async for entry in channel.guild.audit_logs(limit=5, action=discord.AuditLogAction.channel_create):
            if entry.target and entry.target.id == channel.id:
                creator_id = entry.user.id
                break
    except Exception as e:
        print(f"⚠️ Audit log channel_create okunamadı: {e}", flush=True)

    # 👑 ALLAH VEYA BOT İSE ASLA SİLME, KALICI SNAPSHOT'A KAYDET!
    if is_allah(creator_id) or (creator_id == bot.user.id):
        snapshots = load_snapshots()
        snapshots[str(channel.id)] = {
            "name": channel.name,
            "guild_id": channel.guild.id,
            "category_id": channel.category_id,
            "position": channel.position,
            "bitrate": getattr(channel, "bitrate", 64000) if isinstance(channel, discord.VoiceChannel) else 0,
            "user_limit": getattr(channel, "user_limit", 0) if isinstance(channel, discord.VoiceChannel) else 0
        }
        save_snapshots(snapshots)
        print(f"👑 [Allah / Bot Kanalı] '{channel.name}' kanalı açıldı ve kalıcı olarak kaydedildi. Silinmeyecek!", flush=True)
        await sync_voice_permissions(channel.guild)
        return

    snapshots = load_snapshots()

    # 1. Korunan kategori altına yetkililer yeni kanal açarsa direkt sil
    if channel.category_id == PROTECTED_CATEGORY_ID and str(channel.id) not in snapshots:
        try:
            await channel.delete(reason="1021779804023947366 korumalı kategorisinde kanal açmak yasaktır.")
            print(f"🛑 [Kategori Koruma] 1021779804023947366 kategorisinde açılan '{channel.name}' kanalı anında silindi!", flush=True)
            return
        except Exception as e:
            print(f"⚠️ Korumalı kanal silinemedi: {e}", flush=True)

    # 2. Metin kanalı açıldıysa (botun kendi kayıtlı kanalları hariç) anında sil
    if isinstance(channel, discord.TextChannel):
        cfg = load_config()
        w_id = cfg.get("welcome_channel_id")
        e_id = cfg.get("exit_channel_id")
        l_id = cfg.get("log_channel_id")
        if str(channel.id) not in (w_id, e_id, l_id) and str(channel.id) not in snapshots:
            try:
                await channel.delete(reason="Sunucuda yetkililerin metin kanalı açması engellendi.")
                print(f"🛑 [Metin Kanalı Engeli] Yeni açılan '{channel.name}' metin kanalı anında silindi!", flush=True)
                return
            except Exception as e:
                print(f"⚠️ Metin kanalı silinemedi: {e}", flush=True)

    # 3. İzinli yeni ses kanalı (yetkilinin açtığı geçici kanal)
    if isinstance(channel, discord.VoiceChannel):
        if str(channel.id) not in snapshots:
            temp_channels[channel.id] = {
                "created_at": time.time(),
                "name": channel.name
            }
            await sync_voice_permissions(channel.guild)
            asyncio.create_task(check_and_delete_temp_channel(channel.id, delay_seconds=300))
            print(f"⏳ [Yeni Ses Kanalı] '{channel.name}' oluşturuldu. 5 dakika boş kalırsa veya sesten çıkılınca silinecek.", flush=True)
    else:
        await restore_server_integrity(channel.guild)


async def send_audit_log(guild: discord.Guild, embed: discord.Embed):
    """Belirlenen gizli denetim (log) kanalına embed mesajı gönderir."""
    cfg = load_config()
    log_channel_id = cfg.get("log_channel_id")
    if not log_channel_id:
        return

    try:
        channel = guild.get_channel(int(log_channel_id))
        if channel and isinstance(channel, discord.TextChannel):
            await channel.send(embed=embed)
    except Exception as e:
        print(f"⚠️ Log gönderilemedi: {e}", flush=True)


@bot.event
async def on_member_ban(guild: discord.Guild, user: discord.User | discord.Member):
    """Bir üye banlandığında denetim kaydından yakalayıp loglar."""
    await asyncio.sleep(1)  # Audit logun Discord API'ye düşmesi için kısa bekleme
    actor_str = "Bilinmiyor"
    reason_str = "Belirtilmedi"

    try:
        async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.ban):
            if entry.target and entry.target.id == user.id:
                actor_str = f"{entry.user.mention} (`{entry.user.id}`)"
                if entry.reason:
                    reason_str = entry.reason
                break
    except Exception as e:
        print(f"⚠️ Audit log ban okunamadı: {e}", flush=True)

    embed = discord.Embed(
        title="🔨 Üye Banlandı",
        description=(
            f"**Banlanan:** {user.mention} (`{user.name}` - `{user.id}`)\n"
            f"**Yapan Yetkili:** {actor_str}\n"
            f"**Sebep:** {reason_str}"
        ),
        color=0xFF4444,
        timestamp=discord.utils.utcnow()
    )
    embed.set_thumbnail(url=user.display_avatar.url)
    await send_audit_log(guild, embed)


@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    """
    1. Geçici ses kanalından herkes çıkarsa kanalı anında sil.
    2. İsim değişikliği yapılmış orijinal kanal boşaldıysa anında eski adına döndür.
    3. Sesten bağlantı kesilmesini (Disconnect) Audit Log üzerinden yakala ve logla.
    """
    # 3. Ses Bağlantısı Kesilme (Disconnect) Kontrolü
    if before.channel and not after.channel:
        # Üye sesten tamamen çıktı veya bağlantısı kesildi
        await asyncio.sleep(1)
        actor_str = None
        try:
            async for entry in member.guild.audit_logs(limit=5, action=discord.AuditLogAction.member_disconnect):
                # Son 5 saniye içindeki disconnect eylemi
                time_diff = (discord.utils.utcnow() - entry.created_at).total_seconds()
                if time_diff < 7:
                    actor_str = f"{entry.user.mention} (`{entry.user.id}`)"
                    break
        except Exception:
            pass

        if actor_str:
            embed = discord.Embed(
                title="🔌 Sesten Bağlantı Kesildi",
                description=(
                    f"**Kullanıcı:** {member.mention} (`{member.id}`)\n"
                    f"**Kanal:** {before.channel.name}\n"
                    f"**Bağlantıyı Kesen Yetkili:** {actor_str}"
                ),
                color=0xFEE75C,
                timestamp=discord.utils.utcnow()
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            await send_audit_log(member.guild, embed)

    # 👑 ALLAH (416978259557744640) Ses Kanalına Giriş / Çıkış Takibi
    if before.channel:
        ch = before.channel

        # 1. Geçici kanal boşaldıysa sil
        if ch.id in temp_channels and len(ch.members) == 0:
            try:
                await ch.delete(reason="Geçici ses kanalındaki herkes çıktığı için silindi.")
                temp_channels.pop(ch.id, None)
                print(f"🗑️ [Geçici Kanal] '{ch.name}' içerisindeki son kişi de çıktığı için anında silindi.", flush=True)
            except Exception as e:
                print(f"⚠️ Kanal silinemedi: {e}", flush=True)

        # 2. İsim değişikliği bekleyen orijinal kanal boşaldıysa anında eski adına döndür
        if ch.id in pending_name_reverts and len(ch.members) == 0:
            orig_name = pending_name_reverts.pop(ch.id, None)
            if orig_name and ch.name != orig_name:
                try:
                    await ch.edit(name=orig_name)
                    print(f"🔄 [Kanal Koruma] '{ch.name}' boşaldığı için hemen eski adı olan '{orig_name}' adına geri döndürüldü.", flush=True)
                except Exception as e:
                    print(f"⚠️ İsim geri döndürülemedi: {e}", flush=True)

    # 4. Kayıtsız Üyeler İçin Dinamik Ses Kanalı Görünürlüğü
    # Biri sese girdiğinde o kanal kayıtsızlara görünür (giremez), kanal boşalınca tamamen gizlenir
    unreg_role = member.guild.get_role(UNREGISTERED_ROLE_ID)
    if unreg_role:
        channels_to_update = set()
        if before.channel:
            channels_to_update.add(before.channel)
        if after.channel:
            channels_to_update.add(after.channel)

        for ch in channels_to_update:
            try:
                over = ch.overwrites_for(unreg_role)
                should_view = (len(ch.members) > 0)
                if over.view_channel != should_view or over.connect is not False:
                    over.view_channel = should_view
                    over.connect = False
                    await ch.set_permissions(unreg_role, overwrite=over)
            except Exception:
                pass


# Kurucuların @everyone kullanım takibi: {user_id: [timestamp1, timestamp2, ...]}
kurucu_everyone_tracker = {}


async def revoke_all_user_perms(rem_id: int):
    """Kullanıcının tüm kanallardaki özel izinlerini kaldırır."""
    for g in bot.guilds:
        rem_m = g.get_member(rem_id)
        if rem_m:
            for ch in g.channels:
                try:
                    await ch.set_permissions(rem_m, overwrite=None)
                except Exception:
                    pass


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    # ──── SUNUCU İÇİ MESAJ KORUMALARI ────
    if message.guild:
        # 👑 @everyone ve @here KORUMASI
        if message.mention_everyone:
            author_id = message.author.id

            # 1. Eğer Allah değilse ve Kurucu da değilse -> Anında Sil ve Engelle
            if not is_kurucu(author_id):
                try:
                    await message.delete()
                    print(f"🛑 [@everyone Engeli] {message.author.name} ({author_id}) izinsiz @everyone/@here attı, mesaj silindi.", flush=True)
                    
                    log_embed = discord.Embed(
                        title="🛑 İzinsiz @everyone Engellendi",
                        description=(
                            f"**Kullanıcı:** {message.author.mention} (`{author_id}`)\n"
                            f"**Kanal:** {message.channel.mention} (`#{message.channel.name}`)\n"
                            f"**Eylem:** @everyone / @here etiketi silindi (Yetkisi yok)."
                        ),
                        color=0xFF0000,
                        timestamp=discord.utils.utcnow()
                    )
                    await send_audit_log(message.guild, log_embed)
                except Exception as e:
                    print(f"⚠️ @everyone mesajı silinemedi: {e}", flush=True)
                return

            # 2. Kurucu ise: Birden fazla @everyone atarsa YETKİSİ ALINIR (Allah hariç)
            elif not is_allah(author_id):
                now = time.time()
                # Son 24 saatteki @everyone kullanımlarını sakla
                if author_id not in kurucu_everyone_tracker:
                    kurucu_everyone_tracker[author_id] = []
                
                # 24 saatten eski kayıtları temizle
                kurucu_everyone_tracker[author_id] = [t for t in kurucu_everyone_tracker[author_id] if now - t < 86400]
                kurucu_everyone_tracker[author_id].append(now)

                # Eğer 1'den fazla @everyone attıysa Kuruculuktan çıkar ve tüm izinlerini sil
                if len(kurucu_everyone_tracker[author_id]) > 1:
                    try:
                        await message.delete()
                    except Exception:
                        pass

                    # Kuruculuktan çıkar
                    k_list = load_kurucu()
                    if author_id in k_list:
                        k_list.remove(author_id)
                        save_kurucu(k_list)

                    # Yetkili (.yt) listesindeyse oradan da çıkar
                    auth_list = load_authorized()
                    if author_id in auth_list:
                        auth_list.remove(author_id)
                        save_authorized(auth_list)

                    # Tüm kanal izinlerini sıfırla
                    await revoke_all_user_perms(author_id)
                    for g in bot.guilds:
                        await sync_voice_permissions(g)

                    print(f"🚨 [Kurucu Yetkisi Alındı] {message.author.name} ({author_id}) birden fazla @everyone attığı için Kurucu yetkisi ve tüm izinleri kalıcı olarak alındı!", flush=True)

                    # Log kanalına ve sunucuya bildir
                    log_embed = discord.Embed(
                        title="🚨 Kurucu Yetkisi Düşürüldü!",
                        description=(
                            f"**Yetkisi Alınan Kurucu:** {message.author.mention} (`{author_id}`)\n"
                            f"**Kanal:** {message.channel.mention} (`#{message.channel.name}`)\n"
                            f"**Sebep:** Birden fazla kez @everyone / @here attığı için Kurucu yetkisi ve tüm kanal izinleri tamamen silindi."
                        ),
                        color=0xFF0000,
                        timestamp=discord.utils.utcnow()
                    )
                    await send_audit_log(message.guild, log_embed)
                    try:
                        await message.channel.send(f"⚠️ {message.author.mention} birden fazla kez @everyone attığı için **Kurucu yetkisi ve tüm izinleri tamamen alındı!**")
                    except Exception:
                        pass
                    return

        # Sunucu içi komutları beklemeden doğrudan ve en hızlı şekilde işle
        await bot.process_commands(message)
        return

    # ──── ÖZELDEN (DM) GELEN MESAJLAR ────
    if isinstance(message.channel, discord.DMChannel):
        uid = message.author.id
        raw_content = message.content.strip()
        content = raw_content.lstrip(".!").strip()

        sender_is_allah = is_allah(uid)
        sender_is_kurucu = is_kurucu(uid) and not sender_is_allah
        sender_is_yetkili = (uid in load_authorized()) and not is_kurucu(uid)

        # Sadece yetkili/kurucu/allah cevap alır
        if not is_authorized(uid):
            await bot.process_commands(message)
            return

        async def sync_all():
            cfg = load_config()
            for g in bot.guilds:
                await sync_voice_permissions(g)
                w_id = cfg.get("welcome_channel_id")
                e_id = cfg.get("exit_channel_id")
                l_id = cfg.get("log_channel_id")
                if w_id:
                    wch = g.get_channel(int(w_id))
                    if wch:
                        await lock_and_grant_channel(wch)
                if e_id:
                    ech = g.get_channel(int(e_id))
                    if ech:
                        await lock_and_grant_private_channel(ech)
                if l_id:
                    lch = g.get_channel(int(l_id))
                    if lch:
                        await lock_and_grant_private_channel(lch)
                # Kayıtsız rol izinlerini EN SON uygula
                await configure_unregistered_role_permissions(g)

        async def remove_all_perms(rem_id: int):
            for g in bot.guilds:
                rem_m = g.get_member(rem_id)
                if rem_m:
                    # Tüm ses kanallarından izinlerini sıfırla
                    for ch in g.voice_channels:
                        try:
                            await ch.set_permissions(rem_m, overwrite=None)
                        except Exception:
                            pass
                    # Hoş geldin, çıkış, log kanallarından izinlerini sıfırla
                    cfg = load_config()
                    for cid_key in ("welcome_channel_id", "exit_channel_id", "log_channel_id"):
                        cid = cfg.get(cid_key)
                        if cid:
                            wch = g.get_channel(int(cid))
                            if wch:
                                try:
                                    await wch.set_permissions(rem_m, overwrite=None)
                                except Exception:
                                    pass

        # ── ALLAH KOMUTLARI ──────────────────────────────────────────
        if sender_is_allah:
            # duzenleme / düzenleme (Ses kanalları düzenleme modunu açar/kapatır ve hafızaya kazır)
            if content in ("duzenleme", "düzenleme"):
                cfg = load_config()
                current_mode = cfg.get("edit_mode", False)
                if not current_mode:
                    # Düzenleme modunu AÇ
                    cfg["edit_mode"] = True
                    save_config(cfg)
                    await message.channel.send(
                        "🔧 **Ses Kanalları Düzenleme Modu AÇILDI!**\n"
                        "• Artık ses kanallarını silebilir veya değiştirebilirsiniz (bot kanalları geri açmayacak).\n"
                        "• Düzenlemeniz bittiğinde tekrar `duzenleme` yazın; yeni ses kanalları botun hafızasına kazınacak ve koruma tekrar aktifleşecektir."
                    )
                else:
                    # Düzenleme modunu KAPAT ve sunucudaki güncel ses kanallarını hafızaya kazı
                    cfg["edit_mode"] = False
                    save_config(cfg)
                    for g in bot.guilds:
                        record_voice_snapshot(g, overwrite=True)
                        await sync_voice_permissions(g)
                    await message.channel.send(
                        "✅ **Ses Kanalları Düzenleme Modu KAPATILDI!**\n"
                        "• Sunucudaki tüm güncel ses kanalları botun hafızasına kazındı.\n"
                        "• İzinler eşitlendi ve ses kanalları koruması tekrar aktif edildi."
                    )
                return

            # kurucu ekle <id>
            if content.startswith("kurucu ekle "):
                parts = content.split()
                target_part = parts[-1]
                try:
                    new_id = int(target_part)
                    k_list = load_kurucu()
                    if new_id in k_list:
                        await message.channel.send(f"⚠️ <@{new_id}> (`{new_id}`) zaten kurucudur!")
                    else:
                        k_list.append(new_id)
                        save_kurucu(k_list)
                        await sync_all()
                        await message.channel.send(f"👑 <@{new_id}> (`{new_id}`) **Kurucu** olarak eklendi!")
                except ValueError:
                    await message.channel.send("❌ Geçersiz ID!")
                return

            # kurucu cikar <id>
            if content.startswith("kurucu cikar ") or content.startswith("kurucu çıkar "):
                parts = content.split()
                target_part = parts[-1]
                try:
                    rem_id = int(target_part)
                    k_list = load_kurucu()
                    if rem_id not in k_list:
                        await message.channel.send(f"⚠️ <@{rem_id}> (`{rem_id}`) kurucu listesinde yok!")
                    else:
                        k_list.remove(rem_id)
                        save_kurucu(k_list)
                        await remove_all_perms(rem_id)
                        await sync_all()
                        await message.channel.send(f"✅ <@{rem_id}> (`{rem_id}`) kurucu listesinden çıkarıldı!")
                except ValueError:
                    await message.channel.send("❌ Geçersiz ID!")
                return

            # kurucu liste
            if content in ("kurucu liste", "kuruculiste"):
                k_list = load_kurucu()
                if not k_list:
                    await message.channel.send("📋 Kurucu listesi boş.")
                else:
                    liste = "\n".join([f"• <@{i}> (`{i}`)" for i in k_list])
                    await message.channel.send(f"👑 **Kurucular Listesi:**\n{liste}")
                return

        # ── KURUCU VE ALLAH KOMUTLARI ────────────────────────────────
        if sender_is_allah or sender_is_kurucu:
            # yt ekle <id>
            if content.startswith("yt ekle ") or content.startswith("yetkili ekle "):
                parts = content.split()
                target_part = parts[-1]
                try:
                    new_id = int(target_part)
                    a_list = load_authorized()
                    if new_id in a_list:
                        await message.channel.send(f"⚠️ <@{new_id}> (`{new_id}`) zaten yetkilidir!")
                    else:
                        a_list.append(new_id)
                        save_authorized(a_list)
                        await sync_all()
                        await message.channel.send(f"✅ <@{new_id}> (`{new_id}`) **Tam Yetkili (.yt)** olarak eklendi!")
                except ValueError:
                    await message.channel.send("❌ Geçersiz ID!")
                return

            # yt cikar <id>
            if content.startswith("yt cikar ") or content.startswith("yt çıkar ") or content.startswith("yetkili cikar ") or content.startswith("yetkili çıkar "):
                parts = content.split()
                target_part = parts[-1]
                try:
                    rem_id = int(target_part)
                    a_list = load_authorized()
                    if rem_id not in a_list:
                        await message.channel.send(f"⚠️ <@{rem_id}> (`{rem_id}`) yetkili listesinde yok!")
                    else:
                        a_list.remove(rem_id)
                        save_authorized(a_list)
                        await remove_all_perms(rem_id)
                        await sync_all()
                        await message.channel.send(f"✅ <@{rem_id}> (`{rem_id}`) yetkili listesinden çıkarıldı!")
                except ValueError:
                    await message.channel.send("❌ Geçersiz ID!")
                return

            # yt liste
            if content in ("yt liste", "ytliste", "yetkili liste", "yetkililiste"):
                a_list = load_authorized()
                if not a_list:
                    await message.channel.send("📋 Tam yetkili listesi boş.")
                else:
                    liste = "\n".join([f"• <@{i}> (`{i}`)" for i in a_list])
                    await message.channel.send(f"📋 **Tam Yetkililer (.yt) Listesi:**\n{liste}")
                return

            # welcome <kanal_id>
            if content.startswith("welcome "):
                parts = content.split()
                if len(parts) == 2:
                    try:
                        ch_id = int(parts[1])
                        channel = bot.get_channel(ch_id)
                        if not channel or not isinstance(channel, discord.TextChannel):
                            await message.channel.send("❌ Bu ID'ye sahip bir metin kanalı bulunamadı!")
                            return
                        cfg = load_config()
                        cfg["welcome_channel_id"] = str(ch_id)
                        save_config(cfg)
                        await lock_and_grant_channel(channel)
                        # Kayıtsız izinlerini de tazele
                        for g in bot.guilds:
                            await configure_unregistered_role_permissions(g)
                        await message.channel.send(
                            f"✅ **Hoş Geldin kanalı ayarlandı:** #{channel.name} (`{ch_id}`)\n"
                            f"🔒 Kanal herkese yazmaya kapatıldı, sadece yetkililere ve üstlerine açık!"
                        )
                    except ValueError:
                        await message.channel.send("❌ Geçersiz kanal ID'si!")
                else:
                    await message.channel.send("❌ Kullanım: `welcome <kanal_id>`")
                return

            # exit <kanal_id>
            if content.startswith("exit "):
                parts = content.split()
                if len(parts) == 2:
                    try:
                        ch_id = int(parts[1])
                        channel = bot.get_channel(ch_id)
                        if not channel or not isinstance(channel, discord.TextChannel):
                            await message.channel.send("❌ Bu ID'ye sahip bir metin kanalı bulunamadı!")
                            return
                        cfg = load_config()
                        cfg["exit_channel_id"] = str(ch_id)
                        save_config(cfg)
                        await lock_and_grant_private_channel(channel)
                        await message.channel.send(
                            f"✅ **Ayrılanlar (Exit) kanalı ayarlandı:** #{channel.name} (`{ch_id}`)\n"
                            f"🔒 Kanal @everyone'a tamamen GİZLENDİ! Sadece yetkililer görebilir."
                        )
                    except ValueError:
                        await message.channel.send("❌ Geçersiz kanal ID'si!")
                else:
                    await message.channel.send("❌ Kullanım: `exit <kanal_id>`")
                return

            # log <kanal_id> (Denetim Kaydı Kanalı Ayarlama)
            if content.startswith("log "):
                parts = content.split()
                if len(parts) == 2:
                    try:
                        ch_id = int(parts[1])
                        channel = bot.get_channel(ch_id)
                        if not channel or not isinstance(channel, discord.TextChannel):
                            await message.channel.send("❌ Bu ID'ye sahip bir metin kanalı bulunamadı!")
                            return
                        cfg = load_config()
                        cfg["log_channel_id"] = str(ch_id)
                        save_config(cfg)
                        await lock_and_grant_private_channel(channel)
                        await message.channel.send(
                            f"✅ **Denetim Kaydı (Log) kanalı ayarlandı:** #{channel.name} (`{ch_id}`)\n"
                            f"🔒 Kanal @everyone'a tamamen GİZLENDİ! Sadece yetkililer görebilir."
                        )
                    except ValueError:
                        await message.channel.send("❌ Geçersiz kanal ID'si!")
                else:
                    await message.channel.send("❌ Kullanım: `log <kanal_id>`")
                return

            # rules <kanal_id>
            if content.startswith("rules "):
                parts = content.split()
                if len(parts) == 2:
                    try:
                        ch_id = int(parts[1])
                        channel = bot.get_channel(ch_id)
                        if not channel or not isinstance(channel, discord.TextChannel):
                            await message.channel.send("❌ Bu ID'ye sahip bir metin kanalı bulunamadı!")
                            return
                        cfg = load_config()
                        cfg["rules_channel_id"] = str(ch_id)
                        save_config(cfg)
                        # Kayıtsız rol izinlerini güncelle
                        for g in bot.guilds:
                            await configure_unregistered_role_permissions(g)
                        await message.channel.send(
                            f"✅ **Kurallar (Rules) kanalı ayarlandı:** #{channel.name} (`{ch_id}`)\n"
                            f"📋 Kayıtsız üyeler artık bu kanalı da görebilir (sadece okuma)."
                        )
                    except ValueError:
                        await message.channel.send("❌ Geçersiz kanal ID'si!")
                else:
                    await message.channel.send("❌ Kullanım: `rules <kanal_id>`")
                return

            # kayitrol <rol_id>
            if content.startswith("kayitrol "):
                parts = content.split()
                if len(parts) == 2:
                    try:
                        rol_id = int(parts[1])
                        # Rolün var olup olmadığını kontrol et
                        rol_found = False
                        for g in bot.guilds:
                            role = g.get_role(rol_id)
                            if role:
                                rol_found = True
                                break
                        if not rol_found:
                            await message.channel.send(f"⚠️ `{rol_id}` ID'sine sahip bir rol bulunamadı! Yine de kaydedildi.")
                        cfg = load_config()
                        cfg["registered_role_id"] = str(rol_id)
                        save_config(cfg)
                        await message.channel.send(
                            f"✅ **Kayıtlı Rolü ayarlandı:** `{rol_id}`\n"
                            f"Bundan sonra butonla kayıt edilenlere bu rol verilecek, Kayıtsız Rolü alınacak."
                        )
                    except ValueError:
                        await message.channel.send("❌ Geçersiz rol ID'si!")
                else:
                    await message.channel.send("❌ Kullanım: `kayitrol <rol_id>`")
                return

            # yt yardim
            if content in ("yt yardim", "yt yardım", "yardim", "yardım"):
                cfg = load_config()
                w_id = cfg.get("welcome_channel_id", "Ayarlanmadı")
                e_id = cfg.get("exit_channel_id", "Ayarlanmadı")
                l_id = cfg.get("log_channel_id", "Ayarlanmadı")
                r_id = cfg.get("rules_channel_id", "Ayarlanmadı")
                rr_id = cfg.get("registered_role_id", "Ayarlanmadı")
                extra = ""
                if sender_is_allah:
                    extra = (
                        "\n**👼 Allah Komutları:**\n"
                        "`kurucu ekle <id>` → Kurucu ekle\n"
                        "`kurucu cikar <id>` → Kurucu çıkar\n"
                        "`kurucu liste` → Kurucu listesini göster\n"
                    )
                await message.channel.send(
                    f"**🔧 Yönetim Komutları (Özelden yaz):**\n"
                    "`yt ekle <id>` → Tam Yetkili ekle (ses açma + ban/kick + mute)\n"
                    "`yt cikar <id>` → Tam Yetkili çıkar\n"
                    "`yt liste` → Tam Yetkili listesi\n"
                    "`sesyt ekle <id>` → Ses Yetkilisi ekle (bağlantı kes/mute/sağırlaştır)\n"
                    "`sesyt cikar <id>` → Ses Yetkilisi çıkar\n"
                    "`sesyt liste` → Ses Yetkilisi listesi\n"
                    "`welcome <kanal_id>` → Giriş kanalını ayarla & kitle\n"
                    "`exit <kanal_id>` → Çıkış kanalını ayarla & kitle\n"
                    "`log <kanal_id>` → Gizli Denetim (Audit Log) kanalını ayarla & yetkililere özel yap\n"
                    f"{extra}"
                    f"\n📌 **Mevcut Ayarlar:**\n"
                    f"• Welcome Kanalı: `{w_id}`\n"
                    f"• Exit Kanalı: `{e_id}`\n"
                    f"• Denetim Log Kanalı: `{l_id}`"
                )
                return

        # ── TAM YETKİLİLER (.yt) İÇİN SES YETKİLİSİ (.sesyt) YÖNETİMİ ──
        if is_full_authorized(uid):
            # sesyt ekle <id>
            if content.startswith("sesyt ekle ") or content.startswith("ses yt ekle "):
                parts = content.split()
                target_part = parts[-1]
                try:
                    new_id = int(target_part)
                    s_list = load_sesyt()
                    if new_id in s_list:
                        await message.channel.send(f"⚠️ <@{new_id}> (`{new_id}`) zaten ses yetkilisidir!")
                    else:
                        s_list.append(new_id)
                        save_sesyt(s_list)
                        await sync_all()
                        await message.channel.send(f"✅ <@{new_id}> (`{new_id}`) **Ses Yetkilisi (.sesyt)** olarak eklendi! (Mute/Deafen/Move izinleri tanımlandı)")
                except ValueError:
                    await message.channel.send("❌ Geçersiz ID!")
                return

            # sesyt cikar <id>
            if content.startswith("sesyt cikar ") or content.startswith("sesyt çıkar ") or content.startswith("ses yt cikar ") or content.startswith("ses yt çıkar "):
                parts = content.split()
                target_part = parts[-1]
                try:
                    rem_id = int(target_part)
                    s_list = load_sesyt()
                    if rem_id not in s_list:
                        await message.channel.send(f"⚠️ <@{rem_id}> (`{rem_id}`) ses yetkilisi listesinde yok!")
                    else:
                        s_list.remove(rem_id)
                        save_sesyt(s_list)
                        await remove_all_perms(rem_id)
                        await sync_all()
                        await message.channel.send(f"✅ <@{rem_id}> (`{rem_id}`) ses yetkilisi listesinden çıkarıldı!")
                except ValueError:
                    await message.channel.send("❌ Geçersiz ID!")
                return

            # sesyt liste
            if content in ("sesyt liste", "sesytliste", "ses yt liste"):
                s_list = load_sesyt()
                if not s_list:
                    await message.channel.send("📋 Ses yetkilisi (.sesyt) listesi boş.")
                else:
                    liste = "\n".join([f"• <@{i}> (`{i}`)" for i in s_list])
                    await message.channel.send(f"📋 **Ses Yetkilileri (.sesyt) Listesi:**\n{liste}")
                return

        # ── HEPSİ için: komutlar menüsü ─────────────────────────────
        if content == "komutlar":
            view = KomutlarView(
                user=message.author,
                is_owner=(sender_is_allah or sender_is_kurucu),
                is_auth=is_full_authorized(uid)
            )
            await message.channel.send(embed=view.get_embed(), view=view)
            return

    await bot.process_commands(message)


@bot.event
async def on_command_error(ctx, error):
    print(f"❌ Komut hatası ({ctx.command}): {error}", flush=True)


@bot.event
async def on_member_join(member: discord.Member):
    """Biri sunucuya katıldığında tetiklenir: Kayıtsız rolü verir ve welcome mesajı atar."""
    print(f"👋 Yeni üye katıldı: {member.name} (Sunucu: {member.guild.name})", flush=True)

    # 1. Kayıtsız Rolü Ver (1544413431409410058)
    try:
        unreg_role = member.guild.get_role(UNREGISTERED_ROLE_ID)
        if unreg_role:
            await member.add_roles(unreg_role, reason="Yeni katılan üyeye Kayıtsız Rolü verildi.")
            print(f"🔒 {member.name} kullanıcısına Kayıtsız Rolü verildi.", flush=True)
    except Exception as e:
        print(f"⚠️ Kayıtsız rolü verilemedi: {e}", flush=True)

    # 2. Hoş Geldin Mesajı Gönder
    cfg = load_config()
    target_channel = None
    w_id = cfg.get("welcome_channel_id") or os.getenv("WELCOME_CHANNEL_ID")

    if w_id and w_id != "KANAL_ID_BURAYA_YAZIN":
        try:
            target_channel = bot.get_channel(int(w_id))
        except ValueError:
            pass

    if not target_channel:
        target_channel = member.guild.system_channel
        if not target_channel:
            target_channel = next(
                (ch for ch in member.guild.text_channels if ch.permissions_for(member.guild.me).send_messages),
                None
            )

    if target_channel:
        try:
            embed = create_welcome_embed(member)
            view = KayitView()
            await target_channel.send(embed=embed, view=view)
            print(f"✅ Hoş geldin mesajı '{target_channel.name}' kanalına gönderildi.", flush=True)
        except Exception as e:
            print(f"❌ Hoş geldin mesajı gönderilirken hata: {e}", flush=True)


@bot.event
async def on_member_remove(member: discord.Member):
    """Biri sunucudan ayrıldığında veya atıldığında (kick) tetiklenir."""
    print(f"🚪 Üye ayrıldı: {member.name} (Sunucu: {member.guild.name})", flush=True)

    # 1. Allah dışındaki kişilerin yetkilerini tamamen sıfırla
    if not is_allah(member.id):
        k_list = load_kurucu()
        a_list = load_authorized()
        s_list = load_sesyt()
        changed = False

        if member.id in k_list:
            k_list.remove(member.id)
            save_kurucu(k_list)
            changed = True
            print(f"🚫 [Yetki İptali] {member.name} sunucudan çıktığı için Kurucu yetkisi alındı.", flush=True)

        if member.id in a_list:
            a_list.remove(member.id)
            save_authorized(a_list)
            changed = True
            print(f"🚫 [Yetki İptali] {member.name} sunucudan çıktığı için Tam Yetkili (.yt) yetkisi alındı.", flush=True)

        if member.id in s_list:
            s_list.remove(member.id)
            save_sesyt(s_list)
            changed = True
            print(f"🚫 [Yetki İptali] {member.name} sunucudan çıktığı için Ses Yetkisi (.sesyt) alındı.", flush=True)

        if changed:
            # Sunucudaki kanal izinlerini senkronize et
            await sync_voice_permissions(member.guild)

    # 2. Kick (Atılma) Kontrolü (Audit Log)
    await asyncio.sleep(1)
    try:
        async for entry in member.guild.audit_logs(limit=5, action=discord.AuditLogAction.kick):
            if entry.target and entry.target.id == member.id:
                time_diff = (discord.utils.utcnow() - entry.created_at).total_seconds()
                if time_diff < 7:
                    actor_str = f"{entry.user.mention} (`{entry.user.id}`)"
                    reason_str = entry.reason or "Belirtilmedi"
                    embed_kick = discord.Embed(
                        title="👢 Üye Sunucudan Atıldı (Kick)",
                        description=(
                            f"**Atılan:** {member.mention} (`{member.name}` - `{member.id}`)\n"
                            f"**Yapan Yetkili:** {actor_str}\n"
                            f"**Sebep:** {reason_str}"
                        ),
                        color=0xFF8800,
                        timestamp=discord.utils.utcnow()
                    )
                    embed_kick.set_thumbnail(url=member.display_avatar.url)
                    await send_audit_log(member.guild, embed_kick)
                    break
    except Exception as e:
        print(f"⚠️ Audit log kick okunamadı: {e}", flush=True)

    # 3. Standart Çıkış Mesajı
    cfg = load_config()
    target_channel = None
    e_id = cfg.get("exit_channel_id")

    if e_id:
        try:
            target_channel = bot.get_channel(int(e_id))
        except ValueError:
            pass

    # Exit kanalı ayarlanmamışsa welcome kanalına gönder
    if not target_channel:
        w_id = cfg.get("welcome_channel_id")
        if w_id:
            try:
                target_channel = bot.get_channel(int(w_id))
            except ValueError:
                pass

    if target_channel:
        try:
            embed = create_exit_embed(member)
            await target_channel.send(embed=embed)
            print(f"✅ Çıkış mesajı '{target_channel.name}' kanalına gönderildi.", flush=True)
        except Exception as e:
            print(f"❌ Çıkış mesajı gönderilirken hata: {e}", flush=True)


# ──────────────────────────────────────────────
# KOMUTLAR
# ──────────────────────────────────────────────

@bot.tree.command(name="testwelcome", description="Hoş geldin mesajını test eder.")
async def test_welcome(interaction: discord.Interaction):
    embed = create_welcome_embed(interaction.user)
    view = KayitView()
    await interaction.response.send_message(embed=embed, view=view)
    view.stop()


@bot.command(name="testwelcome")
async def test_welcome_prefix(ctx):
    embed = create_welcome_embed(ctx.author)
    view = KayitView()
    await ctx.send(embed=embed, view=view)
    view.stop()


@bot.command(name="testexit")
async def test_exit_prefix(ctx):
    embed = create_exit_embed(ctx.author)
    await ctx.send(embed=embed)


@bot.command(name="av")
async def avatar(ctx, *, hedef: str = None):
    """Avatar gösterir. Kullanım: .av | .av @kisi | .av <id>"""
    user = None
    if hedef is None:
        user = ctx.author
    elif ctx.message.mentions:
        user = ctx.message.mentions[0]
    else:
        try:
            user = await bot.fetch_user(int(hedef.strip()))
        except ValueError:
            await ctx.send("❌ Geçersiz kullanıcı ID'si!")
            return
        except discord.NotFound:
            await ctx.send("❌ Bu ID'ye sahip kullanıcı bulunamadı!")
            return

    avatar_url = user.display_avatar.with_size(1024).url
    embed = discord.Embed(title=f"{user.display_name} avatarı", color=user.accent_color or 0x5865F2)
    embed.set_image(url=avatar_url)
    embed.set_footer(text=f"ID: {user.id}")
    await ctx.send(embed=embed)


class KomutlarView(discord.ui.View):
    """Komutları sayfalar halinde butonlarla gösteren interaktif menü."""

    def __init__(self, user: discord.User, is_owner: bool, is_auth: bool):
        super().__init__(timeout=180)
        self.user = user
        self.is_owner = is_owner
        self.is_auth = is_auth
        self.current_page = 0

        # Sayfaları oluştur
        self.pages = []

        # 1. Sayfa: Genel Komutlar
        p1 = discord.Embed(
            title="🌐 Genel Komutlar",
            description=(
                "- `.av` → Kendi avatarını göster\n"
                "- `.av @kisi` → Birinin avatarını göster\n"
                "- `.av <id>` → ID'li kişinin avatarını göster\n"
                "- `.komutlar` → Bu menüyü özelden aç\n"
                "- `.testwelcome` → Hoş geldin mesajını test et\n"
                "- `.testexit` → Ayrıldı mesajını test et"
            ),
            color=0x242429
        )
        self.pages.append(p1)

        # 2. Sayfa: Moderasyon Komutları (Yetkili veya üstü)
        if self.is_auth or self.is_owner:
            p2 = discord.Embed(
                title="🔨 Moderasyon & Ses Yetkisi Komutları",
                description=(
                    "- `.ban @kisi [sebep]` → Kullanıcıyı sunucudan banla\n"
                    "- `.ban <id> [sebep]` → ID ile sunucudan banla\n"
                    "- `.kick @kisi [sebep]` → Kullanıcıyı sunucudan at\n"
                    "- `.kick <id> [sebep]` → ID ile sunucudan at\n"
                    "- `.nuke` → Bulunulan kanalı sıfırlar (tüm mesajları temizler)\n"
                    "- `.sestara` → Ses kanalları izinlerini yenile\n"
                    "- `sesyt ekle <id>` → (Özelden) Ses Yetkilisi ekle\n"
                    "- `sesyt cikar <id>` → (Özelden) Ses Yetkilisi çıkar\n"
                    "- `sesyt liste` → (Özelden) Ses Yetkilisi listesi"
                ),
                color=0x242429
            )
            self.pages.append(p2)

        # 3. Sayfa: Kurucu Komutları (Kurucu ve Allah)
        if self.is_owner:
            p3 = discord.Embed(
                title="👑 Kurucu Komutları (Özelden)",
                description=(
                    "- `yt ekle <id>` → Tam Yetkili ekle (ses açma + ban/kick)\n"
                    "- `yt cikar <id>` → Tam Yetkili çıkar\n"
                    "- `yt liste` → Tam Yetkili listesini göster\n"
                    "- `sesyt ekle <id>` → Ses Yetkilisi ekle (bağlantı kes/mute/sağırlaştır)\n"
                    "- `sesyt cikar <id>` → Ses Yetkilisi çıkar\n"
                    "- `sesyt liste` → Ses Yetkilileri listesi\n"
                    "- `welcome <kanal_id>` → Giriş kanalını ayarla & kitle\n"
                    "- `exit <kanal_id>` → Çıkış kanalını ayarla & kitle\n"
                    "- `yt yardim` → Yönetim durum & menü"
                ),
                color=0x242429
            )
            self.pages.append(p3)

        # 4. Sayfa: Allah Komutları (Sadece Allah)
        if is_allah(self.user.id):
            p4 = discord.Embed(
                title="👼 Allah Komutları (Özelden)",
                description=(
                    "- `kurucu ekle <id>` → Kurucu ekle\n"
                    "- `kurucu cikar <id>` → Kurucu çıkar\n"
                    "- `kurucu liste` → Kurucu listesini göster\n\n"
                    "**Hiyerarşi:** 👼 Allah > 👑 Kurucu > 🔨 Tam Yetkili (.yt) > 🔊 Ses Yetkilisi (.sesyt)"
                ),
                color=0xFFD700
            )
            self.pages.append(p4)

        self.update_buttons()

    def get_embed(self) -> discord.Embed:
        embed = self.pages[self.current_page]
        embed.set_footer(text=f"Sayfa {self.current_page + 1} / {len(self.pages)} • Prefix: . veya !")
        return embed

    def update_buttons(self):
        self.prev_button.disabled = (self.current_page == 0)
        self.next_button.disabled = (self.current_page == len(self.pages) - 1)
        self.page_indicator.label = f"{self.current_page + 1}/{len(self.pages)}"

    @discord.ui.button(label="◀ Geri", style=discord.ButtonStyle.secondary, custom_id="btn_prev")
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Bu butonları sadece komutu kullanan kişi tıklayabilir.", ephemeral=True)
            return
        if self.current_page > 0:
            self.current_page -= 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(label="1/1", style=discord.ButtonStyle.primary, disabled=True, custom_id="btn_indicator")
    async def page_indicator(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass

    @discord.ui.button(label="İleri ▶", style=discord.ButtonStyle.secondary, custom_id="btn_next")
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Bu butonları sadece komutu kullanan kişi tıklayabilir.", ephemeral=True)
            return
        if self.current_page < len(self.pages) - 1:
            self.current_page += 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.get_embed(), view=self)


@bot.command(name="komutlar")
async def komutlar(ctx):
    """
    SADECE ÖZELDEN (DM) çalışır.
    Sunucuda yazılırsa çalışmaz ve mesaj silinir.
    """
    # Sunucuda yazıldıysa çalıştırma, mesajı sil
    if ctx.guild is not None:
        try:
            await ctx.message.delete()
        except Exception:
            pass
        return

    is_owner_tier = is_kurucu(ctx.author.id)
    yetkili = is_authorized(ctx.author.id)

    view = KomutlarView(user=ctx.author, is_owner=is_owner_tier, is_auth=yetkili)
    await ctx.send(embed=view.get_embed(), view=view)


@bot.command(name="sestara")
async def ses_tara(ctx):
    """Yetkililerin ses kanalı izinlerini yeniler."""
    if not is_authorized(ctx.author.id):
        if ctx.guild:
            await ctx.message.delete()
        return

    guild = ctx.guild
    if not guild:
        guild = bot.guilds[0] if bot.guilds else None
    if not guild:
        await ctx.send("❌ Bot herhangi bir sunucuda bulunamadı!")
        return

    await sync_voice_permissions(guild)
    await ctx.send("✅ Ses kanalları tarandı ve yetkililerin sağ tık izinleri tanımlandı!")
    if ctx.guild:
        try:
            await ctx.message.delete()
        except Exception:
            pass


@bot.command(name="ban")
async def ban(ctx, *, hedef: str = None):
    """Kullanıcıyı banlar."""
    if not is_authorized(ctx.author.id):
        if ctx.guild:
            await ctx.message.delete()
        return

    if hedef is None:
        await ctx.send("❌ Kullanım: `.ban @kisi [sebep]` veya `.ban <id> [sebep]`")
        return

    # DM'den veya sunucudan çalışabilmesi için guild tespiti
    guild = ctx.guild
    if not guild:
        guild = bot.guilds[0] if bot.guilds else None
    if not guild:
        await ctx.send("❌ Bot herhangi bir sunucuda bulunamadı!")
        return

    member = None
    reason = "Sebep belirtilmedi"
    user_obj = None

    if ctx.message.mentions:
        member = ctx.message.mentions[0]
        user_obj = member
        mention_str = hedef.split()
        if len(mention_str) > 1:
            reason = " ".join(mention_str[1:])
    else:
        parts = hedef.split(None, 1)
        try:
            uid = int(parts[0])
            if len(parts) > 1:
                reason = parts[1]
            try:
                member = await guild.fetch_member(uid)
                user_obj = member
            except (discord.NotFound, discord.HTTPException):
                try:
                    user_obj = await bot.fetch_user(uid)
                except Exception:
                    user_obj = None
        except ValueError:
            await ctx.send("❌ Geçersiz kullanıcı ID'si!")
            return

    target_id = member.id if member else (user_obj.id if user_obj else uid)

    # Hiyerarşik Koruma Kuralları
    if is_allah(target_id):
        await ctx.send("❌ Allah modundaki kişiye ASLA dokunamazsınız!")
        return
    if target_id == ctx.author.id:
        await ctx.send("❌ Kendinizi banlayamazsınız!")
        return
    if target_id == bot.user.id:
        await ctx.send("❌ Beni banlayamazsınız!")
        return

    # Hedef Kurucu ise sadece Allah işlem yapabilir
    if is_kurucu(target_id) and not is_allah(ctx.author.id):
        await ctx.send("❌ Kurucu birine sadece Allah modundaki kişi işlem yapabilir!")
        return

    # Hedef Yetkili ise sıradan yetkililer işlem yapamaz
    if is_authorized(target_id) and not is_kurucu(ctx.author.id):
        await ctx.send("❌ Yetkili birine sadece Kurucu veya Allah işlem yapabilir!")
        return

    # Onay Görünümü (Teyit Butonları)
    class ModerationConfirmView(discord.ui.View):
        def __init__(self, author_id: int):
            super().__init__(timeout=60)
            self.author_id = author_id
            self.value = None

        @discord.ui.button(label="emin misin", style=discord.ButtonStyle.green, custom_id="btn_confirm_mod")
        async def confirm_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
            if interaction.user.id != self.author_id:
                await interaction.response.send_message("❌ Bu butona sadece komutu kullanan kişi basabilir!", ephemeral=True)
                return
            self.value = True
            self.stop()
            await interaction.response.defer()

        @discord.ui.button(label="🥺", style=discord.ButtonStyle.red, custom_id="btn_cancel_mod")
        async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
            if interaction.user.id != self.author_id:
                await interaction.response.send_message("❌ Bu butona sadece komutu kullanan kişi basabilir!", ephemeral=True)
                return
            self.value = False
            self.stop()
            await interaction.response.defer()

    confirm_text = (
        "Ay, hüüü... bunu ya-yapıyosun ama... 🥺👉👈 bunu yapai'ken sa-sahibim bana kı'zmayacak di' mi, emin misinnn? 🥺🐾\n\n"
        "Ben sadeceee sen istedin diye yapıyoiuuu'm ki, ben aslı'nda hiç böyle şeylei yapma'm, çok utangacııı'm zateeen... 👉👈🫣 Beni de koiui'sun di' mi, owwo? 💕✨"
    )

    confirm_embed = discord.Embed(
        title="🥺 Emin Misinnn? 👉👈",
        description=confirm_text,
        color=0xFFB6C1
    )

    view = ModerationConfirmView(ctx.author.id)
    confirm_msg = await ctx.send(embed=confirm_embed, view=view)

    await view.wait()

    if view.value is True:
        try:
            target_obj = member or discord.Object(id=target_id)
            await guild.ban(target_obj, reason=reason)
            target_display = f"<@{target_id}> (`{target_id}`)"
            embed = discord.Embed(
                description=f"🔨 {target_display} sunucudan **banlandı**.\n📝 Sebep: {reason}",
                color=0xFF4444
            )
            await ctx.send(embed=embed)
            if ctx.guild:
                try:
                    await ctx.message.delete()
                except Exception:
                    pass
            try:
                await confirm_msg.delete()
            except Exception:
                pass
            print(f"🔨 {ctx.author} → {target_id} banlandı. Sebep: {reason}", flush=True)
        except discord.Forbidden:
            await ctx.send("❌ Botun bu kişiyi banlama yetkisi veya rol sırası yetersiz!")
        except Exception as e:
            await ctx.send(f"❌ Hata: {e}")
    else:
        try:
            await confirm_msg.delete()
        except Exception:
            pass
        cancel_embed = discord.Embed(
            description="🥺 İşlem iptal edildi, sahibim kızmayacak yaşasınnn! ✨",
            color=0x57F287
        )
        await ctx.send(embed=cancel_embed, delete_after=6)


@bot.command(name="kick")
async def kick(ctx, *, hedef: str = None):
    """Kullanıcıyı atar."""
    if not is_authorized(ctx.author.id):
        if ctx.guild:
            await ctx.message.delete()
        return

    if hedef is None:
        await ctx.send("❌ Kullanım: `.kick @kisi [sebep]` veya `.kick <id> [sebep]`")
        return

    guild = ctx.guild
    if not guild:
        guild = bot.guilds[0] if bot.guilds else None
    if not guild:
        await ctx.send("❌ Bot herhangi bir sunucuda bulunamadı!")
        return

    member = None
    reason = "Sebep belirtilmedi"

    if ctx.message.mentions:
        member = ctx.message.mentions[0]
        mention_str = hedef.split()
        if len(mention_str) > 1:
            reason = " ".join(mention_str[1:])
    else:
        parts = hedef.split(None, 1)
        try:
            uid = int(parts[0])
            if len(parts) > 1:
                reason = parts[1]
            try:
                member = await guild.fetch_member(uid)
            except (discord.NotFound, discord.HTTPException):
                await ctx.send("❌ Bu ID'li kullanıcı sunucuda bulunamadı (Kick için sunucuda olmalı)!")
                return
        except ValueError:
            await ctx.send("❌ Geçersiz kullanıcı!")
            return

    if member is None:
        await ctx.send("❌ Kullanıcı bulunamadı!")
        return

    # Hiyerarşik Koruma Kuralları
    if is_allah(member.id):
        await ctx.send("❌ Allah modundaki kişiye ASLA dokunamazsınız!")
        return
    if member.id == ctx.author.id:
        await ctx.send("❌ Kendinizi atamazsınız!")
        return
    if member.id == bot.user.id:
        await ctx.send("❌ Beni atamazsınız!")
        return

    # Hedef Kurucu ise sadece Allah işlem yapabilir
    if is_kurucu(member.id) and not is_allah(ctx.author.id):
        await ctx.send("❌ Kurucu birine sadece Allah modundaki kişi işlem yapabilir!")
        return

    # Hedef Yetkili ise sıradan yetkililer işlem yapamaz
    if is_authorized(member.id) and not is_kurucu(ctx.author.id):
        await ctx.send("❌ Yetkili birine sadece Kurucu veya Allah işlem yapabilir!")
        return

    # Onay Görünümü (Teyit Butonları)
    class ModerationConfirmView(discord.ui.View):
        def __init__(self, author_id: int):
            super().__init__(timeout=60)
            self.author_id = author_id
            self.value = None

        @discord.ui.button(label="emin misin", style=discord.ButtonStyle.green, custom_id="btn_confirm_kick")
        async def confirm_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
            if interaction.user.id != self.author_id:
                await interaction.response.send_message("❌ Bu butona sadece komutu kullanan kişi basabilir!", ephemeral=True)
                return
            self.value = True
            self.stop()
            await interaction.response.defer()

        @discord.ui.button(label="🥺", style=discord.ButtonStyle.red, custom_id="btn_cancel_kick")
        async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
            if interaction.user.id != self.author_id:
                await interaction.response.send_message("❌ Bu butona sadece komutu kullanan kişi basabilir!", ephemeral=True)
                return
            self.value = False
            self.stop()
            await interaction.response.defer()

    confirm_text = (
        "Ay, hüüü... bunu ya-yapıyosun ama... 🥺👉👈 bunu yapai'ken sa-sahibim bana kı'zmayacak di' mi, emin misinnn? 🥺🐾\n\n"
        "Ben sadeceee sen istedin diye yapıyoiuuu'm ki, ben aslı'nda hiç böyle şeylei yapma'm, çok utangacııı'm zateeen... 👉👈🫣 Beni de koiui'sun di' mi, owwo? 💕✨"
    )

    confirm_embed = discord.Embed(
        title="🥺 Emin Misinnn? 👉👈",
        description=confirm_text,
        color=0xFFB6C1
    )

    view = ModerationConfirmView(ctx.author.id)
    confirm_msg = await ctx.send(embed=confirm_embed, view=view)

    await view.wait()

    if view.value is True:
        try:
            await member.kick(reason=reason)
            embed = discord.Embed(
                description=f"👢 {member.mention} (`{member.id}`) sunucudan **atıldı**.\n📝 Sebep: {reason}",
                color=0xFF8800
            )
            await ctx.send(embed=embed)
            if ctx.guild:
                try:
                    await ctx.message.delete()
                except Exception:
                    pass
            try:
                await confirm_msg.delete()
            except Exception:
                pass
            print(f"👢 {ctx.author} → {member} atıldı. Sebep: {reason}", flush=True)
        except discord.Forbidden:
            await ctx.send("❌ Botun bu kişiyi atma yetkisi yok!")
        except Exception as e:
            await ctx.send(f"❌ Hata: {e}")
    else:
        try:
            await confirm_msg.delete()
        except Exception:
            pass
        cancel_embed = discord.Embed(
            description="🥺 İşlem iptal edildi, sahibim kızmayacak yaşasınnn! ✨",
            color=0x57F287
        )
        await ctx.send(embed=cancel_embed, delete_after=6)


@bot.command(name="nuke")
async def nuke(ctx):
    """Bulunulan kanalı klonlar, eskisini siler ve tüm mesajları sıfırlar."""
    # Sadece yetkili veya üstü (Allah, Kurucu, .yt) kullanabilir
    if not is_full_authorized(ctx.author.id):
        if ctx.guild:
            try:
                await ctx.message.delete()
            except Exception:
                pass
        return

    channel = ctx.channel
    if not isinstance(channel, discord.TextChannel):
        await ctx.send("❌ Bu komut yalnızca metin kanallarında kullanılabilir!")
        return

    # Welcome ve Exit kanalları koruması: Sadece Allah nuke atabilir
    cfg = load_config()
    w_id = cfg.get("welcome_channel_id")
    e_id = cfg.get("exit_channel_id")
    if (w_id and str(channel.id) == str(w_id)) or (e_id and str(channel.id) == str(e_id)):
        if not is_allah(ctx.author.id):
            await ctx.send("Bu kanalı sadece Allah nukeleyebilir!")
            return

    # Onay Görünümü
    class NukeConfirmView(discord.ui.View):
        def __init__(self, author_id: int):
            super().__init__(timeout=30)
            self.author_id = author_id
            self.value = None

        @discord.ui.button(label="emin misin", style=discord.ButtonStyle.green, custom_id="btn_confirm_nuke")
        async def confirm_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
            if interaction.user.id != self.author_id:
                await interaction.response.send_message("Bu butona sadece komutu kullanan yetkili basabilir!", ephemeral=True)
                return
            self.value = True
            self.stop()
            await interaction.response.defer()

        @discord.ui.button(label="iptal", style=discord.ButtonStyle.red, custom_id="btn_cancel_nuke")
        async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
            if interaction.user.id != self.author_id:
                await interaction.response.send_message("Bu butona sadece komutu kullanan yetkili basabilir!", ephemeral=True)
                return
            self.value = False
            self.stop()
            await interaction.response.defer()

    confirm_embed = discord.Embed(
        title="Kanal Sıfırlama (Nuke)",
        description=f"**{channel.mention}** kanalı sıfırlanacak ve içindeki tüm mesajlar silinecektir.\nDevam etmek istediğinden emin misin?",
        color=0xFF4444
    )

    view = NukeConfirmView(ctx.author.id)
    confirm_msg = await ctx.send(embed=confirm_embed, view=view)
    await view.wait()

    if view.value is True:
        try:
            # 1. Kanalı klonla
            old_position = channel.position
            new_channel = await channel.clone(reason=f"Nuke komutu ile sıfırlandı ({ctx.author})")
            await new_channel.edit(position=old_position)

            # 2. Config içinde bu kanal kayıtlıysa yeni ID ile güncelle
            cfg = load_config()
            cfg_changed = False
            old_id_str = str(channel.id)
            new_id_str = str(new_channel.id)

            for key in ("welcome_channel_id", "exit_channel_id", "log_channel_id", "rules_channel_id"):
                if cfg.get(key) == old_id_str:
                    cfg[key] = new_id_str
                    cfg_changed = True

            if cfg_changed:
                save_config(cfg)

            # 3. Snapshot güncellemesi
            snaps = load_snapshots()
            snaps[new_id_str] = {
                "name": new_channel.name,
                "type": "voice" if isinstance(new_channel, discord.VoiceChannel) else "text",
                "guild_id": new_channel.guild.id,
                "category_id": new_channel.category_id,
                "position": new_channel.position,
                "bitrate": getattr(new_channel, "bitrate", 64000),
                "user_limit": getattr(new_channel, "user_limit", 0)
            }
            snaps.pop(old_id_str, None)
            save_snapshots(snaps)

            # 4. Eğer kanal sunucunun kurallar, güncellemeler veya sistem kanalı ise sunucu ayarlarını yeni kanala geçir
            guild = channel.guild
            guild_edit_kwargs = {}
            if guild.rules_channel and guild.rules_channel.id == channel.id:
                guild_edit_kwargs["rules_channel"] = new_channel
            if guild.public_updates_channel and guild.public_updates_channel.id == channel.id:
                guild_edit_kwargs["public_updates_channel"] = new_channel
            if guild.system_channel and guild.system_channel.id == channel.id:
                guild_edit_kwargs["system_channel"] = new_channel

            if guild_edit_kwargs:
                try:
                    await guild.edit(**guild_edit_kwargs, reason=f"Nuke sonrası topluluk kanalı güncellendi ({ctx.author})")
                except Exception as ge:
                    print(f"⚠️ Sunucu kanal ayarı güncellenemedi: {ge}", flush=True)

            # 5. Eski kanalı sil (Topluluk engeli verirse klonu silip eski kanalı temizle/purge yap)
            try:
                await channel.delete(reason=f"Nuke işlemi tamamlandı. Yapan: {ctx.author}")
            except discord.HTTPException as del_err:
                if del_err.code == 50074:
                    # Topluluk gereksinimi nedeniyle silinemedi, yeni açılan klonu kaldırıp mevcut kanalı purge et
                    await new_channel.delete(reason="Topluluk kanalı silinemediği için klon iptal edildi.")
                    new_channel = channel
                    await channel.purge(limit=1000)
                else:
                    raise del_err

            # 6. Tüm izinleri yeni kanala da anında senkronize et
            await sync_voice_permissions(new_channel.guild)

            # 6. Yeni kanala sade nuke mesajı gönder (Görselsiz/Embedsiz düz metin)
            await new_channel.send(f"{ctx.author.mention} kanala nuke attı")

            # 7. Denetim logu gönder
            log_embed = discord.Embed(
                title="Kanal Sıfırlandı (Nuke)",
                description=(
                    f"**Kanal:** #{new_channel.name} (`{new_channel.id}`)\n"
                    f"**Yetkili:** {ctx.author.mention} (`{ctx.author.id}`)"
                ),
                color=0xFF0000,
                timestamp=discord.utils.utcnow()
            )
            await send_audit_log(new_channel.guild, log_embed)
            print(f"[Nuke] #{channel.name} kanalı {ctx.author} tarafından sıfırlandı ve tüm yetkiler senkronize edildi.", flush=True)

        except discord.Forbidden:
            await ctx.send("Botun bu kanalı sıfırlamak için gerekli yetkisi yok!")
        except Exception as e:
            await ctx.send(f"Nuke işlemi sırasında hata oluştu: {e}")
    else:
        try:
            await confirm_msg.delete()
        except Exception:
            pass
        cancel_embed = discord.Embed(
            description="Nuke işlemi iptal edildi.",
            color=0x57F287
        )
@bot.command(name="sil", aliases=["clear", "purge", "temizle"])
async def sil_komutu(ctx, adet: int = None):
    """
    Belirtilen miktarda mesajı anında sormadan siler.
    Kullanım: .sil <sayı>
    """
    if not is_authorized(ctx.author.id) and not ctx.author.guild_permissions.manage_messages:
        if ctx.guild:
            try:
                await ctx.message.delete()
            except Exception:
                pass
        return

    # Welcome ve Exit kanallarında SADECE ALLAH mesaj silebilir
    cfg = load_config()
    w_id = cfg.get("welcome_channel_id")
    e_id = cfg.get("exit_channel_id")
    if (w_id and str(ctx.channel.id) == str(w_id)) or (e_id and str(ctx.channel.id) == str(e_id)):
        if not is_allah(ctx.author.id):
            await ctx.send("Bu kanalda sadece Allah mesaj silebilir!", delete_after=5)
            return

    if adet is None or adet <= 0:
        await ctx.send("❌ Lütfen silinecek mesaj sayısını girin! Örnek: `.sil 10`", delete_after=5)
        return

    # En fazla tek seferde 1000 mesaj silinebilir (Discord sınırı için döngüsel)
    limit = min(adet, 1000)

    try:
        # Komut mesajının kendisi dahil silinecek
        deleted = await ctx.channel.purge(limit=limit + 1)
        # Komut mesajı hariç gerçek silinen mesaj sayısı
        deleted_count = max(len(deleted) - 1, 0)

        # Sade bilgilendirme mesajı (emojisiz, kalıcı)
        await ctx.channel.send(f"{ctx.author.mention} **{deleted_count}** adet mesaj sildi.")

        # Denetim loguna kaydet
        log_embed = discord.Embed(
            title="🧹 Mesajlar Silindi (.sil)",
            description=(
                f"**Yetkili:** {ctx.author.mention} (`{ctx.author.id}`)\n"
                f"**Kanal:** {ctx.channel.mention} (`#{ctx.channel.name}`)\n"
                f"**Silinen Mesaj Sayısı:** `{deleted_count}`"
            ),
            color=0xFEE75C,
            timestamp=discord.utils.utcnow()
        )
        await send_audit_log(ctx.guild, log_embed)
        print(f"🧹 [Mesaj Silme] #{ctx.channel.name} kanalında {ctx.author} tarafından {deleted_count} mesaj silindi.", flush=True)

    except discord.Forbidden:
        await ctx.send("❌ Botun bu kanalda mesajları silmek için `Mesajları Yönet` yetkisi yok!", delete_after=5)
    except Exception as e:
        await ctx.send(f"❌ Mesajlar silinirken hata oluştu: {e}", delete_after=5)


# ──────────────────────────────────────────────
# SPOTIFY & MÜZİK SİSTEMİ
# ──────────────────────────────────────────────
import urllib.request
import urllib.parse
import re
from yt_dlp import YoutubeDL

# Sunucu bazlı müzik kuyruğu: {guild_id: {"queue": list[dict], "current": dict, "loop": bool}}
music_queues = {}

YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'scsearch',
    'source_address': '0.0.0.0',
}

import shutil

# FFmpeg yolunu otomatik bul (Linux sistem ffmpeg veya Windows PATH / WinGet)
FFMPEG_EXE = shutil.which("ffmpeg")
if not FFMPEG_EXE:
    winget_ffmpeg = r"C:\Users\biber\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.1-full_build\bin\ffmpeg.exe"
    if os.path.exists(winget_ffmpeg):
        FFMPEG_EXE = winget_ffmpeg
    else:
        FFMPEG_EXE = "ffmpeg"

# Kesintisiz Canlı Yayın & Yüksek Kaliteli Ses Akışı
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

ytdl = YoutubeDL(YTDL_OPTIONS)


def get_spotify_tracks(spotify_url: str) -> list[str]:
    """Spotify playlist/track/album sayfasından tüm şarkı ve sanatçı isimlerini %100 doğrulukla çeker."""
    tracks = []
    try:
        # Spotify linkini normalize et
        clean_url = spotify_url.split("?")[0].strip()
        # Embed URL'e çevir
        if "open.spotify.com/embed/" not in clean_url:
            embed_url = clean_url.replace("open.spotify.com/", "open.spotify.com/embed/")
        else:
            embed_url = clean_url

        req = urllib.request.Request(
            embed_url,
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            html = response.read().decode('utf-8')

        # 1. Embed JSON __NEXT_DATA__ içinden tam listeyi çek
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html)
        if m:
            data = json.loads(m.group(1))
            entity = data.get("props", {}).get("pageProps", {}).get("state", {}).get("data", {}).get("entity", {})
            
            # Playlist veya Album ise trackList vardır
            track_list = entity.get("trackList", [])
            if track_list:
                for item in track_list:
                    title = item.get("title", "")
                    subtitle = item.get("subtitle", "")
                    if title:
                        query = f"{subtitle} - {title}".strip(" -") if subtitle else title
                        tracks.append(query)
            
            # Tekil şarkı (Track) ise
            elif entity.get("name") or entity.get("title"):
                title = entity.get("title") or entity.get("name")
                artists = entity.get("artists", [])
                artist_names = ", ".join([a.get("name", "") for a in artists if a.get("name")])
                query = f"{artist_names} - {title}".strip(" -") if artist_names else title
                tracks.append(query)

        # 2. Eğer Next data bulunamazsa resmi Spotify oEmbed API ile başlığı al
        if not tracks:
            oembed_url = f"https://open.spotify.com/oembed?url={urllib.parse.quote(clean_url)}"
            o_req = urllib.request.Request(oembed_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(o_req, timeout=5) as o_res:
                o_data = json.loads(o_res.read().decode('utf-8'))
                if o_data.get("title"):
                    tracks.append(o_data["title"])

    except Exception as e:
        print(f"⚠️ Spotify ayrıştırma hatası: {e}", flush=True)

    return tracks


# Sunucu bazlı müzik bekleme görevi: {guild_id: asyncio.Task}
music_idle_tasks = {}


async def delayed_return_home(guild: discord.Guild, delay_seconds: int = 180):
    """Müzik bittiğinde 3 dakika bekler. Yeni istek gelmezse kendi 7/24 ses odasına döner."""
    try:
        await asyncio.sleep(delay_seconds)
        g_data = music_queues.get(guild.id)
        if g_data and not g_data.get("queue") and not g_data.get("current"):
            g_data["active_user_id"] = None
            vc = guild.voice_client
            if vc and vc.is_connected():
                home_ch = guild.get_channel(STAY_VOICE_CHANNEL_ID)
                if home_ch and vc.channel.id != STAY_VOICE_CHANNEL_ID:
                    await vc.move_to(home_ch)
                    print(f"🏠 [Ses Odası] 3 dakika boyunca yeni şarkı istenmediği için bot kendi odasına ({home_ch.name}) geri döndü.", flush=True)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"⚠️ Kendi odasına dönerken hata: {e}", flush=True)
    finally:
        music_idle_tasks.pop(guild.id, None)


async def play_next_song(guild: discord.Guild):
    """Kuyruktaki sıradaki şarkıyı çalar. Kuyruk bittiğinde 3 dakika bekleyip varsayılan odaya geri döner."""
    g_data = music_queues.get(guild.id)
    if not g_data or not g_data["queue"]:
        if g_data:
            g_data["current"] = None

        # Şarkı bittiğinde 3 dakikalık bekleme zamanlayıcısını başlat
        if guild.id in music_idle_tasks:
            music_idle_tasks[guild.id].cancel()
        music_idle_tasks[guild.id] = asyncio.create_task(delayed_return_home(guild, delay_seconds=180))
        return

    # Eğer bekleme zamanlayıcısı varsa iptal et
    if guild.id in music_idle_tasks:
        music_idle_tasks[guild.id].cancel()
        music_idle_tasks.pop(guild.id, None)

    vc = guild.voice_client
    if not vc or not vc.is_connected():
        return

    track_query = g_data["queue"].pop(0)
    g_data["current"] = track_query

    try:
        loop = asyncio.get_event_loop()
        
        # Doğrudan arama (Önce SoundCloud, eğer YouTube linki ise YouTube)
        if "youtube.com" in track_query or "youtu.be" in track_query:
            search_target = track_query
        elif "soundcloud.com" in track_query or "http" in track_query:
            search_target = track_query
        else:
            search_target = f"scsearch:{track_query}"

        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(search_target, download=False))
        
        info = None
        if data:
            if 'entries' in data and len(data['entries']) > 0:
                info = data['entries'][0]
            elif 'url' in data:
                info = data

        if not info or not info.get('url'):
            # Eğer scsearch bulamazsa ytsearch dene
            yt_target = f"ytsearch:{track_query}"
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(yt_target, download=False))
            if data and 'entries' in data and len(data['entries']) > 0:
                info = data['entries'][0]
            elif data and 'url' in data:
                info = data

        if not info or not info.get('url'):
            raise RuntimeError(f"Ses kaynağı bulunamadı: {track_query}")

        url = info['url']
        title = info.get('title', track_query)
        g_data["current"] = title

        def after_playing(error):
            if error:
                print(f"⚠️ Çalma hatası: {error}", flush=True)
            asyncio.run_coroutine_threadsafe(play_next_song(guild), bot.loop)

        # Discord'un en kararlı ve kesintisiz native ses kaynağı: FFmpegOpusAudio
        source = await discord.FFmpegOpusAudio.from_probe(
            url,
            executable=FFMPEG_EXE,
            before_options='-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            options='-vn'
        )
        vc.play(source, after=after_playing)
        print(f"🎵 [Müzik] Çalıyor: {title}", flush=True)

    except Exception as e:
        print(f"⚠️ Şarkı yüklenemedi ({track_query}): {e}", flush=True)
        await play_next_song(guild)


@bot.command(name="oynat", aliases=["play", "p"])
async def oynat_komutu(ctx, *, sorgu: str = None):
    """
    Spotify linki, YouTube linki veya şarkı adı çalar.
    Kullanıcının bulunduğu ses kanalına gelir, müzik bitince 3 dakika bekler ve kendi odasına geri döner.
    """
    if not is_authorized(ctx.author.id):
        return

    if not sorgu:
        await ctx.send("Lütfen bir şarkı adı, Spotify veya YouTube linki girin! Örnek: `.oynat <link>`")
        return

    # Kullanıcının ses kanalında olup olmadığını kontrol et
    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send("Önce bir ses kanalına girmelisin!")
        return

    user_channel = ctx.author.voice.channel

    # Eğer geri dönüş için 3 dakikalık zamanlayıcı çalışıyorsa iptal et
    if ctx.guild.id in music_idle_tasks:
        music_idle_tasks[ctx.guild.id].cancel()
        music_idle_tasks.pop(ctx.guild.id, None)

    if ctx.guild.id not in music_queues:
        music_queues[ctx.guild.id] = {"queue": [], "current": None, "loop": False, "active_user_id": None}

    g_data = music_queues[ctx.guild.id]
    active_uid = g_data.get("active_user_id")

    # Botu şu an başka biri kullanıyor mu kontrolü (Allah hariç herkes kilitlenir)
    vc = ctx.guild.voice_client
    is_busy = (vc and (vc.is_playing() or vc.is_paused()) and active_uid and active_uid != ctx.author.id and not is_allah(ctx.author.id))
    if is_busy:
        await ctx.send(f"Şu anda botu başka biri (<@{active_uid}>) kullanıyor!")
        return

    # Botu komutu kullanan kullanıcının ses kanalına taşı/bağla
    if not vc or not vc.is_connected():
        await user_channel.connect(self_deaf=True, self_mute=False)
        vc = ctx.guild.voice_client
    elif vc.channel.id != user_channel.id:
        await vc.move_to(user_channel)

    g_data["active_user_id"] = ctx.author.id
    g_queue = g_data["queue"]

    # 1. Spotify linki mi?
    if "open.spotify.com" in sorgu:
        msg = await ctx.send("Spotify taranıyor...")
        tracks = get_spotify_tracks(sorgu)
        if not tracks:
            g_queue.append(sorgu)
            await msg.edit(content=f"Sıraya eklendi: **{sorgu}**")
        elif len(tracks) == 1:
            g_queue.append(tracks[0])
            await msg.edit(content=f"Sıraya eklendi: **{tracks[0]}**")
        else:
            g_queue.extend(tracks)
            preview = ", ".join(tracks[:3])
            more = f" ve {len(tracks) - 3} şarkı daha" if len(tracks) > 3 else ""
            await msg.edit(content=f"**{len(tracks)}** adet şarkı sıraya eklendi!\n`{preview}{more}`")

        if not vc.is_playing() and not vc.is_paused():
            await play_next_song(ctx.guild)

    # 2. YouTube linki mi?
    elif "youtube.com" in sorgu or "youtu.be" in sorgu:
        msg = await ctx.send("YouTube taranıyor...")
        try:
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(sorgu, download=False))
            if 'entries' in data:
                # YouTube Playlist
                entries = data['entries']
                for entry in entries:
                    if entry:
                        g_queue.append(entry.get('webpage_url') or entry.get('title'))
                await msg.edit(content=f"**{len(entries)}** adet şarkı YouTube Playlist'inden sıraya eklendi!")
            else:
                title = data.get('title', sorgu)
                g_queue.append(sorgu)
                await msg.edit(content=f"Sıraya eklendi: **{title}**")
        except Exception:
            g_queue.append(sorgu)
            await msg.edit(content=f"Sıraya eklendi: **{sorgu}**")

        if not vc.is_playing() and not vc.is_paused():
            await play_next_song(ctx.guild)

    # 3. Düz isim araması -> Butonlu Seçenek Sun (YouTube / Spotify)
    else:
        class PlatformSelectView(discord.ui.View):
            def __init__(self, author_id: int, query_text: str):
                super().__init__(timeout=30)
                self.author_id = author_id
                self.query_text = query_text

            @discord.ui.button(label="YouTube", style=discord.ButtonStyle.red, custom_id="btn_play_yt")
            async def yt_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != self.author_id:
                    await interaction.response.send_message("Bu seçeneği sadece komutu kullanan seçebilir!", ephemeral=True)
                    return
                for child in self.children:
                    child.disabled = True
                await interaction.response.edit_message(content=f"Sıraya eklendi: **{self.query_text}**", view=self)
                g_queue.append(self.query_text)
                if not vc.is_playing() and not vc.is_paused():
                    await play_next_song(ctx.guild)

            @discord.ui.button(label="Spotify", style=discord.ButtonStyle.green, custom_id="btn_play_sp")
            async def sp_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != self.author_id:
                    await interaction.response.send_message("Bu seçeneği sadece komutu kullanan seçebilir!", ephemeral=True)
                    return
                for child in self.children:
                    child.disabled = True
                await interaction.response.edit_message(content=f"Sıraya eklendi: **{self.query_text}**", view=self)
                g_queue.append(self.query_text)
                if not vc.is_playing() and not vc.is_paused():
                    await play_next_song(ctx.guild)

        view = PlatformSelectView(ctx.author.id, sorgu)
        await ctx.send(f"**{sorgu}** nereden çalınsın?", view=view)


@bot.command(name="atla", aliases=["skip", "s", "gec"])
async def atla_komutu(ctx):
    """Çalan şarkıyı atlar."""
    if not is_authorized(ctx.author.id):
        return
    g_data = music_queues.get(ctx.guild.id)
    active_uid = g_data.get("active_user_id") if g_data else None
    if active_uid and active_uid != ctx.author.id and not is_allah(ctx.author.id):
        await ctx.send(f"Şu anda botu başka biri (<@{active_uid}>) kullanıyor!")
        return

    vc = ctx.guild.voice_client
    if vc and vc.is_playing():
        vc.stop()
        await ctx.send("Şarkı atlandı.")
    else:
        await ctx.send("Şu anda çalan bir şarkı yok.")


@bot.command(name="durdur", aliases=["pause", "dur"])
async def durdur_komutu(ctx):
    """Müziği duraklatır."""
    if not is_authorized(ctx.author.id):
        return
    g_data = music_queues.get(ctx.guild.id)
    active_uid = g_data.get("active_user_id") if g_data else None
    if active_uid and active_uid != ctx.author.id and not is_allah(ctx.author.id):
        await ctx.send(f"Şu anda botu başka biri (<@{active_uid}>) kullanıyor!")
        return

    vc = ctx.guild.voice_client
    if vc and vc.is_playing():
        vc.pause()
        await ctx.send("Müzik duraklatıldı.")


@bot.command(name="devam", aliases=["resume"])
async def devam_komutu(ctx):
    """Duraklatılan müziği devam ettirir."""
    if not is_authorized(ctx.author.id):
        return
    g_data = music_queues.get(ctx.guild.id)
    active_uid = g_data.get("active_user_id") if g_data else None
    if active_uid and active_uid != ctx.author.id and not is_allah(ctx.author.id):
        await ctx.send(f"Şu anda botu başka biri (<@{active_uid}>) kullanıyor!")
        return

    vc = ctx.guild.voice_client
    if vc and vc.is_paused():
        vc.resume()
        await ctx.send("Müzik devam ediyor.")


@bot.command(name="sarki", aliases=["şarkı", "muzik", "müzik", "music", "mhelp"])
async def sarki_yardim_komutu(ctx):
    """Müzik komutları listesini sade ve şık bir embed ile gösterir."""
    embed = discord.Embed(
        title="🎵 Müzik Komutları",
        description=(
            "**`.play <şarkı / link>`** (veya `.p`, `.oynat`)\n"
            "↳ Şarkı adı, YouTube veya Spotify linki çalar.\n\n"
            "**`.atla`** (veya `.skip`, `.s`)\n"
            "↳ Çalan şarkıyı geçer, sıradakine atlar.\n\n"
            "**`.durdur`** (veya `.pause`, `.dur`)\n"
            "↳ Çalan müziği duraklatır.\n\n"
            "**`.devam`** (veya `.resume`)\n"
            "↳ Duraklatılan müziği devam ettirir.\n\n"
            "**`.kuyruk`** (veya `.queue`, `.q`, `.sıra`, `.liste`)\n"
            "↳ Sıradaki ve çalan şarkıları sayfalı gösterir.\n\n"
            "**`.kuyruktemizle`** (veya `.clearqueue`)\n"
            "↳ Müzik kuyruğunu tamamen temizler."
        ),
        color=0x1DB954
    )
    embed.set_footer(text="Spotify & YouTube & SoundCloud Destekli • Prefix: . veya !")
    await ctx.send(embed=embed)


@bot.command(name="kuyruk", aliases=["queue", "q", "liste", "sira", "sıra", "calan", "çalan"])
async def kuyruk_komutu(ctx):
    """
    Sıradaki ve şu an çalan şarkıları sayfalama butonlarıyla gösterir.
    Kullanım: .kuyruk veya .sıra
    """
    if not is_authorized(ctx.author.id):
        return
    g_data = music_queues.get(ctx.guild.id)
    if not g_data or (not g_data.get("current") and not g_data.get("queue")):
        await ctx.send("Kuyrukta şarkı yok.")
        return

    cur = g_data.get("current", "Yok")
    q_list = g_data.get("queue", [])
    active_uid = g_data.get("active_user_id")
    user_str = f"<@{active_uid}>" if active_uid else "Bilinmiyor"

    # Sayfalama Mantığı (Her sayfada 10 şarkı)
    items_per_page = 10
    total_pages = max(1, (len(q_list) + items_per_page - 1) // items_per_page)

    def generate_queue_embed(page: int) -> discord.Embed:
        start_idx = page * items_per_page
        end_idx = start_idx + items_per_page
        page_items = q_list[start_idx:end_idx]

        desc = f"**Şu An Çalan:**\n🎵 `{cur}`\n*(Dinleyen: {user_str})*\n\n"
        if not q_list:
            desc += "*(Sırada bekleyen başka şarkı yok)*"
        else:
            desc += f"**Sıradaki Şarkılar ({len(q_list)}):**\n"
            for i, item in enumerate(page_items, start=start_idx + 1):
                desc += f"`{i}.` {item}\n"

        embed = discord.Embed(
            title="🎶 Müzik Çalma Sırası",
            description=desc,
            color=0x57F287
        )
        embed.set_footer(text=f"Sayfa {page + 1}/{total_pages} • Toplam {len(q_list)} şarkı")
        return embed

    class QueuePaginationView(discord.ui.View):
        def __init__(self, author_id: int):
            super().__init__(timeout=60)
            self.author_id = author_id
            self.page = 0
            self.update_buttons()

        def update_buttons(self):
            self.prev_btn.disabled = (self.page == 0)
            self.next_btn.disabled = (self.page >= total_pages - 1)

        @discord.ui.button(label="◀ Önceki", style=discord.ButtonStyle.secondary, custom_id="btn_queue_prev")
        async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
            if interaction.user.id != self.author_id:
                await interaction.response.send_message("Bu butonları sadece komutu yazan kullanabilir!", ephemeral=True)
                return
            if self.page > 0:
                self.page -= 1
                self.update_buttons()
                await interaction.response.edit_message(embed=generate_queue_embed(self.page), view=self)

        @discord.ui.button(label="Sonraki ▶", style=discord.ButtonStyle.secondary, custom_id="btn_queue_next")
        async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
            if interaction.user.id != self.author_id:
                await interaction.response.send_message("Bu butonları sadece komutu yazan kullanabilir!", ephemeral=True)
                return
            if self.page < total_pages - 1:
                self.page += 1
                self.update_buttons()
                await interaction.response.edit_message(embed=generate_queue_embed(self.page), view=self)

    if total_pages > 1:
        view = QueuePaginationView(ctx.author.id)
        await ctx.send(embed=generate_queue_embed(0), view=view)
    else:
        await ctx.send(embed=generate_queue_embed(0))


@bot.command(name="kuyruktemizle", aliases=["clearqueue", "qclear", "siratemizle", "sıratemizle"])
async def kuyruk_temizle_komutu(ctx):
    """Müzik kuyruğunu tamamen temizler."""
    if not is_authorized(ctx.author.id):
        return
    g_data = music_queues.get(ctx.guild.id)
    active_uid = g_data.get("active_user_id") if g_data else None
    if active_uid and active_uid != ctx.author.id and not is_allah(ctx.author.id):
        await ctx.send(f"Şu anda botu başka biri (<@{active_uid}>) kullanıyor!")
        return

    if ctx.guild.id in music_queues:
        music_queues[ctx.guild.id]["queue"].clear()
    await ctx.send("Kuyruk tamamen temizlendi.")


if __name__ == "__main__":
    if not TOKEN or TOKEN == "BOT_TOKENINIZI_BURAYA_YAZIN":
        print("❌ HATA: Lütfen .env dosyasını açıp geçerli bir DISCORD_TOKEN girin!")
    elif OWNER_ID == 0:
        print("❌ HATA: Lütfen .env dosyasında OWNER_ID'yi kendi Discord ID'ne ayarla!")
    else:
        bot.run(TOKEN)
