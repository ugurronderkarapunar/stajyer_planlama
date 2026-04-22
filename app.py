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
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'stajyer_takip_sistemi.db')

@st.cache_resource
def init_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()

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

    c.execute('''CREATE TABLE IF NOT EXISTS izinler
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  stajyer_id INTEGER,
                  izin_baslangic DATE,
                  izin_bitis DATE,
                  izin_tipi TEXT,
                  FOREIGN KEY(stajyer_id) REFERENCES stajyerler(id))''')

    mevcut_kolonlar = [r[1] for r in c.execute("PRAGMA table_info(stajyerler)").fetchall()]
    for kolon, tip in [("sicil_no", "TEXT"), ("notlar", "TEXT")]:
        if kolon not in mevcut_kolonlar:
            c.execute(f"ALTER TABLE stajyerler ADD COLUMN {kolon} {tip}")

    izin_kolonlar = [r[1] for r in c.execute("PRAGMA table_info(izinler)").fetchall()]
    if "izin_tarihi" in izin_kolonlar:
        c.execute('''CREATE TABLE IF NOT EXISTS izinler_yeni
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      stajyer_id INTEGER,
                      izin_baslangic DATE,
                      izin_bitis DATE,
                      izin_tipi TEXT,
                      FOREIGN KEY(stajyer_id) REFERENCES stajyerler(id))''')
        c.execute('''INSERT INTO izinler_yeni (id, stajyer_id, izin_baslangic, izin_bitis, izin_tipi)
                     SELECT id, stajyer_id, izin_tarihi, izin_tarihi, izin_tipi FROM izinler''')
        c.execute("DROP TABLE izinler")
        c.execute("ALTER TABLE izinler_yeni RENAME TO izinler")
    elif "izin_bitis" not in izin_kolonlar:
        c.execute("ALTER TABLE izinler ADD COLUMN izin_bitis DATE")
        c.execute("UPDATE izinler SET izin_bitis = izin_baslangic WHERE izin_bitis IS NULL")

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
    for _, row in leaves_df.iterrows():
        bas = str(row['izin_baslangic'])
        bit = str(row['izin_bitis']) if pd.notna(row['izin_bitis']) else bas
        if bas <= d_str <= bit:
            return row['izin_tipi']
    return None


def stajyer_istatistik(row, baslangic_dt, bitis_dt, tatiller_listesi):
    gunler_range = pd.date_range(baslangic_dt, bitis_dt)
    leaves = get_intern_leaves(row['id'])
    toplam_staj_gunu = 0
    devam_gunu = 0
    raporlu_gun = 0
    raporsuz_gun = 0

    for d in gunler_range:
        d_str  = d.strftime('%Y-%m-%d')
        gun_tr = TR_GUNLER[d.strftime('%A')]
        is_tatil = (gun_tr in ["CUMARTESİ", "PAZAR"]) or (d_str in tatiller_listesi)
        if is_tatil:
            continue

        # FIX: Türkçe karakterler düzeltildi (İ, Ş, Ç)
        staj_gunu = (
            gun_tr in ["PAZARTESİ", "SALI", "ÇARŞAMBA"]
            if row['gun_grubu'] == "PAZARTESİ-SALI-ÇARŞAMBA"
            else gun_tr in ["ÇARŞAMBA", "PERŞEMBE", "CUMA"]
        )
        if not staj_gunu:
            continue

        toplam_staj_gunu += 1
        izin_tipi = izin_var_mi(leaves, d_str)
        if izin_tipi == "RAPORLU":
            raporlu_gun += 1
        elif izin_tipi == "RAPORSUZ DEVAMSIZLIK":
            raporsuz_gun += 1
        else:
            devam_gunu += 1

    oran = round(devam_gunu / toplam_staj_gunu * 100, 1) if toplam_staj_gunu > 0 else 0
    return {
        "toplam_staj_gunu": toplam_staj_gunu,
        "devam_gunu": devam_gunu,
        "raporlu_gun": raporlu_gun,
        "raporsuz_gun": raporsuz_gun,
        "devam_orani": oran,
    }

# --- SIDEBAR NAVİGASYON ---
st.sidebar.title("⚓ NAVİGASYON")
menu = st.sidebar.radio("SAYFA SEÇİNİZ:", [
    "📊 DASHBOARD",
    "👤 PERSONEL YÖNETİMİ",
    "📅 İZİN SİSTEMİ",
    "📑 PUANTAJ VE EXCEL",
    "👁️ KİŞİ BAZLI DEVAM RAPORU",
    "🔍 GELİŞMİŞ FİLTRELEME",
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
            sicil  = st.text_input("SİCİL NO")
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
            notlar = st.text_area("NOTLAR (ÖĞRENCİ / GEMİ / OKUL BAZLI)", height=80)

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
            i_bas  = st.date_input("İZİN BAŞLANGIÇ TARİHİ", key="izin_bas")
            i_bit  = st.date_input("İZİN BİTİŞ TARİHİ", key="izin_bit", value=i_bas)
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
                    izin_tipi = izin_var_mi(leaves, d_str)

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


# =============================================================
# 5. KİŞİ BAZLI DEVAM RAPORU
# =============================================================
elif menu == "👁️ KİŞİ BAZLI DEVAM RAPORU":
    st.header("👁️ KİŞİ BAZLI DEVAM RAPORU")
    df_all = get_all_interns()

    if df_all.empty:
        st.warning("SİSTEMDE KAYITLI STAJYER BULUNAMADI.")
    else:
        col_f1, col_f2, col_f3 = st.columns([2, 1, 1])
        with col_f1:
            secim = st.selectbox("STAJYER SEÇİN (VEYA TÜMÜ)", ["— TÜMÜ —"] + df_all['ad_soyad'].tolist())
        with col_f2:
            r_bas = st.date_input("BAŞLANGIÇ", datetime(datetime.now().year, 1, 1).date(), key="r_bas")
        with col_f3:
            r_bit = st.date_input("BİTİŞ", datetime.now().date(), key="r_bit")

        if r_bit < r_bas:
            st.error("BİTİŞ TARİHİ BAŞLANGIÇTAN ÖNCE OLAMAZ!")
            st.stop()

        tatiller = get_resmi_tatiller(r_bas.year)
        if r_bas.year != r_bit.year:
            tatiller += get_resmi_tatiller(r_bit.year)

        filtre_df = df_all if secim == "— TÜMÜ —" else df_all[df_all['ad_soyad'] == secim]
        istat_listesi = []
        for _, row in filtre_df.iterrows():
            ist = stajyer_istatistik(row, r_bas, r_bit, tatiller)
            ist["AD SOYAD"] = row['ad_soyad']
            ist["GEMİ"]    = row['gemi']
            ist["BÖLÜM"]   = row['bolum']
            ist["SİCİL"]   = row.get('sicil_no', '')
            istat_listesi.append(ist)

        if secim != "— TÜMÜ —" and len(istat_listesi) == 1:
            ist = istat_listesi[0]
            st.subheader(f"📋 {secim} — DETAY RAPOR")
            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("TOPLAM STAJ GÜNÜ",    ist["toplam_staj_gunu"])
            m2.metric("DEVAM GÜNÜ",          ist["devam_gunu"])
            m3.metric("RAPORLU",             ist["raporlu_gun"])
            m4.metric("RAPORSUZ DEVAMSIZLIK",ist["raporsuz_gun"])
            m5.metric("DEVAM ORANI",         f"%{ist['devam_orani']}")

            st.progress(int(ist["devam_orani"]))

            izinler_kisi = get_intern_leaves(int(df_all[df_all['ad_soyad'] == secim]['id'].values[0]))
            if not izinler_kisi.empty:
                st.subheader("📅 İZİN GEÇMİŞİ")
                izinler_kisi['SÜRE (GÜN)'] = (
                    pd.to_datetime(izinler_kisi['izin_bitis']) -
                    pd.to_datetime(izinler_kisi['izin_baslangic'])
                ).dt.days + 1
                st.dataframe(izinler_kisi[['izin_baslangic','izin_bitis','izin_tipi','SÜRE (GÜN)']].rename(columns={
                    'izin_baslangic': 'BAŞLANGIÇ',
                    'izin_bitis': 'BİTİŞ',
                    'izin_tipi': 'TİP'
                }), use_container_width=True, hide_index=True)
        else:
            istat_df = pd.DataFrame(istat_listesi)[[
                "SİCİL","AD SOYAD","GEMİ","BÖLÜM",
                "toplam_staj_gunu","devam_gunu","raporlu_gun","raporsuz_gun","devam_orani"
            ]].rename(columns={
                "toplam_staj_gunu": "TOPLAM GÜN",
                "devam_gunu":       "DEVAM",
                "raporlu_gun":      "RAPORLU",
                "raporsuz_gun":     "RAPORSUZ",
                "devam_orani":      "DEVAM %",
            })

            # FIX: background_gradient (matplotlib gerektirir) kaldırıldı
            # Devam oranını görsel olarak ifade etmek için Plotly kullanılıyor
            st.dataframe(istat_df, use_container_width=True, hide_index=True)

            # Devam % renk göstergesi ayrı bir bar chart ile
            fig_oran_tablo = px.bar(
                istat_df.sort_values("DEVAM %", ascending=False),
                x="AD SOYAD", y="DEVAM %",
                title="📊 DEVAM ORANLARI — RENK SKALASI",
                color="DEVAM %",
                color_continuous_scale="RdYlGn",
                range_color=[0, 100],
                text="DEVAM %"
            )
            fig_oran_tablo.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
            fig_oran_tablo.add_hline(y=80, line_dash="dash", line_color="navy",
                                     annotation_text="80% EŞİĞİ")
            st.plotly_chart(fig_oran_tablo, use_container_width=True)

            col_g1, col_g2 = st.columns(2)
            with col_g1:
                fig_bar = px.bar(
                    istat_df, x="AD SOYAD", y=["DEVAM","RAPORLU","RAPORSUZ"],
                    title="📊 KİŞİ BAZLI DEVAM KARŞILAŞTIRMASI",
                    barmode="stack", color_discrete_map={
                        "DEVAM": "#2ecc71", "RAPORLU": "#f39c12", "RAPORSUZ": "#e74c3c"
                    }
                )
                st.plotly_chart(fig_bar, use_container_width=True)
            with col_g2:
                fig_oran = px.bar(
                    istat_df.sort_values("DEVAM %"),
                    x="DEVAM %", y="AD SOYAD",
                    orientation='h',
                    title="📈 DEVAM ORANLARI (%)",
                    color="DEVAM %",
                    color_continuous_scale="RdYlGn",
                    range_color=[0, 100]
                )
                fig_oran.add_vline(x=80, line_dash="dash", line_color="navy",
                                   annotation_text="80% EŞİĞİ")
                st.plotly_chart(fig_oran, use_container_width=True)

            out2 = io.BytesIO()
            with pd.ExcelWriter(out2, engine='xlsxwriter') as writer:
                istat_df.to_excel(writer, index=False, sheet_name='DEVAM_RAPORU')
            st.download_button("📥 RAPORU EXCEL OLARAK İNDİR",
                               data=out2.getvalue(),
                               file_name=f"DEVAM_RAPORU_{r_bas}_{r_bit}.xlsx")

# =============================================================
# 6. GELİŞMİŞ FİLTRELEME
# =============================================================
elif menu == "🔍 GELİŞMİŞ FİLTRELEME":
    st.header("🔍 GELİŞMİŞ FİLTRELEME VE ARAMA")
    df_all = get_all_interns()

    if df_all.empty:
        st.warning("SİSTEMDE KAYITLI STAJYER BULUNAMADI.")
    else:
        with st.expander("🎛️ FİLTRELER", expanded=True):
            fc1, fc2, fc3, fc4 = st.columns(4)
            with fc1:
                gemiler     = ["TÜMÜ"] + sorted(df_all['gemi'].dropna().unique().tolist())
                f_gemi      = st.selectbox("GEMİ", gemiler)
            with fc2:
                bolumler    = ["TÜMÜ"] + sorted(df_all['bolum'].dropna().unique().tolist())
                f_bolum     = st.selectbox("BÖLÜM", bolumler)
            with fc3:
                gun_gruplari = ["TÜMÜ"] + sorted(df_all['gun_grubu'].dropna().unique().tolist())
                f_gun_grubu  = st.selectbox("GÜN GRUBU", gun_gruplari)
            with fc4:
                f_ad = st.text_input("AD SOYAD ARA")

        bugun = datetime.now().date()
        df_all['baslangic'] = pd.to_datetime(df_all['baslangic']).dt.date
        df_all['bitis']     = pd.to_datetime(df_all['bitis']).dt.date
        df_all['DURUM'] = df_all['bitis'].apply(
            lambda b: "✅ AKTİF" if pd.notna(b) and b >= bugun else "⏹️ TAMAMLANDI"
        )

        sonuc = df_all.copy()
        if f_gemi     != "TÜMÜ":   sonuc = sonuc[sonuc['gemi']     == f_gemi]
        if f_bolum    != "TÜMÜ":   sonuc = sonuc[sonuc['bolum']    == f_bolum]
        if f_gun_grubu!= "TÜMÜ":   sonuc = sonuc[sonuc['gun_grubu']== f_gun_grubu]
        if f_ad.strip():           sonuc = sonuc[sonuc['ad_soyad'].str.contains(f_ad.upper(), na=False)]

        sm1, sm2, sm3, sm4 = st.columns(4)
        sm1.metric("SONUÇ SAYISI",    len(sonuc))
        sm2.metric("AKTİF",          len(sonuc[sonuc['DURUM'] == "✅ AKTİF"]))
        sm3.metric("TAMAMLANDI",     len(sonuc[sonuc['DURUM'] == "⏹️ TAMAMLANDI"]))
        aktif_gemiler = sonuc['gemi'].nunique()
        sm4.metric("GEMİ SAYISI",    aktif_gemiler)

        st.divider()

        if sonuc.empty:
            st.info("FİLTREYE UYAN KAYIT BULUNAMADI.")
        else:
            goster_kolonlar = ['sicil_no','ad_soyad','okul','gemi','bolum',
                               'telefon','baslangic','bitis','gun_grubu','DURUM','notlar']
            goster_kolonlar = [k for k in goster_kolonlar if k in sonuc.columns]
            st.dataframe(
                sonuc[goster_kolonlar].rename(columns={
                    'sicil_no':'SİCİL', 'ad_soyad':'AD SOYAD', 'okul':'OKUL',
                    'gemi':'GEMİ', 'bolum':'BÖLÜM', 'telefon':'TELEFON',
                    'baslangic':'BAŞLANGIÇ', 'bitis':'BİTİŞ',
                    'gun_grubu':'GÜN GRUBU', 'notlar':'NOTLAR'
                }),
                use_container_width=True, hide_index=True
            )

            col_g1, col_g2 = st.columns(2)
            with col_g1:
                gemi_dag = sonuc['gemi'].value_counts().reset_index()
                gemi_dag.columns = ['GEMİ','SAYI']
                st.plotly_chart(
                    px.bar(gemi_dag, x='GEMİ', y='SAYI',
                           title="🚢 SONUÇLARDA GEMİ DAĞILIMI",
                           color='SAYI', color_continuous_scale='Blues'),
                    use_container_width=True
                )
            with col_g2:
                durum_dag = sonuc['DURUM'].value_counts().reset_index()
                durum_dag.columns = ['DURUM','SAYI']
                st.plotly_chart(
                    px.pie(durum_dag, values='SAYI', names='DURUM',
                           title="📊 AKTİF / TAMAMLANDI",
                           color_discrete_map={"✅ AKTİF":"#2ecc71","⏹️ TAMAMLANDI":"#bdc3c7"},
                           hole=0.4),
                    use_container_width=True
                )

            out3 = io.BytesIO()
            with pd.ExcelWriter(out3, engine='xlsxwriter') as writer:
                sonuc[goster_kolonlar].to_excel(writer, index=False, sheet_name='FİLTRELİ_LİSTE')
            st.download_button("📥 FİLTRELİ LİSTEYİ EXCEL OLARAK İNDİR",
                               data=out3.getvalue(),
                               file_name="FILTRELI_LISTE.xlsx")
