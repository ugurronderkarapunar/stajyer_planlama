import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
import io
import plotly.express as px

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="STAJYER PLANLAMA SİSTEMİ", layout="wide")

# Tüm metinleri büyük harf yapma ve modern stil (CSS)
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    h1, h2, h3, h4, label, .stButton>button, .stMarkdown, p, span { 
        text-transform: uppercase !important; 
        font-weight: bold !important;
    }
    .stDataFrame, .stTable { border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

# --- VERİTABANI YÖNETİMİ ---
def init_db():
    conn = sqlite3.connect('stajyer_takip_sistemi.db', check_same_thread=False)
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
    return pd.read_sql(f"SELECT izin_tarihi, izin_tipi FROM izinler WHERE stajyer_id = {intern_id}", conn)

TR_GUNLER = {
    'Monday': 'PAZARTESİ', 'Tuesday': 'SALI', 'Wednesday': 'ÇARŞAMBA',
    'Thursday': 'PERŞEMBE', 'Friday': 'CUMA', 'Saturday': 'CUMARTESİ', 'Sunday': 'PAZAR'
}

# --- SIDEBAR NAVİGASYON ---
st.sidebar.title("⚓ NAVİGASYON")
menu = st.sidebar.radio("SAYFA SEÇİNİZ:", ["📊 DASHBOARD", "👤 PERSONEL YÖNETİMİ", "📅 İZİN SİSTEMİ", "📑 PUANTAJ VE EXCEL"])

# --- 1. SAYFA: DASHBOARD ---
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
            fig_bar = px.bar(gemi_counts, x='GEMİ', y='SAYI', title="🚢 GEMİ BAZLI DAĞILIM", color='GEMİ')
            st.plotly_chart(fig_bar, use_container_width=True)
            
        with col3:
            bolum_counts = df_stajyer['bolum'].value_counts().reset_index()
            bolum_counts.columns = ['BÖLÜM', 'SAYI']
            fig_pie = px.pie(bolum_counts, values='SAYI', names='BÖLÜM', title="🛠️ BÖLÜM DAĞILIMI", hole=0.3)
            st.plotly_chart(fig_pie, use_container_width=True)

        st.divider()
        st.subheader("🗓️ AYLIK DEVAMLILIK ANALİZİ")
        c1, c2 = st.columns(2)
        d_ay = c1.number_input("ANALİZ AYI", 1, 12, datetime.now().month, key="db_ay")
        d_yil = c2.number_input("ANALİZ YILI", 2024, 2030, datetime.now().year, key="db_yil")

        db_ozet = []
        for _, row in df_stajyer.iterrows():
            leaves = get_intern_leaves(row['id'])
            bas = datetime(d_yil, d_ay, 1)
            next_month = bas.replace(day=28) + timedelta(days=4)
            bit = next_month - timedelta(days=next_month.day)
            gunler = pd.date_range(bas, bit)
            
            gelen, gelmeyen = 0, 0
            for d in gunler:
                d_str = d.strftime('%Y-%m-%d')
                gun_tr = TR_GUNLER[d.strftime('%A')]
                is_work_day = False
                if row['gun_grubu'] == "PAZARTESİ-SALI-ÇARŞAMBA":
                    if gun_tr in ["PAZARTESİ", "SALI", "ÇARŞAMBA"]: is_work_day = True
                else:
                    if gun_tr in ["ÇARŞAMBA", "PERŞEMBE", "CUMA"]: is_work_day = True
                
                has_izin = not leaves[leaves['izin_tarihi'] == d_str].empty
                if has_izin: gelmeyen += 1
                elif is_work_day: gelen += 1
            
            db_ozet.append({"STAJYER": row['ad_soyad'], "GEMİ": row['gemi'], "GELDİĞİ GÜN": gelen, "GELMEDİĞİ GÜN": gelmeyen})
        
        st.table(pd.DataFrame(db_ozet))
    else:
        st.info("HENÜZ KAYITLI PERSONEL YOK.")

# --- 2. SAYFA: PERSONEL YÖNETİMİ ---
elif menu == "👤 PERSONEL YÖNETİMİ":
    st.header("👤 STAJYER KAYIT VE DÜZENLEME")
    with st.expander("➕ YENİ STAJYER EKLE"):
        c1, c2 = st.columns(2)
        with c1:
            ad = st.text_input("AD SOYAD").upper()
            okul = st.text_input("OKUL").upper()
            gemi = st.text_input("GEMİ ADI").upper()
            tel = st.text_input("TELEFON NUMARASI")
        with c2:
            bas = st.date_input("STAJ BAŞLANGIÇ")
            bit = st.date_input("STAJ BİTİŞ")
            gunler = st.selectbox("STAJ GÜNLERİ", ["PAZARTESİ-SALI-ÇARŞAMBA", "ÇARŞAMBA-PERŞEMBE-CUMA"])
            bolum = st.selectbox("BÖLÜM", ["MAKİNE", "GÜVERTE"])
        
        if st.button("KAYDI TAMAMLA"):
            conn.execute("INSERT INTO stajyerler (ad_soyad, okul, gemi, telefon, baslangic, bitis, gun_grubu, bolum) VALUES (?,?,?,?,?,?,?,?)",
                         (ad, okul, gemi, tel, bas, bit, gunler, bolum))
            conn.commit()
            st.success("KAYIT BAŞARILI!"); st.rerun()

    df = get_all_interns()
    if not df.empty:
        st.subheader("📋 PERSONEL LİSTESİ (DÜZENLEME VE SİLME)")
        edited_df = st.data_editor(df, num_rows="dynamic", key="main_editor", hide_index=True)
        if st.button("TÜM DEĞİŞİKLİKLERİ KAYDET"):
            conn.execute("DELETE FROM stajyerler")
            edited_df.to_sql('stajyerler', conn, if_exists='append', index=False)
            conn.commit(); st.success("GÜNCELLENDİ!")
    else:
        st.info("LİSTE BOŞ.")

# --- 3. SAYFA: İZİN SİSTEMİ ---
elif menu == "📅 İZİN SİSTEMİ":
    st.header("📅 İZİN VE DEVAMSIZLIK GİRİŞİ")
    df = get_all_interns()
    if not df.empty:
        c1, c2 = st.columns([1, 2])
        with c1:
            s_ad = st.selectbox("STAJYER SEÇİN", df['ad_soyad'].tolist())
            s_id = df[df['ad_soyad'] == s_ad]['id'].values[0]
            i_tarih = st.date_input("İZİN TARİHİ")
            i_tip = st.radio("DURUM", ["RAPORLU", "RAPORSUZ DEVAMSIZLIK"])
            if st.button("İZİNİ KAYDET"):
                conn.execute("INSERT INTO izinler (stajyer_id, izin_tarihi, izin_tipi) VALUES (?,?,?)", (int(s_id), i_tarih, i_tip))
                conn.commit(); st.toast("İŞLENDİ")
        with c2:
            st.subheader("GİRİLEN İZİNLER")
            st.write(pd.read_sql(f"SELECT id, izin_tarihi, izin_tipi FROM izinler WHERE stajyer_id = {s_id}", conn))
    else:
        st.warning("PERSONEL YOK.")

# --- 4. SAYFA: PUANTAJ VE EXCEL ---
elif menu == "📑 PUANTAJ VE EXCEL":
    st.header("📑 AYLIK PUANTAJ CETVELİ")
    ay = st.number_input("AY", 1, 12, datetime.now().month)
    yil = st.number_input("YIL", 2024, 2030, datetime.now().year)
    
    df_st = get_all_interns()
    if not df_st.empty:
        bas = datetime(yil, ay, 1)
        next_month = bas.replace(day=28) + timedelta(days=4)
        bit = next_month - timedelta(days=next_month.day)
        gunler_range = pd.date_range(bas, bit)
        
        puantaj_res = []
        for _, row in df_st.iterrows():
            satir = {"AD SOYAD": row['ad_soyad'], "GEMİ": row['gemi'], "BÖLÜM": row['bolum']}
            leaves = get_intern_leaves(row['id'])
            for d in gunler_range:
                d_str = d.strftime('%Y-%m-%d')
                gun_tr = TR_GUNLER[d.strftime('%A')]
                staj_gunu = (gun_tr in ["PAZARTESİ", "SALI", "ÇARŞAMBA"]) if row['gun_grubu'] == "PAZARTESİ-SALI-ÇARŞAMBA" else (gun_tr in ["ÇARŞAMBA", "PERŞEMBE", "CUMA"])
                
                izin_durum = leaves[leaves['izin_tarihi'] == d_str]
                if not izin_durum.empty: satir[d.day] = izin_durum['izin_tipi'].values[0]
                elif staj_gunu: satir[d.day] = "1"
                else: satir[d.day] = "-"
            puantaj_res.append(satir)
            
        p_df = pd.DataFrame(puantaj_res)
        st.dataframe(p_df)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            p_df.to_excel(writer, index=False, sheet_name='PUANTAJ')
        st.download_button(label="📥 EXCEL OLARAK İNDİR", data=output.getvalue(), file_name=f"PUANTAJ_{ay}_{yil}.xlsx", mime="application/vnd.ms-excel")
