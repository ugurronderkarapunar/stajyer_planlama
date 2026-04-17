import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
import io

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="STAJYER PLANLAMA SİSTEMİ", layout="wide")

# Modern Stil ve Büyük Harf Zorunluluğu için CSS
st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    h1, h2, h3, label, .stButton>button { 
        text-transform: uppercase !important; 
        font-weight: bold;
    }
    .stDataFrame { border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

# --- VERİTABANI YÖNETİMİ ---
def init_db():
    conn = sqlite3.connect('stajyer_takip.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS stajyerler
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, ad_soyad TEXT, okul TEXT, 
                  gemi TEXT, telefon TEXT, baslangic DATE, bitis DATE, 
                  gun_grubu TEXT, bolum TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS izinler
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, stajyer_id INTEGER, 
                  izin_tarihi DATE, FOREIGN KEY(stajyer_id) REFERENCES stajyerler(id))''')
    conn.commit()
    return conn

conn = init_db()

# --- YARDIMCI FONKSİYONLAR ---
def get_all_interns():
    return pd.read_sql("SELECT * FROM stajyerler", conn)

def get_intern_leaves(intern_id):
    query = f"SELECT izin_tarihi FROM izinler WHERE stajyer_id = {intern_id}"
    return pd.read_sql(query, conn)['izin_tarihi'].tolist()

# --- SIDEBAR / NAVİGASYON ---
st.sidebar.title("⚓ NAVİGASYON")
menu = st.sidebar.radio("SAYFA SEÇİNİZ:", ["PERSONEL YÖNETİMİ", "İZİN SİSTEMİ", "PUANTAJ VE EXCEL"])

# --- SAYFA 1: PERSONEL YÖNETİMİ ---
if menu == "PERSONEL YÖNETİMİ":
    st.header("👤 STAJYER EKLEME VE DÜZENLEME")
    
    with st.expander("➕ YENİ STAJYER EKLE"):
        col1, col2 = st.columns(2)
        with col1:
            ad = st.text_input("AD SOYAD").upper()
            okul = st.text_input("OKUL").upper()
            gemi = st.text_input("GEMİ ADI").upper()
            tel = st.text_input("TELEFON NUMARASI")
        with col2:
            bas = st.date_input("STAJ BAŞLANGIÇ")
            bit = st.date_input("STAJ BİTİŞ")
            gunler = st.selectbox("STAJ GÜNLERİ", ["PAZARTESİ-SALI-ÇARŞAMBA", "ÇARŞAMBA-PERŞEMBE-CUMA"])
            bolum = st.selectbox("BÖLÜM", ["MAKİNE", "GÜVERTE"])
        
        if st.button("KAYDET"):
            query = "INSERT INTO stajyerler (ad_soyad, okul, gemi, telefon, baslangic, bitis, gun_grubu, bolum) VALUES (?,?,?,?,?,?,?,?)"
            conn.execute(query, (ad, okul, gemi, tel, bas, bit, gunler, bolum))
            conn.commit()
            st.success("KAYIT BAŞARILI!")
            st.rerun()

    st.subheader("📋 MEVCUT STAJYER LİSTESİ")
    df = get_all_interns()
    
    if not df.empty:
        # Düzenleme ve Silme için Data Editor
        edited_df = st.data_editor(df, num_rows="dynamic", key="intern_editor", hide_index=True)
        
        if st.button("DEĞİŞİKLİKLERİ KAYDET"):
            # Basitlik adına tabloyu sıfırlayıp tekrar yazar (Production'da ID bazlı update önerilir)
            conn.execute("DELETE FROM stajyerler")
            edited_df.to_sql('stajyerler', conn, if_exists='append', index=False)
            conn.commit()
            st.success("LİSTE GÜNCELLENDİ!")
    else:
        st.info("HENÜZ KAYITLI STAJYER YOK.")

# --- SAYFA 2: İZİN SİSTEMİ ---
elif menu == "İZİN SİSTEMİ":
    st.header("📅 İZİN GİRİŞ SİSTEMİ")
    df = get_all_interns()
    
    if not df.empty:
        col1, col2 = st.columns([1, 2])
        with col1:
            secili_stajyer = st.selectbox("STAJYER SEÇİN", df['ad_soyad'].tolist())
            stajyer_id = df[df['ad_soyad'] == secili_stajyer]['id'].values[0]
            izin_tarihi = st.date_input("İZİN TARİHİ SEÇİN")
            
            if st.button("İZİN EKLE"):
                conn.execute("INSERT INTO izinler (stajyer_id, izin_tarihi) VALUES (?,?)", (int(stajyer_id), izin_tarihi))
                conn.commit()
                st.toast(f"{secili_stajyer} İÇİN İZİN TANIMLANDI.")
        
        with col2:
            st.subheader("GİRİLEN İZİNLER")
            izinler_df = pd.read_sql(f"SELECT id, izin_tarihi FROM izinler WHERE stajyer_id = {stajyer_id}", conn)
            st.write(izinler_df)
            if st.button("SEÇİLİ İZİNLERİ SİL (ID GİREREK)"):
                # Gelişmiş silme buraya eklenebilir
                pass
    else:
        st.warning("ÖNCE PERSONEL EKLEMELİSİNİZ.")

# --- SAYFA 3: PUANTAJ VE EXCEL ---
elif menu == "PUANTAJ VE EXCEL":
    st.header("📊 AYLIk PUANTAJ CETVELİ")
    
    ay = st.number_input("AY SEÇİN (1-12)", min_value=1, max_value=12, value=datetime.now().month)
    yil = st.number_input("YIL SEÇİN", min_value=2024, max_value=2030, value=datetime.now().year)
    
    df = get_all_interns()
    
    if not df.empty:
        # Puantaj Hesaplama Mantığı
        gun_sayisi = 31 # Basitleştirme için 31 gün
        puantaj_data = []
        
        for index, row in df.iterrows():
            satir = {"AD SOYAD": row['ad_soyad'], "GEMİ": row['gemi'], "BÖLÜM": row['bolum']}
            izinler = get_intern_leaves(row['id'])
            izinler = [str(d) for d in izinler]
            
            for gun in range(1, gun_sayisi + 1):
                tarih = datetime(yil, ay, gun) if gun <= 28 else (datetime(yil, ay, 1) + timedelta(days=gun-1))
                if tarih.month != ay: continue
                
                tarih_str = tarih.strftime('%Y-%m-%d')
                gun_adi = tarih.strftime('%A') # İngilizce gün adı
                
                # Staj Günleri Kontrolü
                mesai_gunu = False
                if row['gun_grubu'] == "PAZARTESİ-SALI-ÇARŞAMBA":
                    if gun_adi in ['Monday', 'Tuesday', 'Wednesday']: mesai_gunu = True
                else:
                    if gun_adi in ['Wednesday', 'Thursday', 'Friday']: mesai_gunu = True
                
                if tarih_str in izinler:
                    satir[gun] = "İZİN"
                elif mesai_gunu:
                    satir[gun] = "X"
                else:
                    satir[gun] = "-"
            
            puantaj_data.append(satir)
        
        puantaj_df = pd.DataFrame(puantaj_data)
        st.dataframe(puantaj_df)
        
        # Excel Export
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            puantaj_df.to_excel(writer, index=False, sheet_name='Puantaj')
            writer.close()
        
        st.download_button(
            label="📥 PUANTAJI EXCEL OLARAK İNDİR",
            data=buffer,
            file_name=f"puantaj_{ay}_{yil}.xlsx",
            mime="application/vnd.ms-excel"
        )
