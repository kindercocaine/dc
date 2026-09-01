# 🛡️ Discord Gelişmiş Sunucu Yönetim, Koruma & Müzik Botu

Bu bot; otomatik kanal & kategori koruma, dinamik ses görünürlüğü, kayıt sistemi, rol senkronizasyonu, Spotify & YouTube müzik çalar ve gelişmiş yönetim araçlarını bir arada sunar.

---

## 📋 Genel Özellikler

### 1. 🛡️ Gelişmiş Sunucu Koruma & Snapshot Sistemi
- **Otomatik Onarım:** Bot açıldığında veya periyodik kontrolde (`auto_repair_loop`) tüm sunucu kanallarını, kilitlerini ve izinlerini doğrular.
- **Kanal Silme / Açma Koruması:** Yetkililer izinsiz kanal silerse veya açarsa anında eski haline döndürülür veya silinir.
- **`duzenleme` Modu:** Allah (`ALLAH_ID`) özelden `duzenleme` yazarak korumayı geçici kapatabilir, kanalları düzenledikten sonra tekrar `duzenleme` yazarak sunucunun son halini botun hafızasına (snapshot) kazıyabilir.

### 2. 🎙️ Dinamik Ses Odası Görünürlüğü & 7/24 Ses
- **Dinamik Görünürlük:** Kayıtsız üyeler sadece içinde insan olan ses kanallarını görebilir (`view_channel=True`), ancak bağlanamazlar (`connect=False`). Kanal boşaldığında kayıtsızlara otomatik gizlenir.
- **7/24 Ses Odası:** Bot belirlenen odada (`1532596503447867434`) sağırlaştırılmış ve mikrofonu açık şekilde 7/24 bekler.

### 3. 🎵 Spotify & YouTube Müzik Çalar
- **Otomatik Odaya Gelme:** `.oynat` yazan yetkilinin odasına gider ve müziği çalar.
- **Kullanıcı Kilidi:** Bir kişi müzik dinlerken başka birinin şarkıyı değiştirmesini/durdurmasını engeller.
- **Bekleme Süresi:** Şarkı/liste bittiğinde **3 dakika** boyunca yeni şarkı bekler; yeni istek gelmezse otomatik olarak kendi orijinal ses odasına geri döner.
- **Platform Seçimi:** Şarkı adı yazıldığında butonla **[YouTube]** veya **[Spotify]** seçeneği sunar.
- **Müzik Komutları:** `.oynat <şarkı/link>`, `.atla`, `.durdur`, `.devam`, `.kuyruk`, `.kuyruktemizle`.

### 4. 🧹 Yönetim & Temizlik Komutları
- **`.sil <adet>`:** Kanaldaki mesajları anında siler ve düz sade bilgilendirme metni gönderir.
- **`.nuke`:** Kanalı klonlayıp temizler, izinleri senkronize eder. (`#welcome` ve `#exit` kanallarında sadece Allah nuke atabilir).

---

## 🚀 Kurulum ve VDS Çalıştırma

### 1. Kütüphaneleri Yükleyin
```bash
pip install -r requirements.txt
```

### 2. Ortam Değişkenlerini Ayarlayın (`.env`)
`.env` dosyasını açıp bot tokenınızı ve Allah ID'sini girin:
```env
DISCORD_TOKEN=BOT_TOKENINIZ
OWNER_ID=416978259557744640
```

### 3. Botu Başlatın
```bash
python bot.py
```

---

## 📂 Dosya Yapısı

- `bot.py` → Ana bot motoru, komutlar, müzik sistemi ve olay dinleyicileri.
- `config.json` → Kanal ID'leri ve genel ayarlar.
- `channels_snapshot.json` → Sunucunun hafızaya kazınmış kanal yapısı.
- `authorized.json` → Tam Yetkili ID listesi (`.yt`).
- `kurucu.json` → Kurucu ID listesi.
- `sesyt.json` → Ses Yetkilisi ID listesi (`.sesyt`).
- `requirements.txt` → Python bağımlılıkları.
