import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
import io
import plotly.express as px

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="STAJYER PLANLAMA VE YÖNETİM SİSTEMİ", layout="wide")

# TÜM METİNLERİ BÜYÜK HARF YAPMA VE MODERN STİL (CSS)
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
    # Düzenleme ve silme için ID sütununu da alıyoruz
    return pd.read_sql(f"SELECT id, izin_tarihi, izin_tipi FROM izinler WHERE stajyer_id = {intern_id}", conn)

TR_GUNLER = {
    'Monday': 'PAZARTESİ', 'Tuesday': 'SALI', 'Wednesday': 'ÇARŞAMBA',
    'Thursday': 'PERŞEMBE', 'Friday': 'CUMA', 'Saturday': 'CUMARTESİ', 'Sunday': 'PAZAR'
}

def get_resmi_tatiller(yil):
    tatiller = [f"{yil}-01-01", f"{yil}-04-23", f"{yil}-05-01", f"{yil}-05-19", f"{yil}-07-15", f"{yil}-08-30", f"{yil}-10-29"]
    if yil == 2026:
        tatiller.extend(["2026-03-19", "2026-03-20", "2026-03-21", "2026-03-22", 
                         "2026-05-26", "2026-05-27", "2026-05-28", "2026-05-29", "2026-05-30"])
    return tatiller

# --- SIDEBAR NAVİGASYON ---
st.sidebar.title("⚓ NAVİGASYON")
menu = st.sidebar.radio("SAYFA SEÇİNİZ:", ["📊 DASHBOARD", "👤 PERSONEL YÖNETİMİ", "📅 İZİN SİSTEMİ", "📑 PUANTAJ VE EXCEL"])

# --- 1. DASHBOARD ---
if menu == "📊 DASHBOARD":
    st.header("📈 GENEL DURUM VE ANALİZ")
    df_stajyer = get_all_interns()
    if not df_stajyer.empty:
        col1, col2, col3 = st.columns([1, 2, 2])
        with col1: st.metric("TOPLAM STAJYER", len(df_stajyer))
        with col2:
            gemi_counts = df_stajyer['gemi'].value_counts().reset_index()
            gemi_counts.columns = ['GEMİ', 'SAYI']
            st.plotly_chart(px.bar(gemi_counts, x='GEMİ', y='SAYI', title="🚢 GEMİ BAZLI DAĞILIM"), use_container_width=True)
        with col3:
            bolum_counts = df_stajyer['bolum'].value_counts().reset_index()
            bolum_counts.columns = ['BÖLÜM', 'SAYI']
            st.plotly_chart(px.pie(bolum_counts, values='SAYI', names='BÖLÜM', title="🛠️ BÖLÜM DAĞILIMI", hole=0.3), use_container_width=True)

# --- 2. PERSONEL YÖNETİMİ ---
elif menu == "👤 PERSONEL YÖNETİMİ":
    st.header("👤 STAJYER KAYIT VE YÖNETİMİ")
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
            conn.execute("INSERT INTO stajyerler (ad_soyad, okul, gemi, telefon, baslangic, bitis, gun_grubu, bolum) VALUES (?,?,?,?,?,?,?,?)", (ad, okul, gemi, tel, bas, bit, gunler, bolum))
            conn.commit(); st.success(f"{ad} EKLENDİ!"); st.rerun()
    
    df = get_all_interns()
    if not df.empty:
        st.subheader("📝 PERSONEL LİSTESİNİ DÜZENLE/SİL")
        edited_df = st.data_editor(df, num_rows="dynamic", key="main_editor", hide_index=True)
        if st.button("🔄 TÜMÜNÜ GÜNCELLE"):
            conn.execute("DELETE FROM stajyerler")
            edited_df.to_sql('stajyerler', conn, if_exists='append', index=False)
            conn.commit(); st.success("PERSONEL LİSTESİ GÜNCELLENDİ!"); st.rerun()

# --- 3. İZİN SİSTEMİ (SORUNLU OLAN KISIM DÜZELTİLDİ) ---
elif menu == "📅 İZİN SİSTEMİ":
    st.header("📅 İZİN YÖNETİMİ")
    df = get_all_interns()
    
    if not df.empty:
        # Kişi Seçimi
        s_ad = st.selectbox("STAJYER SEÇİN", df['ad_soyad'].tolist())
        s_id = int(df[df['ad_soyad'] == s_ad]['id'].values[0])
        
        col_ekle, col_duzenle = st.columns([1, 2])
        
        with col_ekle:
            st.subheader("➕ İZİN EKLE")
            i_tarih = st.date_input("İZİN TARİHİ", key="yeni_izin_tarih")
            i_tip = st.radio("DURUM", ["RAPORLU", "RAPORSUZ DEVAMSIZLIK"], key="yeni_izin_tip")
            if st.button("İZİNİ KAYDET"):
                conn.execute("INSERT INTO izinler (stajyer_id, izin_tarihi, izin_tipi) VALUES (?,?,?)", (s_id, i_tarih, i_tip))
                conn.commit(); st.success("İZİN BAŞARIYLA EKLENDİ!"); st.rerun()
        
        with col_duzenle:
            st.subheader("📝 İZİN DÜZENLE / SİL")
            iz_df = get_intern_leaves(s_id)
            
            if not iz_df.empty:
                # Kullanıcı tabloyu editler
                edited_iz_df = st.data_editor(
                    iz_df, 
                    column_order=("izin_tarihi", "izin_tipi"), 
                    num_rows="dynamic", 
                    key="izin_editor",
                    use_container_width=True,
                    hide_index=True
                )
                
                c1, c2 = st.columns(2)
                if c1.button("🔄 DEĞİŞİKLİKLERİ KAYDET"):
                    # Önce o kişinin tüm izinlerini siliyoruz, sonra editlenmiş halini geri yazıyoruz
                    conn.execute(f"DELETE FROM izinler WHERE stajyer_id = {s_id}")
                    for _, row in edited_iz_df.iterrows():
                        if pd.notna(row['izin_tarihi']):
                            conn.execute("INSERT INTO izinler (stajyer_id, izin_tarihi, izin_tipi) VALUES (?,?,?)", 
                                         (s_id, row['izin_tarihi'], row['izin_tipi']))
                    conn.commit()
                    st.success("İZİN KAYITLARI GÜNCELLENDİ!"); st.rerun()
                
                st.divider()
                st.caption("NOT: Tablodan satırı seçip 'Delete' tuşuna basarak veya bilgiyi değiştirerek güncelleyebilirsiniz.")
            else:
                st.info("BU KİŞİYE AİT KAYITLI İZİN BULUNMAMAKTADIR.")
    else:
        st.warning("SİSTEMDE KAYITLI STAJYER BULUNAMADI.")

# --- 4. PUANTAJ VE EXCEL ---
elif menu == "📑 PUANTAJ VE EXCEL":
    st.header("📑 AYLIK PUANTAJ VE TOPLAM DEVAM")
    c1, c2 = st.columns(2)
    ay = c1.number_input("AY", 1, 12, datetime.now().month)
    yil = c2.number_input("YIL", 2024, 2030, datetime.now().year)
    
    df_st = get_all_interns()
    if not df_st.empty:
        bas = datetime(yil, ay, 1)
        bit = (datetime(yil, ay+1, 1) if ay < 12 else datetime(yil+1, 1, 1)) - timedelta(days=1)
        gunler_range = pd.date_range(bas, bit)
        tatiller = get_resmi_tatiller(yil)
        
        puantaj_res = []
        genel_toplam_gun = 0
        
        for _, row in df_st.iterrows():
            satir = {"AD SOYAD": row['ad_soyad'], "GEMİ": row['gemi'], "BÖLÜM": row['bolum']}
            leaves = get_intern_leaves(row['id'])
            kisi_toplam_gun = 0
            
            for d in gunler_range:
                d_str = d.strftime('%Y-%m-%d')
                gun_tr = TR_GUNLER[d.strftime('%A')]
                is_tatil = (gun_tr in ["CUMARTESİ", "PAZAR"]) or (d_str in tatiller)
                
                if is_tatil:
                    satir[d.day] = "TATİL"
                else:
                    staj_gunu = (gun_tr in ["PAZARTESİ", "SALI", "ÇARŞAMBA"]) if row['gun_grubu'] == "PAZARTESİ-SALI-ÇARŞAMBA" else (gun_tr in ["ÇARŞAMBA", "PERŞEMBE", "CUMA"])
                    # İzin sorgulama
                    izin_durum = leaves[leaves['izin_tarihi'] == d_str]
                    
                    if not izin_durum.empty:
                        satir[d.day] = izin_durum['izin_tipi'].values[0]
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
            worksheet.write(len(p_df) + 2, 0, "TÜM ÖĞRENCİLER GENEL TOPLAM:")
            worksheet.write(len(p_df) + 2, 1, genel_toplam_gun)
            
        st.download_button(label="📥 EXCEL OLARAK İNDİR", data=output.getvalue(), file_name=f"PUANTAJ_{ay}_{yil}.xlsx")
