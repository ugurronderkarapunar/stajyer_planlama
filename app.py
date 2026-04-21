import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
import io
import plotly.express as px
import os

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="STAJYER PLANLAMA VE YÖNETİM SİSTEMİ", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    h1, h2, h3, h4, label, .stButton>button, .stMarkdown, p, span, .stMetric { 
        text-transform: uppercase !important; 
        font-weight: bold !important;
    }
    .stDataFrame, .stTable { border-radius: 10px; border: 1px solid #e0e0e0; }
    </style>
    """, unsafe_allow_html=True)

# --- VERİTABANI YÖNETİMİ ---
# FIX 1: Veritabanı dosyası her zaman script ile aynı klasörde saklanır → veri kaybolmaz
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'stajyer_takip_sistemi.db')

@st.cache_resource  # FIX 1: Bağlantı uygulama boyunca tek sefer oluşturulur → veri kaybolmaz
def init_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()

    # Ana tablo: sicil_no ve notlar eklendi (FIX 2 & 4)
    c.execute('''CREATE TABLE IF NOT EXISTS stajyerler
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  sicil_no TEXT,
                  ad_soyad TEXT,
                  okul TEXT,
                  gemi TEXT,
                  telefon TEXT,
                  baslangic DATE,
                  bitis DATE,
                  gun_grubu TEXT,
                  bolum TEXT,
                  notlar TEXT)''')

    # İzin tablosu: izin_baslangic + izin_bitis eklendi (FIX 3)
    c.execute('''CREATE TABLE IF NOT EXISTS izinler
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  stajyer_id INTEGER,
                  izin_baslangic DATE,
                  izin_bitis DATE,
                  izin_tipi TEXT,
                  FOREIGN KEY(stajyer_id) REFERENCES stajyerler(id))''')

    # Mevcut veritabanı için sütun migrasyonu (eski kurulumlar bozulmasın)
    mevcut_kolonlar = [r[1] for r in c.execute("PRAGMA table_info(stajyerler)").fetchall()]
    for kolon, tip in [("sicil_no", "TEXT"), ("notlar", "TEXT")]:
        if kolon not in mevcut_kolonlar:
            c.execute(f"ALTER TABLE stajyerler ADD COLUMN {kolon} {tip}")

    izin_kolonlar = [r[1] for r in c.execute("PRAGMA table_info(izinler)").fetchall()]
    if "izin_bitis" not in izin_kolonlar:
        c.execute("ALTER TABLE izinler ADD COLUMN izin_bitis DATE")
    # Eski tek tarihli kayıtları güncelle: bitis = baslangic
    if "izin_tarihi" in izin_kolonlar:
        c.execute("UPDATE izinler SET izin_baslangic = izin_tarihi WHERE izin_baslangic IS NULL")
        c.execute("UPDATE izinler SET izin_bitis = izin_tarihi WHERE izin_bitis IS NULL")

    conn.commit()
    return conn

conn = init_db()

# --- YARDIMCI FONKSİYONLAR ---
def get_all_interns():
    return pd.read_sql("SELECT * FROM stajyerler", conn)

def get_intern_leaves(intern_id):
    return pd.read_sql(
        "SELECT id, izin_baslangic, izin_bitis, izin_tipi FROM izinler WHERE stajyer_id = ?",
        conn, params=(intern_id,)
    )

TR_GUNLER = {
    'Monday': 'PAZARTESİ', 'Tuesday': 'SALI', 'Wednesday': 'ÇARŞAMBA',
    'Thursday': 'PERŞEMBE', 'Friday': 'CUMA', 'Saturday': 'CUMARTESİ', 'Sunday': 'PAZAR'
}

def get_resmi_tatiller(yil):
    tatiller = [
        f"{yil}-01-01", f"{yil}-04-23", f"{yil}-05-01",
        f"{yil}-05-19", f"{yil}-07-15", f"{yil}-08-30", f"{yil}-10-29"
    ]
    if yil == 2026:
        tatiller.extend([
            "2026-03-19", "2026-03-20", "2026-03-21", "2026-03-22",
            "2026-05-26", "2026-05-27", "2026-05-28", "2026-05-29", "2026-05-30"
        ])
    return tatiller

def izin_var_mi(leaves_df, d_str):
    """Verilen tarih herhangi bir izin aralığına denk geliyor mu?"""
    for _, row in leaves_df.iterrows():
        bas = str(row['izin_baslangic'])
        bit = str(row['izin_bitis']) if pd.notna(row['izin_bitis']) else bas
        if bas <= d_str <= bit:
            return row['izin_tipi']
    return None

# --- SIDEBAR NAVİGASYON ---
st.sidebar.title("⚓ NAVİGASYON")
menu = st.sidebar.radio("SAYFA SEÇİNİZ:", [
    "📊 DASHBOARD",
    "👤 PERSONEL YÖNETİMİ",
    "📅 İZİN SİSTEMİ",
    "📑 PUANTAJ VE EXCEL"
])

# =============================================================
# 1. DASHBOARD
# =============================================================
if menu == "📊 DASHBOARD":
    st.header("📈 GENEL DURUM VE ANALİZ")
    df_stajyer = get_all_interns()
    if not df_stajyer.empty:
        col1, col2, col3 = st.columns([1, 2, 2])
        with col1:
            st.metric("TOPLAM STAJYER", len(df_stajyer))
        with col2:
            gemi_counts = df_stajyer['gemi'].value_counts().reset_index()
            gemi_counts.columns = ['GEMİ', 'SAYI']
            st.plotly_chart(
                px.bar(gemi_counts, x='GEMİ', y='SAYI', title="🚢 GEMİ BAZLI DAĞILIM"),
                use_container_width=True
            )
        with col3:
            bolum_counts = df_stajyer['bolum'].value_counts().reset_index()
            bolum_counts.columns = ['BÖLÜM', 'SAYI']
            st.plotly_chart(
                px.pie(bolum_counts, values='SAYI', names='BÖLÜM',
                       title="🛠️ BÖLÜM DAĞILIMI", hole=0.3),
                use_container_width=True
            )
    else:
        st.info("HENÜZ STAJYER KAYDI BULUNMAMAKTADIR.")

# =============================================================
# 2. PERSONEL YÖNETİMİ
# =============================================================
elif menu == "👤 PERSONEL YÖNETİMİ":
    st.header("👤 STAJYER KAYIT VE YÖNETİMİ")

    with st.expander("➕ YENİ STAJYER EKLE"):
        c1, c2 = st.columns(2)
        with c1:
            sicil  = st.text_input("SİCİL NO")                          # FIX 2
            ad     = st.text_input("AD SOYAD").upper()
            okul   = st.text_input("OKUL").upper()
            gemi   = st.text_input("GEMİ ADI").upper()
            tel    = st.text_input("TELEFON NUMARASI")
        with c2:
            bas    = st.date_input("STAJ BAŞLANGIÇ")
            bit    = st.date_input("STAJ BİTİŞ")
            gunler = st.selectbox("STAJ GÜNLERİ",
                                  ["PAZARTESİ-SALI-ÇARŞAMBA", "ÇARŞAMBA-PERŞEMBE-CUMA"])
            bolum  = st.selectbox("BÖLÜM", ["MAKİNE", "GÜVERTE"])
            notlar = st.text_area("NOTLAR (ÖĞRENCİ / GEMİ / OKUL BAZLI)", height=80)  # FIX 4

        if st.button("KAYDI TAMAMLA"):
            conn.execute(
                """INSERT INTO stajyerler
                   (sicil_no, ad_soyad, okul, gemi, telefon, baslangic, bitis,
                    gun_grubu, bolum, notlar)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (sicil, ad, okul, gemi, tel, bas, bit, gunler, bolum, notlar)
            )
            conn.commit()
            st.success(f"{ad} EKLENDİ!")
            st.rerun()

    df = get_all_interns()
    if not df.empty:
        st.subheader("📝 PERSONEL LİSTESİNİ DÜZENLE / SİL")
        edited_df = st.data_editor(df, num_rows="dynamic", key="main_editor", hide_index=True)
        if st.button("🔄 TÜMÜNÜ GÜNCELLE"):
            conn.execute("DELETE FROM stajyerler")
            edited_df.to_sql('stajyerler', conn, if_exists='append', index=False)
            conn.commit()
            st.success("PERSONEL LİSTESİ GÜNCELLENDİ!")
            st.rerun()

# =============================================================
# 3. İZİN SİSTEMİ
# =============================================================
elif menu == "📅 İZİN SİSTEMİ":
    st.header("📅 İZİN YÖNETİMİ")
    df = get_all_interns()

    if not df.empty:
        s_ad = st.selectbox("STAJYER SEÇİN", df['ad_soyad'].tolist())
        s_id = int(df[df['ad_soyad'] == s_ad]['id'].values[0])

        col_ekle, col_duzenle = st.columns([1, 2])

        with col_ekle:
            st.subheader("➕ İZİN EKLE")
            i_bas  = st.date_input("İZİN BAŞLANGIÇ TARİHİ", key="izin_bas")   # FIX 3
            i_bit  = st.date_input("İZİN BİTİŞ TARİHİ", key="izin_bit",       # FIX 3
                                   value=i_bas)
            i_tip  = st.radio("DURUM", ["RAPORLU", "RAPORSUZ DEVAMSIZLIK"], key="yeni_izin_tip")

            if st.button("İZİNİ KAYDET"):
                if i_bit < i_bas:
                    st.error("BİTİŞ TARİHİ BAŞLANGIÇTAN ÖNCE OLAMAZ!")
                else:
                    conn.execute(
                        "INSERT INTO izinler (stajyer_id, izin_baslangic, izin_bitis, izin_tipi) VALUES (?,?,?,?)",
                        (s_id, i_bas, i_bit, i_tip)
                    )
                    conn.commit()
                    gun_sayisi = (i_bit - i_bas).days + 1
                    st.success(f"İZİN KAYDEDİLDİ! ({gun_sayisi} GÜN)")
                    st.rerun()

        with col_duzenle:
            st.subheader("📝 İZİN DÜZENLE / SİL")
            iz_df = get_intern_leaves(s_id)

            if not iz_df.empty:
                edited_iz_df = st.data_editor(
                    iz_df,
                    column_order=("izin_baslangic", "izin_bitis", "izin_tipi"),
                    num_rows="dynamic",
                    key="izin_editor",
                    use_container_width=True,
                    hide_index=True
                )

                if st.button("🔄 DEĞİŞİKLİKLERİ KAYDET"):
                    conn.execute("DELETE FROM izinler WHERE stajyer_id = ?", (s_id,))
                    for _, row in edited_iz_df.iterrows():
                        if pd.notna(row['izin_baslangic']):
                            bit_tar = row['izin_bitis'] if pd.notna(row['izin_bitis']) else row['izin_baslangic']
                            conn.execute(
                                "INSERT INTO izinler (stajyer_id, izin_baslangic, izin_bitis, izin_tipi) VALUES (?,?,?,?)",
                                (s_id, row['izin_baslangic'], bit_tar, row['izin_tipi'])
                            )
                    conn.commit()
                    st.success("İZİN KAYITLARI GÜNCELLENDİ!")
                    st.rerun()

                st.caption("NOT: SATIRI SEÇİP 'DELETE' TUŞUYLA SİLEBİLİRSİNİZ.")
            else:
                st.info("BU KİŞİYE AİT KAYITLI İZİN BULUNMAMAKTADIR.")
    else:
        st.warning("SİSTEMDE KAYITLI STAJYER BULUNAMADI.")

# =============================================================
# 4. PUANTAJ VE EXCEL
# =============================================================
elif menu == "📑 PUANTAJ VE EXCEL":
    st.header("📑 AYLIK PUANTAJ VE TOPLAM DEVAM")
    c1, c2 = st.columns(2)
    ay  = c1.number_input("AY",  1, 12, datetime.now().month)
    yil = c2.number_input("YIL", 2024, 2030, datetime.now().year)

    df_st = get_all_interns()
    if not df_st.empty:
        bas_dt = datetime(yil, ay, 1)
        bit_dt = (datetime(yil, ay + 1, 1) if ay < 12 else datetime(yil + 1, 1, 1)) - timedelta(days=1)
        gunler_range = pd.date_range(bas_dt, bit_dt)
        tatiller = get_resmi_tatiller(yil)

        puantaj_res = []
        genel_toplam_gun = 0

        for _, row in df_st.iterrows():
            satir = {
                "SİCİL NO": row.get('sicil_no', ''),
                "AD SOYAD": row['ad_soyad'],
                "GEMİ": row['gemi'],
                "BÖLÜM": row['bolum']
            }
            leaves = get_intern_leaves(row['id'])
            kisi_toplam_gun = 0

            for d in gunler_range:
                d_str  = d.strftime('%Y-%m-%d')
                gun_tr = TR_GUNLER[d.strftime('%A')]
                is_tatil = (gun_tr in ["CUMARTESİ", "PAZAR"]) or (d_str in tatiller)

                if is_tatil:
                    satir[d.day] = "TATİL"
                else:
                    staj_gunu = (
                        gun_tr in ["PAZARTESİ", "SALI", "ÇARŞAMBA"]
                        if row['gun_grubu'] == "PAZARTESİ-SALI-ÇARŞAMBA"
                        else gun_tr in ["ÇARŞAMBA", "PERŞEMBE", "CUMA"]
                    )
                    izin_tipi = izin_var_mi(leaves, d_str)  # FIX 3: aralık kontrolü

                    if izin_tipi:
                        satir[d.day] = izin_tipi
                    elif staj_gunu:
                        satir[d.day] = "1"
                        kisi_toplam_gun += 1
                    else:
                        satir[d.day] = "-"

            satir["KİŞİ TOPLAM"] = kisi_toplam_gun
            genel_toplam_gun += kisi_toplam_gun
            puantaj_res.append(satir)

        p_df = pd.DataFrame(puantaj_res)
        st.info(f"📊 **BU AY TÜM STAJYERLERİN TOPLAM STAJ GÜNÜ: {genel_toplam_gun} GÜN**")
        st.dataframe(p_df, use_container_width=True)

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            p_df.to_excel(writer, index=False, sheet_name='PUANTAJ')
            workbook  = writer.book
            worksheet = writer.sheets['PUANTAJ']
            bold = workbook.add_format({'bold': True})
            worksheet.write(len(p_df) + 2, 0, "TÜM ÖĞRENCİLER GENEL TOPLAM:", bold)
            worksheet.write(len(p_df) + 2, 1, genel_toplam_gun, bold)

        st.download_button(
            label="📥 EXCEL OLARAK İNDİR",
            data=output.getvalue(),
            file_name=f"PUANTAJ_{ay}_{yil}.xlsx"
        )
    else:
        st.warning("SİSTEMDE KAYITLI STAJYER BULUNAMADI.")
