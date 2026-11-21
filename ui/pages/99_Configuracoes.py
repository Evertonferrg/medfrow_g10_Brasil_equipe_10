"""— Página de configuração de regras, limite de confiança e roteamento."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import requests
import streamlit as st

logger = logging.getLogger(__name__)

PASTA_UI = str(Path(__file__).resolve().parents[1])
if PASTA_UI not in sys.path:
    sys.path.insert(0, PASTA_UI)

try:
    from services.estilo import preparar_pagina
except ImportError:

    def preparar_pagina():
        pass


API_URL = os.getenv("API_URL", "http://localhost:8000").rstrip("/")

st.set_page_config(page_title="Regras de Triagem", layout="wide")
preparar_pagina()

CAMINHO_LOGO = Path(__file__).resolve().parents[1] / "assets" / "logo.png"
if CAMINHO_LOGO.exists():
    st.logo(str(CAMINHO_LOGO), size="large")

# Inicializa sessão da auditora
if "auditora" not in st.session_state:
    st.session_state["auditora"] = "Dra. Renata Silveira"
if "nome_auditora" not in st.session_state:
    st.session_state["nome_auditora"] = st.session_state["auditora"]

st.title("⚙️ Regras de Triagem")

col_auditora, _ = st.columns([1, 2])
with col_auditora:
    nome_auditora = st.text_input(
        "Nome da auditora responsável",
        value=st.session_state.get("auditora", "Dra. Renata Silveira"),
    )
    st.session_state["auditora"] = nome_auditora
    st.session_state["nome_auditora"] = nome_auditora


def carregar_regras() -> dict:
    try:
        r = requests.get(f"{API_URL}/regras", timeout=5)
        if r.status_code == 200:
            return r.json()
    except requests.RequestException:
        pass
    return {
        "limite_confianca": 0.80,
        "versao": "v1",
        "campos_criticos": [
            "paciente.nome",
            "medico_solicitante.crm",
            "medicamentos.nome",
            "medicamentos.dose",
            "cid_sugerido",
        ],
        "destinos": [
            "Farmacia_Hospitalar",
            "Auditoria_Autorizacoes",
            "Prontuario_Eletronico",
            "Fila_Emergencia_Medica",
            "Fila_Revisao_Humana",
        ],
        "regras_roteamento": [],
    }


regras_atuais = carregar_regras()
limite_atual = float(regras_atuais.get("limite_confianca", 0.80))
limite_atual = min(0.99, max(0.50, limite_atual))
versao_atual = regras_atuais.get("versao", "v1")

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Limite de confiança ativo", f"{limite_atual:.2f}")
with col2:
    st.metric("Versão das regras", versao_atual)
with col3:
    atualizado_em = regras_atuais.get("atualizado_em")
    st.metric(
        "Última alteração",
        regras_atuais.get("atualizado_por") or "Padrão inicial",
        delta=atualizado_em[:19].replace("T", " ") if atualizado_em else None,
    )

st.markdown("---")
st.subheader("1. Ajuste do Limite de Confiança")
st.markdown(
    """
    **Como funciona o limite:**
    Documentos cujo **score global** (menor valor entre classificação e média dos campos)
    ou qualquer **campo crítico** ficar abaixo deste limite são automaticamente
    encaminhados para a **Fila de Revisão Humana**.
    """
)

# Slider exigido por H6.1.1 T3: 0,50 a 0,99 com passo 0,01
novo_limite = st.slider(
    "Score mínimo para roteamento automático",
    min_value=0.50,
    max_value=0.99,
    value=limite_atual,
    step=0.01,
    help="Valores entre 0,50 e 0,99. Documentos com confiança abaixo deste valor vão para revisão humana.",
)

if st.button("Salvar novo limite de confiança", type="primary"):
    try:
        payload = {
            "limite_confianca": novo_limite,
            "auditora": st.session_state.get("auditora", "Auditora"),
        }
        resp = requests.put(f"{API_URL}/regras/limite", json=payload, timeout=5)
        if resp.status_code == 200:
            dados = resp.json()
            st.success(
                f"Limite alterado para {novo_limite:.2f} com sucesso! "
                f"Nova versão gerada: **{dados.get('versao')}**."
            )
            st.rerun()
        else:
            st.error(f"Erro ao salvar: {resp.status_code} - {resp.text}")
    except requests.RequestException as e:
        st.error(f"Não foi possível conectar à API: {e}")

# H6.3.1 T4 — Formulário de Destinos e Regras de Roteamento
st.markdown("---")
st.subheader("2. Criar Destino e Regra de Roteamento")
st.markdown(
    """
    Cadastre novos destinos (ex.: `Oncologia`) e crie regras de encaminhamento
    baseadas em **tipo de documento** ou **prefixo do código CID** (ex.: laudo com CID do capítulo C).
    """
)

destinos_atuais = regras_atuais.get("destinos", [])

with st.form("form_regra_roteamento"):
    st.write("##### Nova Regra de Roteamento")
    c1, c2 = st.columns(2)
    with c1:
        nome_destino_novo = st.text_input(
            "Nome do novo destino (opcional se destino já existir)",
            placeholder="Ex.: Oncologia",
            help="Se preenchido, adiciona este setor aos destinos disponíveis.",
        )
    with c2:
        tipo_condicao = st.selectbox(
            "Tipo de condição",
            options=["CID começa com", "Tipo de documento igual a"],
            help="Conjunto fechado de condições (expressões livres não são permitidas).",
        )

    c3, c4 = st.columns(2)
    with c3:
        valor_condicao = st.text_input(
            "Valor da condição",
            placeholder="Ex.: C (para neoplasias) ou Laudo de Exame de Imagem",
            help="Prefixo CID ou nome do tipo de documento.",
        )
    with c4:
        opcoes_destino = ["(Usar novo destino digitado ao lado)"] + destinos_atuais
        destino_selecionado = st.selectbox(
            "Destino",
            options=opcoes_destino,
            help="Selecione um destino existente ou escolha o novo destino informado.",
        )

    btn_salvar_regra = st.form_submit_button(
        "Salvar regra de roteamento", type="primary"
    )

    if btn_salvar_regra:
        destino_final = (
            nome_destino_novo.strip()
            if destino_selecionado == "(Usar novo destino digitado ao lado)"
            else destino_selecionado.strip()
        )

        erros_validacao = []
        if not destino_final:
            erros_validacao.append("Destino deve ser informado.")
        if not valor_condicao.strip():
            erros_validacao.append("Valor da condição não pode ser vazio.")

        if erros_validacao:
            for err in erros_validacao:
                st.error(err)
        else:
            tipo_cond_cod = (
                "cid_comeca_com"
                if tipo_condicao == "CID começa com"
                else "tipo_documento_igual"
            )
            auditora_atual = st.session_state.get("auditora", "Auditora")

            # 1. Se o destino não está cadastrado, cadastra via API
            criacao_ok = True
            if destino_final not in destinos_atuais:
                try:
                    resp_dest = requests.post(
                        f"{API_URL}/regras/destinos",
                        json={"nome": destino_final, "auditora": auditora_atual},
                        timeout=5,
                    )
                    if resp_dest.status_code != 200:
                        st.error(
                            f"Erro ao criar destino: {resp_dest.status_code} - {resp_dest.text}"
                        )
                        criacao_ok = False
                except requests.RequestException as e:
                    st.error(f"Falha ao conectar à API para criar destino: {e}")
                    criacao_ok = False

            # 2. Cadastra a regra via API
            if criacao_ok:
                try:
                    payload_regra = {
                        "tipo_condicao": tipo_cond_cod,
                        "valor": valor_condicao.strip(),
                        "destino": destino_final,
                        "auditora": auditora_atual,
                        "descricao": (
                            f"regra {tipo_condicao} '{valor_condicao.strip()}' → {destino_final}"
                        ),
                    }
                    resp_regra = requests.post(
                        f"{API_URL}/regras/roteamento",
                        json=payload_regra,
                        timeout=5,
                    )
                    if resp_regra.status_code == 200:
                        dados = resp_regra.json()
                        st.success(
                            f"Regra criada com sucesso para '{destino_final}'! "
                            f"Versão atualizada para **{dados.get('versao')}**."
                        )
                        st.rerun()
                    else:
                        st.error(
                            f"Erro ao salvar regra: {resp_regra.status_code} - {resp_regra.text}"
                        )
                except requests.RequestException as e:
                    st.error(f"Falha ao conectar à API para criar regra: {e}")

# Tabela com as regras cadastradas
regras_lista = regras_atuais.get("regras_roteamento", [])
if regras_lista:
    st.write("##### Regras configuradas ativas")
    linhas = []
    for r in regras_lista:
        cond = r.get("condicao") or {}
        tipo_c = cond.get("tipo", r.get("tipo_condicao", "—"))
        val_c = cond.get("valor", r.get("valor", "—"))
        tipo_legivel = (
            "CID começa com" if "cid" in str(tipo_c).lower() else "Tipo de documento ="
        )
        linhas.append(
            {
                "ID": r.get("id"),
                "Condição": f"{tipo_legivel} '{val_c}'",
                "Destino": r.get("destino"),
                "Descrição": r.get("descricao") or "—",
            }
        )
    st.dataframe(linhas, hide_index=True, width="stretch")

st.markdown("---")
with st.expander("Campos Críticos e Parâmetros Ativos"):
    st.write("**Campos críticos avaliados individualmente:**")
    st.json(regras_atuais.get("campos_criticos", []))
    st.write("**Canais de origem aceitos:**")
    st.json(regras_atuais.get("canais_origem", []))
    st.write("**Destinos disponíveis:**")
    st.json(regras_atuais.get("destinos", []))

# H6.2.1 T3 — Editar a lista de achados críticos
st.markdown("---")
st.subheader("3. Achados Críticos (Critérios de Urgência)")
st.markdown(
    """
    Edite a lista de achados clínicos que tornam o documento **Urgente**,
    encaminhando-o imediatamente para a **Fila de Emergência Médica**.
    Adicione sinônimos separados por vírgula. A lista não pode ficar vazia.
    """
)

achados_raw = regras_atuais.get("achados_criticos", [])
dados_tabela = []
for a in achados_raw:
    nome = a.get("nome", "")
    sin = a.get("sinonimos", [])
    sin_str = ", ".join(sin) if isinstance(sin, list) else str(sin)
    dados_tabela.append({"Achado": nome, "Sinônimos": sin_str})

if not dados_tabela:
    dados_tabela = [{"Achado": "", "Sinônimos": ""}]

dados_editados = st.data_editor(
    dados_tabela,
    num_rows="dynamic",
    key="editor_achados_criticos",
    width="stretch",
    column_config={
        "Achado": st.column_config.TextColumn(
            "Nome do Achado Crítico",
            help="Nome principal do achado (ex: pneumotórax hipertensivo, TEP)",
            required=True,
        ),
        "Sinônimos": st.column_config.TextColumn(
            "Sinônimos (separados por vírgula)",
            help="Termos alternativos ou abreviações (ex: pneumotorax hipertensivo, pneumotórax)",
        ),
    },
)

btn_salvar_achados = st.button("Salvar achados", type="primary")

if btn_salvar_achados:
    lista_para_salvar = []
    for linha in dados_editados:
        nome = str(linha.get("Achado", "")).strip()
        if not nome:
            continue
        sin_raw = linha.get("Sinônimos", "")
        if isinstance(sin_raw, list):
            sin_lista = [str(x).strip() for x in sin_raw if str(x).strip()]
        else:
            sin_lista = [s.strip() for s in str(sin_raw).split(",") if s.strip()]
        if nome not in sin_lista:
            sin_lista = [nome, *sin_lista]
        lista_para_salvar.append({"nome": nome, "sinonimos": sin_lista})

    if not lista_para_salvar:
        st.error("A lista de achados críticos não pode ficar vazia.")
    else:
        try:
            auditora_atual = st.session_state.get("auditora", "Auditora")
            resp_achados = requests.put(
                f"{API_URL}/regras/achados",
                json={
                    "achados_criticos": lista_para_salvar,
                    "auditora": auditora_atual,
                },
                timeout=5,
            )
            if resp_achados.status_code == 200:
                dados = resp_achados.json()
                st.success(
                    f"Achados críticos salvos com sucesso! "
                    f"Nova versão gerada: **{dados.get('versao')}**."
                )
                st.rerun()
            else:
                msg_erro = resp_achados.text
                try:
                    detalhe = resp_achados.json().get("detail")
                    if detalhe:
                        msg_erro = detalhe
                except (ValueError, KeyError):
                    pass
                st.error(f"Erro ao salvar achados críticos: {msg_erro}")
        except requests.RequestException as e:
            st.error(f"Não foi possível conectar à API: {e}")

# H6.4.1 — Histórico e restauração de versões das regras
st.markdown("---")
st.subheader("4. Histórico de Versões das Regras")

st.markdown(
    """
    Consulte as versões anteriores das regras de triagem e roteamento.
    A restauração cria uma nova versão, preservando todo o histórico.
    """
)


def carregar_historico() -> tuple[list | None, str | None]:
    try:
        resposta = requests.get(
            f"{API_URL}/regras/versoes",
            timeout=5,
        )

        if resposta.status_code != 200:
            return None, (
                f"Erro ao consultar histórico: {resposta.status_code} - {resposta.text}"
            )

        dados = resposta.json()
        versoes = dados.get("versoes")

        if not isinstance(versoes, list):
            return None, "A API retornou um formato inválido para o histórico."

        return versoes, None

    except requests.RequestException as erro:
        return None, f"Não foi possível consultar o histórico: {erro}"
    except ValueError as erro:
        return None, f"A API retornou uma resposta JSON inválida: {erro}"


@st.dialog("Confirmar restauração")
def confirmar_restauracao(versao: str):
    st.warning(f"Você está prestes a restaurar a versão **{versao}** das regras.")
    st.write(
        "Essa operação criará uma nova versão com as configurações "
        "selecionadas, preservando o histórico existente."
    )

    col_confirmar, col_cancelar = st.columns(2)

    with col_confirmar:
        if st.button(
            "Confirmar restauração",
            type="primary",
            key="confirmar_restauracao_regras",
            width="stretch",
        ):
            try:
                resposta = requests.post(
                    f"{API_URL}/regras/restaurar/{versao}",
                    json={"auditora": st.session_state.get("auditora", "Auditora")},
                    timeout=10,
                )

                if resposta.status_code == 200:
                    dados = resposta.json()
                    st.success(
                        f"Versão {versao} restaurada com sucesso! "
                        f"Nova versão criada: {dados.get('versao')}."
                    )
                    st.rerun()
                else:
                    st.error(
                        f"Erro ao restaurar versão: "
                        f"{resposta.status_code} - {resposta.text}"
                    )

            except requests.RequestException as erro:
                st.error(f"Não foi possível conectar à API: {erro}")
            except ValueError as erro:
                st.error(f"A API retornou uma resposta inválida: {erro}")

    with col_cancelar:
        if st.button(
            "Cancelar",
            key="cancelar_restauracao_regras",
            width="stretch",
        ):
            st.rerun()


historico, erro_historico = carregar_historico()

if erro_historico:
    st.error(erro_historico)

elif not historico:
    st.info("Nenhuma versão histórica foi encontrada.")

else:
    linhas_historico = []

    for item in historico:
        configuracao = item.get("configuracao", {})

        linhas_historico.append(
            {
                "Versão": item.get("versao", "—"),
                "Autor": item.get("autor", "—"),
                "Data": str(item.get("data", "—"))[:19].replace("T", " "),
                "Limite de confiança": configuracao.get("limite_confianca", "—"),
                "Alterações": ", ".join(item.get("diferencas", {}).keys())
                or "Versão inicial",
            }
        )

    st.dataframe(
        linhas_historico,
        hide_index=True,
        width="stretch",
    )

    st.markdown("#### Restaurar uma versão anterior")

    versoes_disponiveis = [
        item.get("versao")
        for item in historico
        if item.get("versao") and item.get("versao") != versao_atual
    ]

    if versoes_disponiveis:
        versao_escolhida = st.selectbox(
            "Selecione a versão que deseja restaurar",
            options=versoes_disponiveis,
            key="versao_regras_restaurar",
        )

        if st.button(
            "Restaurar versão selecionada",
            type="secondary",
            key="btn_restaurar_regras",
        ):
            confirmar_restauracao(versao_escolhida)

    else:
        st.info("Não há versões anteriores disponíveis para restauração.")
