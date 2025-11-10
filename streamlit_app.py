# brt_analytics_pro.py
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import folium
from streamlit_folium import st_folium
import numpy as np
from datetime import datetime
import itertools

st.set_page_config(page_title="BRT", layout="wide", initial_sidebar_state="expanded")
st.title("BRT Analytics")
st.markdown("**Outubro 2025** | Estações com Coordenadas Reais + Upload de Arquivos")

# --- UPLOAD DE ARQUIVOS (NOVA SEÇÃO PARA FLEXIBILIDADE) ---
st.sidebar.header("Upload de Arquivos (para outras datas)")
uploaded_carga = st.sidebar.file_uploader("Upload CSV: Carga por Estação (ex: 05_carga_...csv)", type="csv")
uploaded_critico = st.sidebar.file_uploader("Upload CSV: Trecho Crítico (ex: 06_trecho_...csv)", type="csv")
uploaded_stations = st.sidebar.file_uploader("Upload CSV: Estações (brt_stations.csv - opcional, usa padrão se vazio)", type="csv")

# --- CARREGAR DADOS (VIA UPLOAD OU DEFAULT) ---
@st.cache_data
def load_data(uploaded_carga, uploaded_critico, uploaded_stations):
    if uploaded_carga:
        df_carga = pd.read_csv(uploaded_carga)
    else:
        df_carga = pd.read_csv("05_carga_por_estacao_10_2025_UTIL.csv")
    
    if uploaded_critico:
        df_critico = pd.read_csv(uploaded_critico)
    else:
        df_critico = pd.read_csv("06_trecho_critico_10_2025_UTIL.csv")
    
    if uploaded_stations:
        df_stations = pd.read_csv(uploaded_stations)
    else:
        df_stations = pd.read_csv("brt_stations.csv")

    df_carga['data'] = pd.to_datetime(df_carga['data'])
    df_critico['data'] = pd.to_datetime(df_critico['data'])

    faixas = sorted(df_carga['faixa_15'].unique())
    df_carga['faixa_15'] = pd.Categorical(df_carga['faixa_15'], categories=faixas, ordered=True)
    df_critico['faixa_15'] = pd.Categorical(df_critico['faixa_15'], categories=faixas, ordered=True)

    return df_carga, df_critico, df_stations

df_carga, df_critico, df_stations = load_data(uploaded_carga, uploaded_critico, uploaded_stations)

# --- PREPARAR ESTAÇÕES ---
df_stations_unique = df_stations.drop_duplicates(subset='stop_name').set_index('stop_name')

# --- FILTROS ---
st.sidebar.header("Filtros")
grupos = ['Todos'] + sorted(df_carga['grupo_linha'].unique().tolist())
grupo = st.sidebar.selectbox("Grupo Linha", grupos)
datas = ['Todas'] + sorted(df_carga['data'].dt.strftime('%d/%m/%Y').unique().tolist())
data_sel = st.sidebar.selectbox("Data", datas)
direcoes = ['Todas', 'ida', 'volta']
direcao = st.sidebar.selectbox("Direção", direcoes)
capacidade = st.sidebar.number_input("Capacidade (pax)", 50, 200, 90, 10)

# --- APLICAR FILTROS ---
df_f = df_carga.copy()
if grupo != 'Todos': df_f = df_f[df_f['grupo_linha'] == grupo]
if data_sel != 'Todas': df_f = df_f[df_f['data'].dt.date == datetime.strptime(data_sel, '%d/%m/%Y').date()]
if direcao != 'Todas': df_f = df_f[df_f['grupo_linha'].str.contains(direcao)]

df_crit_f = df_critico.copy()
if grupo != 'Todos': df_crit_f = df_crit_f[df_crit_f['grupo_linha'] == grupo]
if data_sel != 'Todas': df_crit_f = df_crit_f[df_crit_f['data'].dt.date == datetime.strptime(data_sel, '%d/%m/%Y').date()]
if direcao != 'Todas': df_crit_f = df_crit_f[df_crit_f['grupo_linha'].str.contains(direcao)]

# --- MÉTRICAS ---
st.markdown("## Resumo Operacional")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Subidas", f"{df_f['boardings'].sum():,.0f}")
c2.metric("Descidas", f"{df_f['alightings'].sum():,.0f}")
c3.metric("Partidas", f"{df_f['qtd_partidas'].sum():,.0f}")
if not df_crit_f.empty:
    pico = df_crit_f['carga_maxima'].max()
    est = df_crit_f.loc[df_crit_f['carga_maxima'].idxmax(), 'estacao_pico']
    hora = df_crit_f.loc[df_crit_f['carga_maxima'].idxmax(), 'faixa_15']
    lot = pico / capacidade * 100
    c4.metric("Pico", f"{pico:,.0f}", f"{est} | {hora} ({lot:.1f}%)")
else:
    c4.metric("Pico", "N/A")

# --- ABAS ---
tab0, tab1, tab2, tab3 = st.tabs(["Dados Crus", "3D Superfície", "Animação Temporal", "Mapa com Carga"])

with tab0:
    st.markdown("### Visualizar Dados Originais (Interativo)")
    csv_selecionado = st.selectbox("Selecione o CSV", ["Carga por Estação", "Trecho Crítico", "Estações"])
    
    if csv_selecionado == "Carga por Estação":
        df_show = df_carga
    elif csv_selecionado == "Trecho Crítico":
        df_show = df_critico
    else:
        df_show = df_stations
    
    st.markdown(f"**Visualizando: {csv_selecionado}** (Busque, ordene, exporte)")
    st.dataframe(df_show, use_container_width=True, height=400)

with tab1:
    st.markdown("### Superfície 3D: Carga a Bordo (por Estação)")
    if df_f.empty:
        st.info("Sem dados.")
    else:
        df_3d = df_f.groupby(['faixa_15', 'stop_name']).agg({'carga_abordo': 'mean', 'ordem': 'first'}).reset_index()
        df_3d = df_3d.sort_values(['faixa_15', 'ordem'])
        pivot_z = df_3d.pivot(index='faixa_15', columns='stop_name', values='carga_abordo').fillna(0)
        ordem_correta = df_f.groupby('stop_name')['ordem'].first().sort_values()
        pivot_z = pivot_z.reindex(columns=ordem_correta.index)
        fig = go.Figure(data=[go.Surface(z=pivot_z.values, x=pivot_z.columns.tolist(), y=pivot_z.index.astype(str).tolist(), colorscale='Plasma')])
        fig.update_layout(scene=dict(xaxis_title="Estação", yaxis_title="Horário", zaxis_title="Pax"), height=600, scene_xaxis_tickangle=45)
        st.plotly_chart(fig, use_container_width=True)

with tab2:
    st.markdown("### Animação: Carga ao Longo da Linha (Play/Pause)")
    if df_f.empty:
        st.warning("Nenhum dado para os filtros selecionados.")
    else:
        df_f['ordem'] = df_f['ordem'].astype(int)
        df_f['faixa_15'] = df_f['faixa_15'].astype(str)
        ordem_to_stop = df_f.groupby('ordem')['stop_name'].first().to_dict()
        faixas = sorted(df_f['faixa_15'].unique())
        ordens = sorted(df_f['ordem'].unique())
        grid = [{'faixa_15': f, 'ordem': o, 'stop_name': ordem_to_stop.get(o, f"Ordem {o}")} for f, o in itertools.product(faixas, ordens)]
        grid_df = pd.DataFrame(grid)
        carga_media = df_f.groupby(['faixa_15', 'ordem'], as_index=False)['carga_abordo'].mean().round(1)
        carga_media['faixa_15'] = carga_media['faixa_15'].astype(str)
        carga_media['ordem'] = carga_media['ordem'].astype(int)
        anim_df = grid_df.merge(carga_media, on=['faixa_15', 'ordem'], how='left').fillna(0)
        anim_df = anim_df.sort_values(['faixa_15', 'ordem']).reset_index(drop=True)
        if anim_df['carga_abordo'].max() == 0:
            st.error("Nenhum dado de carga encontrado. Verifique os filtros.")
        else:
            fig = px.line(anim_df, x='ordem', y='carga_abordo', color='stop_name', animation_frame='faixa_15', animation_group='stop_name', range_y=[0, anim_df['carga_abordo'].max() * 1.2])
            fig.update_layout(height=600, updatemenus=[dict(type="buttons", buttons=[dict(label="Play", method="animate", args=[None, {"frame": {"duration": 700}}]), dict(label="Pause", method="animate", args=[[None], {"frame": {"duration": 0}}])])])
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': True})

with tab3:
    st.markdown("### Mapa: Carga Média por Estação (Coordenadas Reais)")
    if df_f.empty:
        st.info("Sem dados.")
    else:
        map_df = df_f.groupby('stop_name').agg({'carga_abordo': 'mean', 'boardings': 'sum', 'alightings': 'sum', 'ordem': 'first'}).reset_index()
        map_df = map_df.merge(df_stations_unique[['lat', 'lon', 'linha']], left_on='stop_name', right_index=True, how='left').dropna(subset=['lat', 'lon'])
        center_lat, center_lon = map_df['lat'].mean(), map_df['lon'].mean()
        m = folium.Map(location=[center_lat, center_lon], zoom_start=13, tiles="CartoDB positron")
        for _, row in map_df.iterrows():
            carga = row['carga_abordo']
            lotacao = carga / capacidade * 100
            cor = "red" if lotacao > 100 else "orange" if lotacao > 80 else "green"
            folium.CircleMarker(location=[row['lat'], row['lon']], radius=max(8, carga / 15), color=cor, fill=True, fill_opacity=0.8, popup=f"<b>{row['stop_name']}</b><br>Linhas: {row['linha']}<br>Carga: {carga:.0f}<br>Lotação: {lotacao:.1f}%").add_to(m)
        st_folium(m, width=700, height=500)

st.markdown("## Heatmap 2D: Carga Média por Estação e Horário")
pivot_heat = df_f.pivot_table('carga_abordo', 'stop_name', 'faixa_15', 'mean').fillna(0)
fig_heat = px.imshow(pivot_heat, color_continuous_scale="RdYlBu_r", aspect="auto", height=600)
st.plotly_chart(fig_heat, use_container_width=True)

st.markdown("## Trechos Críticos")
if not df_crit_f.empty:
    fig_crit = px.bar(df_crit_f, x='faixa_15', y='carga_maxima', color='estacao_pico', hover_data=['qtd_partidas'])
    fig_crit.add_hline(y=capacidade, line_dash="dash", line_color="red")
    st.plotly_chart(fig_crit, use_container_width=True)
else:
    st.info("Nenhum trecho crítico.")

st.markdown("---")
st.caption("BRT Salvador | Dados: Upload ou default CSVs")