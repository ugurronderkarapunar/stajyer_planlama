import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
import io

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="STAJYER PLANLAMA VE DASHBOARD", layout="wide")

# Modern Stil ve Tüm Metinleri Büyük Harf Yapma (CSS)
st.markdown("""
    <style>
    .main { background-color: #f0f2f6; }
    h1, h2, h3, h4, label, .stButton>button, .stMarkdown, p { 
        text-transform: uppercase !important; 
        font-weight: bold;
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    }
    .stDataFrame { border-radius: 10px; border: 1px solid #d1d5db; }
    div[data-baseweb="select"] > div { text-transform: uppercase; }
    </style>
    """, unsafe_allow_html=True)

# --- VERİTABANI YÖNETİMİ ---
def init_db():
    conn = sqlite3.connect('stajyer_yonetimi.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS stajyerler
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, ad_soyad TEXT, okul TEXT, 
                  gemi TEXT, telefon TEXT, baslangic DATE, bitis DATE, 
                  gun_grubu TEXT, bolum TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS izinler
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, stajyer_id INTEGER, 
                  izin_tarihi DATE, izin_tipi TEXT, FOREIGN KEY(stajyer_id) REFERENCES stajyerler(id))''')
    conn.commit()
    return conn

conn = init_db()

# --- YARDIMCI FONKSİYONLAR ---
def get_all_interns():
    return pd.read_sql("SELECT * FROM stajyerler", conn)

def get_intern_leaves(intern_id):
    query = f"SELECT izin_tarihi, izin_tipi FROM izinler WHERE stajyer_id = {intern_id}"
    return pd.read_sql(query, conn)

# Türkçe Gün Eşleşmesi
TR_GUNLER = {
    'Monday': 'PAZARTESİ', 'Tuesday': 'SALI', 'Wednesday': 'ÇARŞAMBA',
    'Thursday': 'PERŞEMBE', 'Friday': 'CUMA', 'Saturday': 'CUMARTESİ', 'Sunday': 'PAZAR'
}

# --- SIDEBAR NAVİGASYON ---
st.sidebar.title("⚓ STAJ YÖNETİMİ")
menu = st.sidebar.radio("MENÜ:", ["📊 DASHBOARD", "👤 PERSONEL YÖNETİMİ", "📅 İZİN SİSTEMİ", "📑 PUANTAJ VE EXCEL"])

# --- SAYFA 1: DASHBOARD ---
if menu == "📊 DASHBOARD":
    st.header("📈 GENEL DURUM ANALİZİ")
    df_stajyer = get_all_interns()
    
    if not df_stajyer.empty:
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("TOPLAM STAJYER", len(df_stajyer))
        
        with col2:
            # Gemi bazlı dağılım
            gemi_counts = df_stajyer['gemi'].value_counts()
            st.subheader("🚢 GEMİ BAZLI STAJYER SAYISI")
            st.bar_chart(gemi_counts)
        
        with col3:
            # Bölüm bazlı dağılım
            bolum_counts = df_stajyer['bolum'].value_counts()
            st.subheader("🛠️ BÖLÜM DAĞILIMI")
            st.pie_chart(bolum_counts)

        st.divider()
        st.subheader("🗓️ AYLIK DEVAMLILIK ÖZETİ")
        # Basit bir özet tablo
        st.write("AŞAĞIDAKİ TABLODA ÖĞRENCİLERİN AY İÇİNDEKİ TOPLAM VARLIKLARI GÖRÜLEBİLİR.")
    else:
        st.info("VERİ BULUNAMADI. LÜTFEN PERSONEL EKLEYİN.")

# --- SAYFA 2: PERSONEL YÖNETİMİ ---
elif menu == "👤 PERSONEL YÖNETİMİ":
    st.header("👤 PERSONEL EKLEME VE DÜZENLEME")
    
    with st.expander("➕ YENİ STAJYER KAYDI"):
        col1, col2 = st.columns(2)
        with col1:
            ad = st.text_input("AD SOYAD").upper()
            okul = st.text_input("OKUL").upper()
            gemi = st.text_input("GEMİ ADI").upper()
            # Telefon formatı
            tel = st.text_input("TELEFON NUMARASI (ÖR: 05xx xxx xx xx)")
        with col2:
            bas = st.date_input("STAJ BAŞLANGIÇ")
            bit = st.date_input("STAJ BİTİŞ")
            gunler = st.selectbox("STAJ GÜNLERİ", ["PAZARTESİ-SALI-ÇARŞAMBA", "ÇARŞAMBA-PERŞEMBE-CUMA"])
            bolum = st.selectbox("BÖLÜM", ["MAKİNE", "GÜVERTE"])
        
        if st.button("SİSTEME KAYDET"):
            query = "INSERT INTO stajyerler (ad_soyad, okul, gemi, telefon, baslangic, bitis, gun_grubu, bolum) VALUES (?,?,?,?,?,?,?,?)"
            conn.execute(query, (ad, okul, gemi, tel, bas, bit, gunler, bolum))
            conn.commit()
            st.success("KAYIT BAŞARILI!")
            st.rerun()

    st.subheader("📋 PERSONEL LİSTESİ")
    df = get_all_interns()
    if not df.empty:
        edited_df = st.data_editor(df, num_rows="dynamic", key="editor", hide_index=True)
        if st.button("TÜM DEĞİŞİKLİKLERİ GÜNCELLE"):
            conn.execute("DELETE FROM stajyerler")
            edited_df.to_sql('stajyerler', conn, if_exists='append', index=False)
            conn.commit()
            st.success("VERİTABANI GÜNCELLENDİ!")
    else:
        st.info("STAJYER LİSTESİ BOŞ.")

# --- SAYFA 3: İZİN SİSTEMİ ---
elif menu == "📅 İZİN SİSTEMİ":
    st.header("📅 İZİN VE DEVAMSIZLIK GİRİŞİ")
    df = get_all_interns()
    
    if not df.empty:
        col1, col2 = st.columns([1, 2])
        with col1:
            stajyer_sec = st.selectbox("STAJYER SEÇİN", df['ad_soyad'].tolist())
            s_id = df[df['ad_soyad'] == stajyer_sec]['id'].values[0]
            tarih = st.date_input("İZİN TARİHİ", format="DD/MM/YYYY")
            tip = st.radio("İZİN/DEVAMSIZLIK TİPİ", ["RAPORLU", "RAPORSUZ DEVAMSIZLIK"])
            
            if st.button("İZİNİ İŞLE"):
                conn.execute("INSERT INTO izinler (stajyer_id, izin_tarihi, izin_tipi) VALUES (?,?,?)", (int(s_id), tarih, tip))
                conn.commit()
                st.toast("İŞLEM BAŞARILI")
        
        with col2:
            st.subheader(f"📝 {stajyer_sec} İZİN GEÇMİŞİ")
            iz_df = pd.read_sql(f"SELECT id, izin_tarihi, izin_tipi FROM izinler WHERE stajyer_id = {s_id}", conn)
            st.table(iz_df)
    else:
        st.warning("PERSONEL KAYDI BULUNAMADI.")

# --- SAYFA 4: PUANTAJ VE EXCEL ---
elif menu == "📑 PUANTAJ VE EXCEL":
    st.header("📑 AYLIK PUANTAJ RAPORLAMA")
    
    c1, c2 = st.columns(2)
    ay = c1.number_input("AY", 1, 12, datetime.now().month)
    yil = c2.number_input("YIL", 2024, 2030, datetime.now().year)
    
    df_st = get_all_interns()
    if not df_st.empty:
        # Ayın günlerini oluştur
        bas_gun = datetime(yil, ay, 1)
        if ay == 12: bit_gun = datetime(yil+1, 1, 1) - timedelta(days=1)
        else: bit_gun = datetime(yil, ay+1, 1) - timedelta(days=1)
        
        gunler_range = pd.date_range(bas_gun, bit_gun)
        
        puantaj_listesi = []
        for _, row in df_st.iterrows():
            satir = {"AD SOYAD": row['ad_soyad'], "GEMİ": row['gemi'], "BÖLÜM": row['bolum']}
            leaves = get_intern_leaves(row['id'])
            
            gelinen_gun = 0
            gelinmeyen_gun = 0
            
            for d in gunler_range:
                d_str = d.strftime('%Y-%m-%d')
                gun_adi_en = d.strftime('%A')
                gun_adi_tr = TR_GUNLER[gun_adi_en]
                
                # Staj Gün Kontrolü
                staj_gunu_mu = False
                if row['gun_grubu'] == "PAZARTESİ-SALI-ÇARŞAMBA":
                    if gun_adi_tr in ["PAZARTESİ", "SALI", "ÇARŞAMBA"]: staj_gunu_mu = True
                else:
                    if gun_adi_tr in ["ÇARŞAMBA", "PERŞEMBE", "CUMA"]: staj_gunu_mu = True
                
                # İzin Kontrolü
                gunluk_izin = leaves[leaves['izin_tarihi'] == d_str]
                
                if not gunluk_izin.empty:
                    satir[d.day] = gunluk_izin['izin_tipi'].values[0]
                    gelinmeyen_gun += 1
                elif staj_gunu_mu:
                    satir[d.day] = "1"
                    gelinen_gun += 1
                else:
                    satir[d.day] = "-"
            
            satir["TOPLAM GELİS"] = gelinen_gun
            satir["TOPLAM DEVAMSIZLIK"] = gelinmeyen_gun
            puantaj_listesi.append(satir)
            
        final_df = pd.DataFrame(puantaj_listesi)
        st.dataframe(final_df, use_container_width=True)
        
        # Excel'e aktarma
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            final_df.to_excel(writer, index=False, sheet_name='PUANTAJ')
            # Hücre biçimlendirme eklenebilir
        
        st.download_button(
            label="📥 PUANTAJI EXCEL OLARAK İNDİR",
            data=output.getvalue(),
            file_name=f"PUANTAJ_{ay}_{yil}.xlsx",
            mime="application/vnd.ms-excel"
        )
