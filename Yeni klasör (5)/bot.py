import os
import sys
import subprocess

# ──────────────────────────────────────────────
# GEREKLİ KÜTÜPHANELERİ OTOMATİK KONTROL ET VE İNDİR
# ──────────────────────────────────────────────
REQUIRED_PACKAGES = [
    ("discord", "discord.py>=2.3.2"),
    ("dotenv", "python-dotenv>=1.0.1"),
    ("nacl", "PyNaCl>=1.5.0"),
    ("yt_dlp", "yt-dlp>=2025.1.26"),
    ("spotipy", "spotipy>=2.24.0"),
    ("aiohttp", "aiohttp>=3.9.5")
]

for import_name, install_pkg in REQUIRED_PACKAGES:
    try:
        __import__(import_name)
    except ImportError:
        print(f"📦 '{install_pkg}' kütüphanesi eksik, otomatik kuruluyor...", flush=True)
        subprocess.check_call([sys.executable, "-m", "pip", "install", install_pkg])

import json
import time
import re
import asyncio
import discord
from discord import app_commands
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
    """Tek ve mutlak bot yöneticisi mi?"""
    return user_id == ALLAH_ID


def is_kurucu(user_id: int) -> bool:
    """Eski uyumluluk için: Sadece Allah"""
    return is_allah(user_id)


def is_full_authorized(user_id: int) -> bool:
    """Eski uyumluluk için: Sadece Allah"""
    return is_allah(user_id)


def is_sesyt(user_id: int) -> bool:
    """Ses yetkisi var mı? (Allah + .sesyt)"""
    if is_allah(user_id):
        return True
    return user_id in load_sesyt()


def is_authorized(user_id: int) -> bool:
    """Herhangi bir yetkisi var mı?"""
    return is_sesyt(user_id)


def member_has_perm(member: discord.Member) -> bool:
    """Üyenin botta veya sunucuda herhangi bir yetkisi/rolü var mı?"""
    if is_authorized(member.id) or member.guild_permissions.administrator:
        return True
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
    """Sade katıldı embed'i (Renksiz, şeritsiz, butonsuz)."""
    embed = discord.Embed(
        description=f"{member.mention} sunucuya katıldı"
    )
    embed.set_thumbnail(url=member.display_avatar.url)
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
    """Sade ayrıldı embed'i (Renksiz, şeritsiz)."""
    embed = discord.Embed(
        description=f"{member.mention} sunucudan ayrıldı"
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    return embed


async def lock_and_grant_channel(channel: discord.TextChannel):
    """
    Welcome Kanalı:
    Kanalı kilitler (@everyone ve yetkililer dahil kimse mesaj yazamaz, butonla kayıt ve bot mesajı için temiz kalır),
    Herkes sadece görebilir ve okuyabilir.
    """
    owner_member = channel.guild.get_member(ALLAH_ID)
    if owner_member:
        overwrite = channel.overwrites_for(owner_member)
        overwrite.view_channel = True
        overwrite.send_messages = True
        overwrite.read_message_history = True
        overwrite.manage_messages = True
        try:
            await channel.set_permissions(owner_member, overwrite=overwrite)
        except Exception as e:
            print(f"⚠️ Kanal yetkisi verilemedi ({channel.name} -> {owner_member.name}): {e}", flush=True)


async def lock_and_grant_private_channel(channel: discord.TextChannel):
    """
    ÖZEL Kanallar (Exit / Log vb.):
    @everyone için kanalı GİZLER (view_channel = False).
    Sadece bot sahibine (ALLAH_ID) tam erişim verir.
    """
    # 1. @everyone için tamamen görünmez yap
    everyone_overwrite = channel.overwrites_for(channel.guild.default_role)
    everyone_overwrite.view_channel = False
    everyone_overwrite.send_messages = False
    everyone_overwrite.read_message_history = False
    try:
        await channel.set_permissions(channel.guild.default_role, overwrite=everyone_overwrite)
    except Exception as e:
        print(f"⚠️ Özel kanalda @everyone kısıtlanamadı: {e}", flush=True)

    # 2. Bot sahibine tam erişim ver
    owner_member = channel.guild.get_member(ALLAH_ID)
    if owner_member:
        overwrite = channel.overwrites_for(owner_member)
        overwrite.view_channel = True
        overwrite.send_messages = True
        overwrite.read_message_history = True
        overwrite.manage_messages = True
        try:
            await channel.set_permissions(owner_member, overwrite=overwrite)
        except Exception as e:
            print(f"⚠️ Özel kanal yetkisi verilemedi ({channel.name} -> {owner_member.name}): {e}", flush=True)


async def configure_unregistered_role_permissions(guild: discord.Guild):
    """
    Kayıtsız Rolü (1544413431409410058) ve @everyone Varsayılan Kanal İzinleri:
    - Bot kapalı (offline) olsa bile permsiz insanlar:
      * HİÇBİR metin kanalını göremez (Sadece kurallar ve welcome açık kalır).
      * Ses kanallarını görebilir (view_channel=True) ama HİÇBİRİNE KATILAMAZ (connect=False).
    - Bot koruması olmasa dahi bu ayarlar doğrudan kanal izin tablosuna (overwrite) işlendiği için bot kapalıyken de %100 aktiftir.
    """
    unreg_role = guild.get_role(UNREGISTERED_ROLE_ID)
    everyone_role = guild.default_role

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

    # 1. Kategoriler için izinler:
    # @everyone ve Kayıtsız rolü için kategoriyi görebilir ama içindeki kilitli metin kanallarını göremez
    for category in guild.categories:
        try:
            for role in (unreg_role, everyone_role):
                if role:
                    cat_over = category.overwrites_for(role)
                    cat_over.view_channel = True
                    await category.set_permissions(role, overwrite=cat_over)
        except Exception:
            pass

    # 2. Metin kanalları için izinler:
    # Permsiz / yetkisiz insanlar (@everyone ve kayıtsızlar) sadece welcome/rules görebilir, diğer hiçbir metin kanalını göremez!
    for channel in guild.text_channels:
        try:
            for role in (unreg_role, everyone_role):
                if role:
                    over = channel.overwrites_for(role)
                    if channel.id in allowed_channel_ids:
                        over.view_channel = True
                        over.read_message_history = True
                        over.send_messages = False
                        over.add_reactions = False
                    else:
                        # Hiçbir kanalı göremez
                        over.view_channel = False
                        over.send_messages = False
                    await channel.set_permissions(role, overwrite=over)
        except Exception:
            pass

    # 3. Ses kanalları için izinler:
    # Kayıtsız permi olanlar ve @everyone boş ses kanallarını GÖREMEZ (view_channel=False).
    # İçinde bot veya üye olan ses kanallarını GÖRÜR (view_channel=True) ama KATILAMAZ (connect=False).
    for channel in guild.voice_channels:
        try:
            has_someone = (len(channel.members) > 0)
            for role in (unreg_role, everyone_role):
                if role:
                    over = channel.overwrites_for(role)
                    over.view_channel = has_someone
                    over.connect = False
                    over.speak = False
                    await channel.set_permissions(role, overwrite=over)
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

    owner_id = ALLAH_ID
    sesyt_ids = set(load_sesyt())
    all_voice_auths = {owner_id} | sesyt_ids

    # Kategorileri kontrol et (Sadece bot sahibi kategori yönetebilir)
    owner_member = guild.get_member(owner_id)
    if owner_member:
        for category in guild.categories:
            cat_over = category.overwrites_for(owner_member)
            old_pair = cat_over.pair()
            cat_over.manage_channels = True
            if cat_over.pair() != old_pair:
                try:
                    await category.set_permissions(owner_member, overwrite=cat_over)
                except Exception:
                    pass

    # Ses kanallarını denetle
    for channel in guild.voice_channels:
        # Eski yetkililerden kalan ve artık yetkili olmayan üyelerin özel izinlerini temizle
        for target, overwrite in list(channel.overwrites.items()):
            if isinstance(target, discord.Member):
                if target.id not in all_voice_auths and not target.bot:
                    try:
                        await channel.set_permissions(target, overwrite=None)
                    except Exception:
                        pass

        for uid in all_voice_auths:
            member = guild.get_member(uid)
            if member:
                overwrite = channel.overwrites_for(member)
                old_pair = overwrite.pair()
                # .sesyt için mute, deafen, move (sağ tık yetkileri)
                overwrite.mute_members = True
                overwrite.deafen_members = True
                overwrite.move_members = True
                
                # Sadece bot sahibi kanalları yönetebilir
                if uid == owner_id:
                    overwrite.manage_channels = True
                else:
                    overwrite.manage_channels = False

                if overwrite.pair() != old_pair:
                    try:
                        await channel.set_permissions(member, overwrite=overwrite)
                    except Exception as e:
                        print(f"⚠️ Ses izni verilemedi ({channel.name} -> {member.name}): {e}", flush=True)

    # Metin kanallarını denetle
    for channel in guild.text_channels:
        # Metin kanallarındaki eski üye özel izinlerini de temizle
        for target, overwrite in list(channel.overwrites.items()):
            if isinstance(target, discord.Member):
                if target.id != owner_id and not target.bot:
                    try:
                        await channel.set_permissions(target, overwrite=None)
                    except Exception:
                        pass

    if owner_member:
        for channel in guild.text_channels:
            overwrite = channel.overwrites_for(owner_member)
            old_pair = overwrite.pair()
            overwrite.view_channel = True
            overwrite.send_messages = True
            overwrite.read_message_history = True
            overwrite.manage_messages = True
            overwrite.mention_everyone = True
            if overwrite.pair() != old_pair:
                try:
                    await channel.set_permissions(owner_member, overwrite=overwrite)
                except Exception:
                    pass


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
        await configure_unregistered_role_permissions(g)


async def remove_all_perms(rem_id: int):
    for g in bot.guilds:
        rem_m = g.get_member(rem_id)
        if rem_m:
            for ch in g.voice_channels:
                try:
                    await ch.set_permissions(rem_m, overwrite=None)
                except Exception:
                    pass
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


# ──────────────────────────────────────────────
# OLAYLAR (EVENTS)
# ──────────────────────────────────────────────

# Orijinal ses kanalları veritabanı (ID -> {name, category_id, position, bitrate, user_limit, ...})
SNAPSHOT_FILE = os.path.join(BASE_DIR, "channels_snapshot.json")

# İsim değişiklikleri için bekleyen kanallar: {channel_id: {"original_name": str, "target_time": float, "pending_restore": bool}}
pending_name_reverts = {}

# Yeni oluşturulan geçici kanallar için takip: {channel_id: {"created_at": float, "is_temp": True}}
temp_channels = {}

# Nuke yapılan kanalların takibi (otomatik koruma çakışmasını önlemek için)
nuking_channels = set()


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


async def check_and_fix_unregistered_members(guild: discord.Guild, force_welcome: bool = False):
    """
    Kayıt Kontrol & AFK Telafi:
    - Sunucuda hiçbir yetkisi olmayan (veya sadece kayıtlı rolü olan permsiz) üyeleri Kayıtsız Rolü'ne (1544443560571576380) geçirir.
    - Kayıtsız rolü verilen veya permsiz olan üyelere #welcome kanalında tekrar kayıt butonu atar.
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
        # Üzerinde yetki veya özel yetkili rolü olanları KESİNLİKLE atla
        if member_has_perm(member):
            continue

        has_reg_role = (reg_role and reg_role in member.roles)
        has_unreg_role = (unreg_role in member.roles)

        # 1. Eğer üzerinde kayıtlı rolü varsa kaldır
        if has_reg_role:
            try:
                await member.remove_roles(reg_role, reason="Permsiz üye: Kayıtlı rolü alındı, kayıtsıza atıldı.")
            except Exception as e:
                print(f"⚠️ Kayıtlı rolü alınamadı ({member.name}): {e}", flush=True)

        # 2. Kayıtsız rolü yoksa ver
        needs_welcome = False
        if not has_unreg_role:
            try:
                await member.add_roles(unreg_role, reason="Yetkisi olmayan üyeye Kayıtsız Rolü verildi.")
                print(f"🔒 [Kayıtsız Sıfırlama] {member.name} ({member.id}) kullanıcısına Kayıtsız Rolü verildi.", flush=True)
                needs_welcome = True
            except Exception as e:
                print(f"⚠️ Kayıtsız rolü verilemedi ({member.name}): {e}", flush=True)
        elif force_welcome:
            needs_welcome = True

        # 3. Welcome kanalına mesaj gönder (butonsuz, sade)
        if needs_welcome and welcome_channel:
            try:
                embed = create_welcome_embed(member)
                await welcome_channel.send(embed=embed)
                print(f"👋 [Kayıtsız Sıfırlama] {member.name} ({member.id}) için welcome mesajı gönderildi.", flush=True)
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

# Şarkı/kod listesi oynuyor olarak her saniye kesintisiz döner
@tasks.loop(seconds=1)
async def rotate_status_loop():
    """Botun profilindeki '🎮 ... Oynuyor' kısmını her saniye listeden sırayla günceller."""
    global status_song_index
    if not bot.is_ready():
        return
    try:
        # Şarkı / Kod listesi ASLA durmaz, her saniye döner (Game aktivitesi)
        playing_name = DYNAMIC_SONG_NAMES[status_song_index % len(DYNAMIC_SONG_NAMES)]
        status_song_index += 1

        cfg = load_config()
        custom_bio = cfg.get("custom_status") or cfg.get("bot_bio")

        # Discord aktiviteleri:
        # 1. Game (Oynuyor kısmı): Her saniye kod listesinden döner.
        await bot.change_presence(activity=discord.Game(name=playing_name), status=discord.Status.online)
    except Exception as e:
        print(f"⚠️ Durum güncellenemedi: {e}", flush=True)


@tasks.loop(minutes=10)
async def auto_repair_loop():
    """Her 10 dakikada bir arka planda sessizce sunucu ayarlarını kontrol edip onarır."""
    for guild in bot.guilds:
        await restore_server_integrity(guild)


STAY_VOICE_CHANNEL_ID = 1544550991196725298  # Botun 7/24 kalacağı ses kanalı ID'si
STAY_VOICE_CHANNEL_NAME = ""                   # Kanalın bilinen adı (silinirse isminden bulup girmesi için)


def get_stay_voice_channel(guild: discord.Guild = None) -> discord.VoiceChannel | None:
    """
    Botun 7/24 kalacağı ses kanalını bulur:
    1. Önce güncel config veya STAY_VOICE_CHANNEL_ID ile bakar.
    2. Eğer kanal ID ile bulunamazsa (silinmişse/değişmişse) kaydedilmiş kanal ismine göre sunucudaki ses kanallarını tarar.
    """
    global STAY_VOICE_CHANNEL_ID, STAY_VOICE_CHANNEL_NAME
    cfg = load_config()
    target_id = int(cfg.get("stay_voice_channel_id", STAY_VOICE_CHANNEL_ID))

    target_guilds = [guild] if guild else bot.guilds
    for g in target_guilds:
        if not g:
            continue
        # 1. ID ile ara
        ch = g.get_channel(target_id)
        if ch and isinstance(ch, discord.VoiceChannel):
            STAY_VOICE_CHANNEL_NAME = ch.name
            return ch

        # 2. İsim ile ara (Kanal silindiyse veya yeniden açıldıysa isminden tespit et)
        if STAY_VOICE_CHANNEL_NAME:
            for vch in g.voice_channels:
                if vch.name.strip().lower() == STAY_VOICE_CHANNEL_NAME.strip().lower():
                    # Yeni ID'yi güncelle ve kaydet
                    STAY_VOICE_CHANNEL_ID = vch.id
                    cfg["stay_voice_channel_id"] = str(vch.id)
                    save_config(cfg)
                    print(f"🔄 [Sabit Ses Odası] Kanal ID ile bulunamadı, '{vch.name}' isminden yakalandı ve güncellendi (Yeni ID: {vch.id})", flush=True)
                    return vch

    return None


async def ensure_voice_connection():
    """Bot hiçbir seste değilse 7/24 kalacağı odaya bağlanır. Asla odayı zorla değiştirmez."""
    try:
        channel = get_stay_voice_channel()
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


@tasks.loop(seconds=15)
async def voice_keepalive_loop():
    """Bot sesten tamamen düşerse veya kanal değişirse kontrol edip odaya sokar."""
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
            await restore_server_integrity(guild)
        print("⚡ Slash (/) komutları, ses yetkileri ve kanal kilitleri anında eşitlendi.", flush=True)
    else:
        print("⚠️ Bot henüz hiçbir sunucuya eklenmemiş!", flush=True)

    # Botun Hakkında (Bio / Application Description) kısmını ayarla
    token = os.getenv("DISCORD_TOKEN")
    cfg = load_config()
    current_bio = cfg.get("bot_bio", "")
    if token:
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                url = "https://discord.com/api/v10/applications/@me"
                headers = {
                    "Authorization": f"Bot {token}",
                    "Content-Type": "application/json"
                }
                async with session.patch(url, headers=headers, json={"description": current_bio}) as resp:
                    if resp.status == 200:
                        if current_bio:
                            print(f"📝 Botun Hakkında (Bio) kısmı ayarlandı: {current_bio}", flush=True)
                        else:
                            print("🧹 Botun Hakkında (Bio/Description) kısmı temiz.", flush=True)
        except Exception as e:
            print(f"⚠️ Bio ayarlanırken hata: {e}", flush=True)

    # Profil durumu döngüsünü başlat
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
    if channel.id in nuking_channels:
        nuking_channels.discard(channel.id)
        return

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
            global STAY_VOICE_CHANNEL_ID, STAY_VOICE_CHANNEL_NAME
            if str(channel.id) == str(STAY_VOICE_CHANNEL_ID) or (STAY_VOICE_CHANNEL_NAME and channel.name.strip().lower() == STAY_VOICE_CHANNEL_NAME.strip().lower()):
                STAY_VOICE_CHANNEL_ID = new_ch.id
                STAY_VOICE_CHANNEL_NAME = new_ch.name
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
    # Biri sese girdiğinde o kanal kayıtsızlara görünür (giremez), insan kalmayınca tamamen gizlenir
    unreg_role = member.guild.get_role(UNREGISTERED_ROLE_ID)
    everyone_role = member.guild.default_role
    if unreg_role or everyone_role:
        channels_to_update = set()
        if before.channel and isinstance(before.channel, discord.VoiceChannel):
            channels_to_update.add(before.channel)
        if after.channel and isinstance(after.channel, discord.VoiceChannel):
            channels_to_update.add(after.channel)

        for ch in channels_to_update:
            try:
                has_someone = (len(ch.members) > 0)
                for r in (unreg_role, everyone_role):
                    if r:
                        over = ch.overwrites_for(r)
                        if over.view_channel != has_someone or over.connect is not False:
                            over.view_channel = has_someone
                            over.connect = False
                            over.speak = False
                            await ch.set_permissions(r, overwrite=over)
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
        # 👑 @everyone ve @here KORUMASI: Sadece Allah atabilir, başka kimse atamaz!
        if message.mention_everyone:
            author_id = message.author.id
            if not is_allah(author_id):
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

        # Sunucu içi komutları beklemeden doğrudan ve en hızlı şekilde işle
        await bot.process_commands(message)
        return


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
            await target_channel.send(embed=embed)
            print(f"✅ Hoş geldin mesajı '{target_channel.name}' kanalına gönderildi.", flush=True)
        except Exception as e:
            print(f"❌ Hoş geldin mesajı gönderilirken hata: {e}", flush=True)


@bot.event
async def on_member_remove(member: discord.Member):
    """Biri sunucudan ayrıldığında veya atıldığında (kick) tetiklenir."""
    print(f"🚪 Üye ayrıldı: {member.name} (Sunucu: {member.guild.name})", flush=True)

    # 1. Allah dışındaki kişilerin yetkilerini tamamen sıfırla
    if not is_allah(member.id):
        s_list = load_sesyt()
        if member.id in s_list:
            s_list.remove(member.id)
            save_sesyt(s_list)
            await sync_voice_permissions(member.guild)
            print(f"🚫 [Yetki İptali] {member.name} sunucudan çıktığı için Ses Yetkisi (.sesyt) alındı.", flush=True)

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
    await interaction.response.send_message(embed=embed)


@bot.command(name="testwelcome")
async def test_welcome_prefix(ctx):
    embed = create_welcome_embed(ctx.author)
    await ctx.send(embed=embed)


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


@bot.command(name="bio", aliases=["biyografi", "setbio"])
async def set_bio_cmd(ctx, *, yeni_bio: str = None):
    """
    Botun profilindeki 'Hakkımda' (Bio) kısmını günceller.
    'Oynuyor' kısmı ise her saniye şarkı/kod listesinden bağımsız olarak dönmeye devam eder.
    Sadece 416978259557744640 ID'li bot sahibi kullanabilir.
    Kullanım: .bio <Yeni yazı> (veya .bio sıfırla)
    """
    if ctx.author.id != ALLAH_ID:
        return

    if not yeni_bio:
        await ctx.send("❌ Lütfen botun profilinde (Hakkımda/Bio) yazılacak metni girin! Örnek: `.bio https://discord.gg/...` (Sıfırlamak için: `.bio sıfırla`)")
        return

    token = os.getenv("DISCORD_TOKEN")
    cfg = load_config()

    if yeni_bio.strip().lower() in ("sıfırla", "sifirla", "reset", "clear"):
        cfg["bot_bio"] = ""
        save_config(cfg)
        if token:
            try:
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    url = "https://discord.com/api/v10/applications/@me"
                    headers = {
                        "Authorization": f"Bot {token}",
                        "Content-Type": "application/json"
                    }
                    await session.patch(url, headers=headers, json={"description": ""})
            except Exception:
                pass
        try:
            await ctx.message.add_reaction("✅")
        except Exception:
            msg = await ctx.send("✅")
            await asyncio.sleep(10)
            try:
                await msg.delete()
            except Exception:
                pass
        return

    # 1. Config'e kaydet
    cfg["bot_bio"] = yeni_bio.strip()
    save_config(cfg)

    # 2. Discord API üzerinden Bot Profilinin Hakkında (Bio / Description) kısmını güncelle
    if token:
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                url = "https://discord.com/api/v10/applications/@me"
                headers = {
                    "Authorization": f"Bot {token}",
                    "Content-Type": "application/json"
                }
                payload = {"description": yeni_bio.strip()}
                await session.patch(url, headers=headers, json=payload)
        except Exception as e:
            print(f"⚠️ Bio güncellenirken API hatası: {e}", flush=True)

    # Doğrudan kullanıcının mesajına tik (✅) at veya 10 saniye sonra silinen mesaj gönder
    try:
        await ctx.message.add_reaction("✅")
    except Exception:
        pass

    msg = await ctx.send("✅")
    await asyncio.sleep(10)
    try:
        await msg.delete()
    except Exception:
        pass


@bot.command(name="kayitsizsifirla", aliases=["kayitsizreset", "permsifirla"])
async def reset_unregistered_cmd(ctx):
    """
    Sunucudaki tüm permsiz kişileri Kayıtsız rolüne geçirir ve welcome kanalına tekrar buton atar.
    Sadece 416978259557744640 ID'li bot sahibi kullanabilir.
    """
    if ctx.author.id != ALLAH_ID:
        return

    try:
        await ctx.message.add_reaction("⏳")
    except Exception:
        pass

    guild = ctx.guild
    if guild:
        await check_and_fix_unregistered_members(guild, force_welcome=True)

    try:
        await ctx.message.add_reaction("✅")
    except Exception:
        pass
    msg = await ctx.send("✅ Permsiz üyeler kayıtsıza atıldı ve welcome butonları gönderildi.")
    await asyncio.sleep(10)
    try:
        await msg.delete()
    except Exception:
        pass


@bot.command(name="nuke", aliases=["kanalsifirla", "kanalsıfırla"])
async def nuke_cmd(ctx):
    """
    Komutun yazıldığı kanalı tamamen sıfırlar:
    Kanalı aynı isim, sıra (position), kategori ve tüm özel izinleriyle (overwrites)
    birebir yeniden açıp yerine getirir, eski mesajları temizler.
    Sadece 416978259557744640 ID'li bot sahibi kullanabilir.
    """
    if ctx.author.id != ALLAH_ID:
        return

    ch = ctx.channel
    guild = ctx.guild
    if not guild or not isinstance(ch, (discord.TextChannel, discord.VoiceChannel)):
        return

    # Nuke işlemi esnasında otomatik koruma döngüsüyle çakışmayı önlemek için kaydet
    nuking_channels.add(ch.id)

    try:
        # Mevcut kanalın özelliklerini ve izinlerini kopyala
        pos = ch.position
        name = ch.name
        cat = ch.category
        overwrites = ch.overwrites
        topic = getattr(ch, "topic", None)
        slowmode = getattr(ch, "slowmode_delay", 0)
        nsfw = getattr(ch, "nsfw", False)
        bitrate = getattr(ch, "bitrate", 64000)
        user_limit = getattr(ch, "user_limit", 0)

        # Yeni kanalı aynı parametrelerle klonla
        if isinstance(ch, discord.VoiceChannel):
            new_ch = await guild.create_voice_channel(
                name=name,
                category=cat,
                position=pos,
                overwrites=overwrites,
                bitrate=bitrate,
                user_limit=user_limit,
                reason=f"Nuke (.nuke) yapıldı (Yetkili: {ctx.author.name})"
            )
        else:
            new_ch = await guild.create_text_channel(
                name=name,
                category=cat,
                position=pos,
                overwrites=overwrites,
                topic=topic,
                slowmode_delay=slowmode,
                nsfw=nsfw,
                reason=f"Nuke (.nuke) yapıldı (Yetkili: {ctx.author.name})"
            )

        # Pozisyonu tam olarak eski yerine oturt
        try:
            await new_ch.edit(position=pos)
        except Exception:
            pass

        # Config veya snapshot'larda geçen ID varsa güncelle
        cfg = load_config()
        cfg_updated = False
        for key in ["welcome_channel_id", "exit_channel_id", "log_channel_id", "rules_channel_id", "dynamic_voice_channel_id", "stay_voice_channel_id"]:
            if cfg.get(key) == str(ch.id):
                cfg[key] = str(new_ch.id)
                cfg_updated = True
        if cfg_updated:
            save_config(cfg)

        global STAY_VOICE_CHANNEL_ID
        if ch.id == STAY_VOICE_CHANNEL_ID:
            STAY_VOICE_CHANNEL_ID = new_ch.id

        snapshots = load_snapshots()
        if str(ch.id) in snapshots:
            snap_data = snapshots.pop(str(ch.id))
            snapshots[str(new_ch.id)] = snap_data
            save_snapshots(snapshots)

        # Eski kanalı sil
        await ch.delete(reason=f"Nuke (.nuke) ile sıfırlandı.")

        # Yeni açılan kanala sadece silen kişiye etiket at
        if isinstance(new_ch, discord.TextChannel):
            await new_ch.send(f"{ctx.author.mention}")

    except Exception as e:
        print(f"⚠️ Nuke işlemi sırasında hata: {e}", flush=True)
        nuking_channels.discard(ch.id)





# ──────────────────────────────────────────────
# SES YETKİLİSİ (.sesyt / /sesyt) YÖNETİMİ
# Sadece 416978259557744640 ID'li kullanıcı çalıştırabilir
# ──────────────────────────────────────────────
SESYT_ADMIN_ID = 416978259557744640


@bot.group(name="sesyt", invoke_without_command=True)
async def sesyt_group(ctx):
    """Ses yetkilisi yönetim ana komutu."""
    if ctx.author.id != SESYT_ADMIN_ID:
        return

    embed = discord.Embed(
        title="🔊 Ses Yetkilisi Yönetimi",
        description=(
            "• `.sesyt ekle <@kisi / ID>` → Ses yetkilisi ekler (mute, deafen, move izinleri verir).\n"
            "• `.sesyt çıkar <@kisi / ID>` → Ses yetkilisini kaldırır ve izinlerini sıfırlar.\n"
            "• `.sesyt liste` → Ses yetkililerini listeler."
        ),
        color=0x00FF88
    )
    await ctx.send(embed=embed)


@sesyt_group.command(name="ekle")
async def sesyt_ekle_cmd(ctx, *, hedef: str = None):
    if ctx.author.id != SESYT_ADMIN_ID:
        return

    if not hedef:
        await ctx.send("❌ Kullanım: `.sesyt ekle @kullanici` veya `.sesyt ekle <ID>`")
        return

    target_id = None
    if ctx.message.mentions:
        target_id = ctx.message.mentions[0].id
    else:
        try:
            target_id = int(hedef.strip().split()[0])
        except ValueError:
            await ctx.send("❌ Geçersiz kullanıcı veya ID!")
            return

    s_list = load_sesyt()
    if target_id in s_list:
        await ctx.send(f"⚠️ <@{target_id}> (`{target_id}`) zaten ses yetkilisidir!")
        return

    s_list.append(target_id)
    save_sesyt(s_list)
    await sync_all()
    await ctx.send(f"✅ <@{target_id}> (`{target_id}`) **Ses Yetkilisi (.sesyt)** olarak eklendi! (Mute/Deafen/Move izinleri tanımlandı)")


@sesyt_group.command(name="cikar", aliases=["çıkar", "sil"])
async def sesyt_cikar_cmd(ctx, *, hedef: str = None):
    if ctx.author.id != SESYT_ADMIN_ID:
        return

    if not hedef:
        await ctx.send("❌ Kullanım: `.sesyt çıkar @kullanici` veya `.sesyt çıkar <ID>`")
        return

    target_id = None
    if ctx.message.mentions:
        target_id = ctx.message.mentions[0].id
    else:
        try:
            target_id = int(hedef.strip().split()[0])
        except ValueError:
            await ctx.send("❌ Geçersiz kullanıcı veya ID!")
            return

    s_list = load_sesyt()
    if target_id not in s_list:
        await ctx.send(f"⚠️ <@{target_id}> (`{target_id}`) ses yetkilisi listesinde yok!")
        return

    s_list.remove(target_id)
    save_sesyt(s_list)
    await remove_all_perms(target_id)
    await sync_all()
    await ctx.send(f"✅ <@{target_id}> (`{target_id}`) ses yetkilisi listesinden çıkarıldı ve izinleri sıfırlandı!")


@sesyt_group.command(name="liste")
async def sesyt_liste_cmd(ctx):
    if ctx.author.id != SESYT_ADMIN_ID:
        return

    s_list = load_sesyt()
    if not s_list:
        await ctx.send("📋 Ses yetkilisi listesi boş.")
        return

    liste = "\n".join([f"• <@{i}> (`{i}`)" for i in s_list])
    embed = discord.Embed(
        title="📋 Ses Yetkilileri (.sesyt) Listesi",
        description=liste,
        color=0x00FF88
    )
    await ctx.send(embed=embed)


# Slash komutları için grup
sesyt_slash = app_commands.Group(name="sesyt", description="Ses yetkilisi yönetimi")


@sesyt_slash.command(name="ekle", description="Ses yetkilisi ekler (Sadece yetkili ID)")
@app_commands.describe(kullanici="Ses yetkilisi yapılacak kullanıcı veya ID")
async def sesyt_slash_ekle(interaction: discord.Interaction, kullanici: discord.User):
    if interaction.user.id != SESYT_ADMIN_ID:
        await interaction.response.send_message("❌ Bu komutu sadece yetkili kişi kullanabilir.", ephemeral=True)
        return

    s_list = load_sesyt()
    if kullanici.id in s_list:
        await interaction.response.send_message(f"⚠️ {kullanici.mention} (`{kullanici.id}`) zaten ses yetkilisidir!", ephemeral=True)
        return

    s_list.append(kullanici.id)
    save_sesyt(s_list)
    await interaction.response.defer(ephemeral=True)
    await sync_all()
    await interaction.followup.send(f"✅ {kullanici.mention} (`{kullanici.id}`) **Ses Yetkilisi** olarak eklendi!", ephemeral=True)


@sesyt_slash.command(name="cikar", description="Ses yetkilisini kaldırır (Sadece yetkili ID)")
@app_commands.describe(kullanici="Ses yetkisi kaldırılacak kullanıcı")
async def sesyt_slash_cikar(interaction: discord.Interaction, kullanici: discord.User):
    if interaction.user.id != SESYT_ADMIN_ID:
        await interaction.response.send_message("❌ Bu komutu sadece yetkili kişi kullanabilir.", ephemeral=True)
        return

    s_list = load_sesyt()
    if kullanici.id not in s_list:
        await interaction.response.send_message(f"⚠️ {kullanici.mention} (`{kullanici.id}`) ses yetkilisi listesinde yok!", ephemeral=True)
        return

    s_list.remove(kullanici.id)
    save_sesyt(s_list)
    await interaction.response.defer(ephemeral=True)
    await remove_all_perms(kullanici.id)
    await sync_all()
    await interaction.followup.send(f"✅ {kullanici.mention} (`{kullanici.id}`) ses yetkilisi listesinden çıkarıldı!", ephemeral=True)


@sesyt_slash.command(name="liste", description="Ses yetkililerini listeler (Sadece yetkili ID)")
async def sesyt_slash_liste(interaction: discord.Interaction):
    if interaction.user.id != SESYT_ADMIN_ID:
        await interaction.response.send_message("❌ Bu komutu sadece yetkili kişi kullanabilir.", ephemeral=True)
        return

    s_list = load_sesyt()
    if not s_list:
        await interaction.response.send_message("📋 Ses yetkilisi listesi boş.", ephemeral=True)
        return

    liste = "\n".join([f"• <@{i}> (`{i}`)" for i in s_list])
    embed = discord.Embed(
        title="📋 Ses Yetkilileri Listesi",
        description=liste,
        color=0x00FF88
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


bot.tree.add_command(sesyt_slash)



# ──────────────────────────────────────────────
# SPOTIFY & MÜZİK SİSTEMİ
# ──────────────────────────────────────────────
import urllib.request
import urllib.parse
import re
from yt_dlp import YoutubeDL

# Sunucu bazlı müzik kuyruğu: {guild_id: {"queue": list[dict], "current": dict, "loop": bool}}
music_queues = {}

# Müzik Önbellek Dizini (Local Cache)
MUSIC_CACHE_DIR = os.path.join(BASE_DIR, "music_cache")
os.makedirs(MUSIC_CACHE_DIR, exist_ok=True)

# İndirme seçenekleri (VDS IP engellerini aşan ve kesintisiz yerel indirme sağlayan motor)
YTDL_DOWNLOAD_OPTIONS = {
    'format': 'bestaudio/best',
    'outtmpl': os.path.join(MUSIC_CACHE_DIR, '%(id)s.%(ext)s'),
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': True,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'scsearch',
    'source_address': '0.0.0.0',
    'socket_timeout': 15,
    'retries': 3,
    'extractor_args': {
        'youtube': {
            'player_client': ['android', 'ios', 'web_creator'],
            'skip': ['dash', 'hls'],
        }
    },
    'http_headers': {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-us,en;q=0.5',
    }
}

ytdl_downloader = YoutubeDL(YTDL_DOWNLOAD_OPTIONS)

import shutil

# FFmpeg yolunu otomatik bul (Linux sistem ffmpeg veya Windows PATH / WinGet)
FFMPEG_EXE = shutil.which("ffmpeg")
if not FFMPEG_EXE:
    winget_ffmpeg = r"C:\Users\biber\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.1-full_build\bin\ffmpeg.exe"
    if os.path.exists(winget_ffmpeg):
        FFMPEG_EXE = winget_ffmpeg
    else:
        FFMPEG_EXE = "ffmpeg"

FFMPEG_OPTIONS = {
    'options': '-vn -sn -dn'
}


def get_spotify_tracks(spotify_url: str) -> list[str]:
    """Spotify playlist/track/album linkinden sanatçı ve şarkı isimlerini %100 doğrulukla çeker."""
    tracks = []
    try:
        clean_url = spotify_url.split("?")[0].strip()

        # Spotify Web Player sayfaları artık JS ile render edildiğinden, statik HTML ve meta etiketleri
        # embed URL'inde ("open.spotify.com/embed/...") eksiksiz yer alır.
        if "open.spotify.com/embed/" in clean_url:
            embed_url = clean_url
        else:
            embed_url = clean_url.replace("open.spotify.com/", "open.spotify.com/embed/")

        req = urllib.request.Request(
            embed_url,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
                'Accept-Language': 'en-US,en;q=0.9'
            }
        )
        try:
            with urllib.request.urlopen(req, timeout=6) as response:
                html = response.read().decode('utf-8', errors='ignore')

            # __NEXT_DATA__ JSON yapısı (En kesin ve temiz veriyi içerir)
            m_json = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html)
            if m_json:
                try:
                    data = json.loads(m_json.group(1))
                    entity = data.get("props", {}).get("pageProps", {}).get("state", {}).get("data", {}).get("entity", {})
                    track_list = entity.get("trackList", [])
                    if track_list:
                        for item in track_list:
                            t_title = item.get("title", "")
                            t_subtitle = item.get("subtitle", "")
                            if t_title:
                                q = f"{t_subtitle} - {t_title}".strip(" -") if t_subtitle else t_title
                                tracks.append(q)
                    else:
                        # Tekil şarkı (Single Track)
                        t_title = entity.get("title") or entity.get("name")
                        artists = entity.get("artists", [])
                        artist_names = ", ".join([a.get("name", "") for a in artists if a.get("name")])
                        if t_title:
                            q = f"{artist_names} - {t_title}".strip(" -") if artist_names else t_title
                            tracks.append(q)
                except Exception:
                    pass

            # Yedek: OpenGraph Meta etiketleri
            if not tracks:
                og_title_match = re.search(r'property="og:title"\s+content="([^"]+)"', html) or re.search(r'content="([^"]+)"\s+property="og:title"', html)
                og_desc_match = re.search(r'property="og:description"\s+content="([^"]+)"', html) or re.search(r'content="([^"]+)"\s+property="og:description"', html)
                if og_title_match:
                    t_title = og_title_match.group(1).strip()
                    desc = og_desc_match.group(1).strip() if og_desc_match else ""
                    # og:description formatı: "INNA · Hot · Song · 2010" veya "Song · 2010"
                    artist = ""
                    if desc:
                        parts = [p.strip() for p in re.split(r'[\u00b7\u2022\-]', desc) if p.strip()]
                        if parts and parts[0].lower() != "song":
                            artist = parts[0]
                    if artist and artist.lower() not in t_title.lower():
                        tracks.append(f"{artist} - {t_title}")
                    else:
                        tracks.append(t_title)

        except Exception as err:
            print(f"Spotify embed HTML çekme hatası: {err}", flush=True)

        # Yedek 2: Spotify oEmbed API
        if not tracks:
            try:
                oembed_url = f"https://open.spotify.com/oembed?url={urllib.parse.quote(clean_url)}"
                o_req = urllib.request.Request(
                    oembed_url,
                    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
                )
                with urllib.request.urlopen(o_req, timeout=5) as o_res:
                    o_data = json.loads(o_res.read().decode('utf-8'))
                    title = o_data.get("title", "")
                    author = o_data.get("author_name", "") or o_data.get("author", "")
                    if title:
                        if author and author.lower() not in title.lower():
                            tracks.append(f"{author} - {title}")
                        else:
                            tracks.append(title)
            except Exception:
                pass

    except Exception as e:
        print(f"Spotify ayrıştırma genel hatası: {e}", flush=True)

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
                home_ch = get_stay_voice_channel(guild)
                if home_ch and vc.channel.id != home_ch.id:
                    await vc.move_to(home_ch)
                    print(f"🏠 [Ses Odası] 3 dakika boyunca yeni şarkı istenmediği için bot kendi odasına ({home_ch.name}) geri döndü.", flush=True)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"⚠️ Kendi odasına dönerken hata: {e}", flush=True)
    finally:
        music_idle_tasks.pop(guild.id, None)


async def play_next_song(guild: discord.Guild):
    """Kuyruktaki sıradaki şarkıyı indirip yerel olarak çalar (Sıfır Kesinti Garantili)."""
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
        
        # Doğrudan arama (URL ise doğrudan kullan; şarkı adı ise önce YouTube resmi ses kaydı ara)
        if "youtube.com" in track_query or "youtu.be" in track_query or "soundcloud.com" in track_query or track_query.startswith("http"):
            search_target = track_query
        else:
            search_target = f"ytsearch1:{track_query} official audio"

        # Şarkıyı yerel diskteki music_cache klasörüne hızlıca indir
        data = await loop.run_in_executor(None, lambda: ytdl_downloader.extract_info(search_target, download=True))
        
        info = None
        if data:
            if 'entries' in data and len(data['entries']) > 0:
                info = data['entries'][0]
            else:
                info = data

        # Yedek 1: Düz ytsearch (ek kelime olmadan)
        if not info and not track_query.startswith("http"):
            fallback_target = f"ytsearch1:{track_query}"
            data = await loop.run_in_executor(None, lambda: ytdl_downloader.extract_info(fallback_target, download=True))
            if data and 'entries' in data and len(data['entries']) > 0:
                info = data['entries'][0]
            elif data:
                info = data

        # Yedek 2: SoundCloud
        if not info and not track_query.startswith("http"):
            sc_target = f"scsearch1:{track_query}"
            data = await loop.run_in_executor(None, lambda: ytdl_downloader.extract_info(sc_target, download=True))
            if data and 'entries' in data and len(data['entries']) > 0:
                info = data['entries'][0]
            elif data:
                info = data

        if not info:
            raise RuntimeError(f"Şarkı indirilemedi: {track_query}")

        # İndirilen yerel dosyanın tam yolunu bul
        file_path = ytdl_downloader.prepare_filename(info)
        
        # Eğer uzantı değişmişse (örn .opus veya .m4a) dosyayı bul
        if not os.path.exists(file_path):
            base, _ = os.path.splitext(file_path)
            for ext in (".opus", ".m4a", ".mp3", ".webm", ".ogg", ".wav"):
                if os.path.exists(base + ext):
                    file_path = base + ext
                    break

        if not os.path.exists(file_path):
            raise RuntimeError(f"Yerel ses dosyası bulunamadı: {file_path}")

        title = info.get('title', track_query)
        g_data["current"] = title

        def after_playing(error):
            if error:
                print(f"⚠️ Çalma hatası: {error}", flush=True)
            # Şarkı bittiğinde geçici dosyayı temizle
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception:
                pass
            asyncio.run_coroutine_threadsafe(play_next_song(guild), bot.loop)

        # Yerel dosya üzerinden direkt PCM Audio (Sıfır internet kesintisi, sonuna kadar çalma)
        source = discord.FFmpegPCMAudio(file_path, executable=FFMPEG_EXE, **FFMPEG_OPTIONS)
        vc.play(source, after=after_playing)
        print(f"🎵 [Müzik - Kesintisiz Yerel Çalma] Çalıyor: {title}", flush=True)

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
            await msg.edit(content="❌ Spotify linkindeki şarkı veya playlist bilgisi okunamadı! Lütfen şarkı adını yazarak deneyin: `.play Şarkı Adı`")
            return
        elif len(tracks) == 1:
            g_queue.append(tracks[0])
            await msg.edit(content=f"Sıraya eklendi: **{tracks[0]}**")
        else:
            g_queue.extend(tracks)
            preview = ", ".join(tracks[:3])
            more = f" ve {len(tracks) - 3} şarkı daha" if len(tracks) > 3 else ""
            await msg.edit(content=f"**{len(tracks)}** adet şarkı Spotify'dan sıraya eklendi!\n`{preview}{more}`")

        if not vc.is_playing() and not vc.is_paused():
            await play_next_song(ctx.guild)

    # 2. YouTube linki mi?
    elif "youtube.com" in sorgu or "youtu.be" in sorgu:
        msg = await ctx.send("YouTube taranıyor...")
        try:
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, lambda: ytdl_downloader.extract_info(sorgu, download=False))
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
