"""Revisão do caso (layout novo): original à esquerda, conferência e decisão à direita.

Mesmas chamadas ao backend da página original da equipe:
GET /documentos/{id}, /original, /trilha, /regras/destinos e POST /documentos/{id}/decisao.
"""

import html
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

import requests
import streamlit as st

RAIZ_UI = Path(__file__).resolve().parents[1]
if str(RAIZ_UI) not in sys.path:
    sys.path.insert(0, str(RAIZ_UI))

from componentes.revisao import LIMITE_PADRAO, campos_inconsistentes, evidencia_do_campo
from services.estilo import PAGINA_FILA, pill, preparar_pagina
from services.navegacao import abrir_caso, caso_atual, definir_caso

API = os.getenv("API_URL", "http://localhost:8000").rstrip("/")
MAX_PAGINAS = 10
ALTURA_ORIGINAL = 640
FUSO_HORAS = (
    -3
)  # horário de Brasília; use None para mostrar o horário como a API devolveu

CSS_PAGINA = """
<style>
    .rv-sec { font-size: .8rem; font-weight: 700; letter-spacing: .04em; opacity: .7;
              margin: .9rem 0 .35rem; }
    .rv-grade { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
                gap: .6rem; }
    .rv-campo { border: 1px solid rgba(128, 128, 128, .25); border-radius: 10px;
                padding: .5rem .75rem; display: flex; flex-direction: column; gap: .1rem; }
    .rv-alerta { border-left: 4px solid #F97316; background: rgba(249, 115, 22, .08); }
    .rv-rot { font-size: .75rem; opacity: .7; }
    .rv-val { font-size: .95rem; font-weight: 600; word-break: break-word; }
    .rv-ev { font-size: .75rem; opacity: .7; font-style: italic; }
    .rv-motivos { columns: 2; column-gap: 2rem; margin: .5rem 0 0; padding: 0 0 .25rem 1.1rem;
                  font-size: .9rem; }
    .rv-motivos li { break-inside: avoid; margin-bottom: .3rem; }
    .rv-just { font-size: .9rem; margin: .5rem 0 0; }
    .rv-meta { font-size: .85rem; opacity: .8; margin: 0 0 .25rem; }

    /* Trilha de decisões: cartão branco e linha do tempo */
    [data-testid="stExpander"] {
        background: color-mix(in srgb, currentColor 7%, transparent);
        background: rgb(from currentColor 255 255 255 / calc(1 - r / 255));
        border: 1px solid rgba(128, 128, 128, .25);
        border-radius: 12px;
        box-shadow: 0 1px 3px rgba(15, 23, 42, .08);
        overflow: hidden;
    }
    [data-testid="stExpander"] details,
    [data-testid="stExpander"] summary {
        background: transparent !important;
        border: none !important;
    }
    [data-testid="stExpander"] summary { font-weight: 700; padding: .9rem 1.25rem; }
    [data-testid="stExpander"] summary:hover { background: rgba(59, 130, 246, .06) !important; }

    .tl { margin: .6rem 0 0 .5rem; padding-left: 1.5rem;
          border-left: 2px solid rgba(128, 128, 128, .3); }
    .tl-item { position: relative; padding-bottom: 1.1rem; --c: #94A3B8; }
    .tl-item::before { content: ""; position: absolute; left: calc(-1.5rem - 7px); top: .3rem;
                       width: 12px; height: 12px; border-radius: 50%; background: var(--c); }
    .tl-agente { --c: #3B82F6; }
    .tl-auditora { --c: #22C55E; }
    .tl-cab { display: flex; flex-wrap: wrap; align-items: center; gap: .5rem; }
    .tl-hora { font-size: .8rem; opacity: .7; }
    .tl-n { font-size: .75rem; opacity: .6; }
    .tl-linha { font-size: .88rem; margin: .2rem 0 0; }
    .tl-mud { font-size: .88rem; margin: .3rem 0 0; padding: .35rem .6rem; border-radius: 8px;
              background: rgba(128, 128, 128, .1); }
    .tl-antes { text-decoration: line-through; opacity: .7; color: #EF4444; }
    .tl-depois { font-weight: 600; color: #16A34A; }
</style>
"""

ROTULO_ACAO = {
    "aprovar": "Aprovar documento",
    "redirecionar": "Redirecionar para outro setor",
    "rejeitar": "Rejeitar documento",
}
PASSADO_ACAO = {
    "aprovar": "aprovado",
    "redirecionar": "redirecionado",
    "rejeitar": "rejeitado",
}


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def _e(valor) -> str:
    """Texto seguro para HTML; '—' quando vazio."""
    return "—" if valor in (None, "") else html.escape(str(valor))


def _rotulo(valor) -> str:
    return str(valor or "").replace("_", " ").capitalize() or "—"


def _dict(valor) -> dict:
    return valor if isinstance(valor, dict) else {}


def limite_confianca() -> float:
    try:
        from componentes.classificacao import carregar_limite_confianca

        return float(carregar_limite_confianca())
    except (ImportError, OSError, KeyError, TypeError, ValueError):
        return LIMITE_PADRAO


def evidencia(dados: dict, *nomes):
    try:
        return evidencia_do_campo(dados, *nomes)
    except Exception:  # noqa: BLE001 - a evidência é opcional
        return None


# ------------------------------------------------------------------
# Original (mesma lógica da página da equipe)
# ------------------------------------------------------------------
def mostrar_original(documento_id: str) -> None:
    try:
        r = requests.get(
            f"{API}/documentos/{quote(documento_id, safe='')}/original", timeout=30
        )
    except requests.RequestException:
        st.error("Não consegui buscar o original agora.")
        return
    if r.status_code == 404:
        st.warning("Original não encontrado.")
        return
    if r.status_code != 200:
        st.error("Não foi possível abrir o original.")
        return
    tipo = r.headers.get("content-type", "")
    if tipo.startswith("text/"):
        st.text(r.content.decode("utf-8", errors="replace"))
    elif tipo.startswith("image/"):
        st.image(r.content)
    elif tipo.startswith("application/pdf"):
        try:
            import fitz  # PyMuPDF
        except ImportError:
            st.error("Instale o PyMuPDF (pymupdf) para ver PDFs.")
            return
        with fitz.open(stream=r.content, filetype="pdf") as pdf:
            for i, pagina in enumerate(pdf):
                if i >= MAX_PAGINAS:
                    st.caption(f"Mostrando as {MAX_PAGINAS} primeiras páginas.")
                    break
                st.image(pagina.get_pixmap(dpi=100).tobytes("png"))
    else:
        st.info("Formato sem visualização no painel.")


# ------------------------------------------------------------------
# Conferência dos dados
# ------------------------------------------------------------------
def campo_html(rotulo, valor, ident, ruins, ev, exibido=None) -> str:
    """Cor só onde a API sinalizou problema; campo vazio sem sinalização fica discreto."""
    ausente = valor in (None, "")
    sinalizado = ident in ruins
    if sinalizado and ausente:
        selo, alerta = pill("ausente", "orange"), True
    elif sinalizado:
        selo, alerta = pill("inconsistente", "red"), True
    elif ausente:
        selo, alerta = pill("não informado", "gray"), False
    else:
        selo, alerta = "", False

    classe = "rv-campo rv-alerta" if alerta else "rv-campo"
    texto_ev = ""
    if isinstance(ev, str) and ev.strip():
        texto_ev = (
            f'<span class="rv-ev">Evidência: {html.escape(ev.strip()[:140])}</span>'
        )
    mostrado = valor if exibido is None else exibido
    return (
        f'<div class="{classe}"><span class="rv-rot">{rotulo}</span>'
        f'<span class="rv-val">{_e(mostrado)} {selo}</span>{texto_ev}</div>'
    )


def extracao_vazia(dados: dict) -> bool:
    """True quando a leitura automática não trouxe nenhum dado útil."""
    pac = _dict(dados.get("paciente"))
    med = _dict(dados.get("medico_solicitante"))
    valores = [
        pac.get("nome"),
        pac.get("idade"),
        pac.get("data_nascimento"),
        med.get("nome"),
        med.get("crm"),
        dados.get("diagnostico_principal"),
        dados.get("cid_sugerido") or dados.get("cid"),
    ]
    meds = [
        m
        for m in (dados.get("medicamentos") or [])
        if isinstance(m, dict) and m.get("nome")
    ]
    return not meds and all(v in (None, "") for v in valores)


def mostrar_conferencia(res: dict) -> None:
    dados = _dict(res.get("dados_extraidos"))
    pac = _dict(dados.get("paciente"))
    med = _dict(dados.get("medico_solicitante"))
    ruins = campos_inconsistentes(res.get("problemas"))

    st.markdown(
        '<p class="card-title" style="font-weight:700;margin:0">CONFERÊNCIA DOS DADOS</p>',
        unsafe_allow_html=True,
    )

    if extracao_vazia(dados):
        st.warning(
            "A leitura automática não conseguiu extrair dados deste documento. "
            "Compare com o original ao lado antes de decidir.",
            icon=":material/find_in_page:",
        )
        return

    idade = pac.get("idade")
    idade_txt = f"{idade} anos" if isinstance(idade, int) else idade
    cid = dados.get("cid_sugerido") or dados.get("cid")

    paciente = "".join(
        [
            campo_html(
                "Nome",
                pac.get("nome"),
                "nome",
                ruins,
                evidencia(dados, "nome_paciente", "paciente.nome"),
            ),
            campo_html(
                "Idade",
                idade,
                "idade",
                ruins,
                evidencia(dados, "idade", "paciente.idade"),
                idade_txt,
            ),
            campo_html(
                "Data de nascimento",
                pac.get("data_nascimento"),
                "data_nascimento",
                ruins,
                evidencia(dados, "data_nascimento"),
            ),
        ]
    )
    medico = "".join(
        [
            campo_html(
                "Nome",
                med.get("nome"),
                "medico",
                ruins,
                evidencia(dados, "medico_solicitante.nome"),
            ),
            campo_html(
                "CRM",
                med.get("crm"),
                "crm",
                ruins,
                evidencia(dados, "crm", "medico_solicitante.crm"),
            ),
        ]
    )
    diagnostico = "".join(
        [
            campo_html(
                "Diagnóstico principal",
                dados.get("diagnostico_principal"),
                "diagnostico",
                ruins,
                evidencia(dados, "diagnostico_principal"),
            ),
            campo_html(
                "CID", cid, "cid", ruins, evidencia(dados, "cid", "cid_sugerido")
            ),
        ]
    )

    st.markdown(
        '<p class="rv-sec">PACIENTE</p>'
        f'<div class="rv-grade">{paciente}</div>'
        '<p class="rv-sec">MÉDICO SOLICITANTE</p>'
        f'<div class="rv-grade">{medico}</div>'
        '<p class="rv-sec">DIAGNÓSTICO</p>'
        f'<div class="rv-grade">{diagnostico}</div>',
        unsafe_allow_html=True,
    )

    meds = [m for m in (dados.get("medicamentos") or []) if isinstance(m, dict)]
    if meds:
        linhas = "".join(
            "<tr>"
            f"<td>{_e(m.get('nome'))}</td>"
            f"<td>{_e(m['dose']) if m.get('dose') else pill('sem dose', 'orange')}</td>"
            f"<td>{_e(m.get('via'))}</td>"
            "</tr>"
            for m in meds
        )
        st.markdown(
            '<p class="rv-sec">MEDICAMENTOS</p>'
            '<div class="tabela-wrap"><table class="docs"><thead><tr>'
            "<th>Medicamento</th><th>Dose</th><th>Via</th></tr></thead>"
            f"<tbody>{linhas}</tbody></table></div>",
            unsafe_allow_html=True,
        )


# ------------------------------------------------------------------
# Decisão da auditora
# ------------------------------------------------------------------
def carregar_destinos_auditora() -> list[str]:
    """H6.3.1 T5: lista de destinos do ServicoRegras para o redirecionamento."""
    try:
        r = requests.get(f"{API}/regras/destinos", timeout=5)
        if r.status_code == 200:
            destinos = r.json().get("destinos", [])
            return [d for d in destinos if d != "Fila_Revisao_Humana"]
    except requests.RequestException:
        pass
    try:
        from app.revisao import obter_destinos_redirecionaveis

        return obter_destinos_redirecionaveis()
    except Exception:  # noqa: BLE001
        return [
            "Farmacia_Hospitalar",
            "Auditoria_Autorizacoes",
            "Prontuario_Eletronico",
            "Fila_Emergencia_Medica",
        ]


def mostrar_painel_decisao(
    doc_id: str,
    *,
    ja_decidido: bool = False,
    dec: dict | None = None,
) -> None:
    """H4.4.1 a H4.4.4 / H6.3.1 T5: decisão da auditora."""
    st.markdown(
        '<p class="card-title" style="font-weight:700;margin:0 0 .5rem">DECISÃO DA AUDITORA</p>',
        unsafe_allow_html=True,
    )
    if ja_decidido:
        dec = _dict(dec)
        destino_final = dec.get("destino_principal")
        justificativa = str(dec.get("justificativa_roteamento") or "").strip()
        detalhes = []
        if destino_final:
            detalhes.append(f"Destino final: **{destino_final}**.")
        if justificativa:
            detalhes.append(justificativa)
        texto = "Este documento já foi decidido e não pode receber nova decisão."
        if detalhes:
            texto += " " + " ".join(detalhes)
        st.info(texto)
        return
    acao = st.radio(
        "Ação",
        options=list(ROTULO_ACAO),
        format_func=ROTULO_ACAO.get,
        horizontal=True,
        key="rv_acao",
    )

    destino_escolhido = None
    motivo_rejeicao = None
    if acao == "redirecionar":
        destino_escolhido = st.selectbox(
            "Novo destino",
            options=carregar_destinos_auditora(),
            help="Lista de destinos configurados no sistema (lidos do ServicoRegras).",
            key="rv_destino",
        )
    elif acao == "rejeitar":
        motivo_rejeicao = st.text_input(
            "Motivo da rejeição",
            placeholder="Ex.: Documento ilegível ou rasurado",
            key="rv_motivo",
        )

    nome_auditora = st.session_state.get("auditora", "Dra. Renata Silveira")
    if st.button("Confirmar decisão", type="primary", key="rv_confirmar"):
        payload = {"acao": acao, "auditora": nome_auditora}
        if acao == "redirecionar":
            payload["destino"] = destino_escolhido
        elif acao == "rejeitar":
            if not motivo_rejeicao or not motivo_rejeicao.strip():
                st.error("Motivo da rejeição é obrigatório.")
                return
            payload["motivo"] = motivo_rejeicao.strip()

        try:
            r = requests.post(
                f"{API}/documentos/{quote(doc_id, safe='')}/decisao",
                json=payload,
                timeout=10,
            )
        except requests.RequestException:
            st.error("Falha de comunicação com a API.")
            return
        if r.status_code == 200:
            st.cache_data.clear()
            st.session_state["rv_resultado"] = (
                f"Decisão registrada com sucesso! Documento {PASSADO_ACAO[acao]}."
            )
            st.rerun()
        else:
            try:
                corpo = r.json()
            except ValueError:
                corpo = None
            detalhe = corpo.get("detail") if isinstance(corpo, dict) else None
            detalhe = detalhe.strip()[:300] if isinstance(detalhe, str) else ""
            st.error(
                f"Erro ao registrar decisão (HTTP {r.status_code})."
                + (f" {detalhe}" if detalhe else "")
            )


# ------------------------------------------------------------------
# Trilha de decisões (H5.3.1 T4): linha do tempo
# ------------------------------------------------------------------
def formatar_data(valor) -> str:
    texto = str(valor or "").strip()
    if not texto:
        return "Não informado"
    try:
        dt = datetime.fromisoformat(texto)
    except ValueError:
        return texto[:19].replace("T", " ")
    if dt.tzinfo is not None and dt.timestamp() <= 0:
        return "Não informado"
    if dt.tzinfo is None and dt.year <= 1970 and dt.month == 1 and dt.day == 1:
        return "Não informado"
    if FUSO_HORAS is not None and dt.tzinfo is not None:
        dt = dt.astimezone(timezone(timedelta(hours=FUSO_HORAS)))
    return dt.strftime("%d/%m/%Y %H:%M:%S")


def buscar_trilha(documento_id: str) -> tuple[str, dict | None]:
    """GET /documentos/{id}/trilha. Estados: ok, vazio, erro, falha, invalida."""
    try:
        r = requests.get(
            f"{API}/documentos/{quote(documento_id, safe='')}/trilha", timeout=30
        )
    except requests.RequestException:
        return "erro", None
    if r.status_code == 404:
        return "vazio", None
    if r.status_code != 200:
        return "falha", None
    try:
        dados = r.json()
    except ValueError:
        return "invalida", None
    return ("ok", dados) if isinstance(dados, dict) else ("invalida", None)


def mostrar_trilha(documento_id: str) -> None:
    estado, dados = buscar_trilha(documento_id)
    eventos = []
    integra = True
    if estado == "ok":
        eventos = [e for e in (dados.get("eventos") or []) if isinstance(e, dict)]
        integra = bool(dados.get("cadeia_integra", False))

    titulo = "Trilha de decisões"
    if eventos:
        titulo += f" · {len(eventos)} evento(s) · " + (
            "cadeia íntegra" if integra else "atenção: problemas na cadeia"
        )

    with st.expander(titulo):
        if estado == "erro":
            st.error("Não foi possível consultar a trilha de decisões.")
            return
        if estado == "falha":
            st.warning("Não foi possível carregar o histórico de decisões.")
            return
        if estado == "invalida":
            st.error("A API retornou uma resposta inválida para a trilha.")
            return
        if not eventos:
            st.info("Ainda não existem eventos registrados para este documento.")
            return

        if not integra:
            st.error("Atenção: foram encontrados problemas na cadeia de eventos.")
            for problema in dados.get("problemas") or []:
                st.warning(str(problema))

        itens = []
        for indice, ev in reversed(list(enumerate(eventos))):  # mais recente primeiro
            tipo = ev.get("autor_tipo", "legado")
            if tipo == "agente":
                classe, quem = "tl-agente", "Agente"
            elif tipo == "auditora":
                classe, quem = (
                    "tl-auditora",
                    f"Auditora: {ev.get('autor_nome') or 'Nome não informado'}",
                )
            else:
                classe, quem = "tl-legado", "Histórico legado"

            html_ev = (
                f'<div class="tl-item {classe}"><div class="tl-cab">'
                f"<b>{_e(quem)}</b>{pill(_e(_rotulo(ev.get('status'))), 'gray')}"
                f'<span class="tl-hora">{_e(formatar_data(ev.get("em")))}</span>'
                f'<span class="tl-n">#{indice + 1}</span></div>'
            )
            if ev.get("regra_aplicada"):
                html_ev += f'<p class="tl-linha">Regra aplicada: <b>{_e(ev["regra_aplicada"])}</b></p>'
            if ev.get("detalhe"):
                html_ev += f'<p class="tl-linha">{_e(ev["detalhe"])}</p>'
            if ev.get("campo"):
                antes = (
                    "(vazio)"
                    if ev.get("valor_anterior") is None
                    else ev["valor_anterior"]
                )
                depois = "(vazio)" if ev.get("valor_novo") is None else ev["valor_novo"]
                html_ev += (
                    f'<div class="tl-mud">Campo <b>{_e(ev["campo"])}</b>: '
                    f'<span class="tl-antes">{_e(antes)}</span> → '
                    f'<span class="tl-depois">{_e(depois)}</span></div>'
                )
            itens.append(html_ev + "</div>")

        st.markdown(f'<div class="tl">{"".join(itens)}</div>', unsafe_allow_html=True)


# ------------------------------------------------------------------
# PÁGINA
# ------------------------------------------------------------------
st.set_page_config(
    page_title="MediFlow — Revisão do caso", page_icon="🩺", layout="wide"
)
preparar_pagina(estilo_especifico=False)  # esta página cuida do próprio layout
st.markdown(CSS_PAGINA, unsafe_allow_html=True)

documento_id = str(st.query_params.get("id") or caso_atual() or "").strip()
if not documento_id:
    st.title("Revisão do caso")
    st.info("Abra um caso pela fila de revisão.")
    st.stop()

definir_caso(documento_id)
if st.query_params.get("id") != documento_id:
    st.query_params["id"] = documento_id

# Navegação no topo: voltar (contorno azul) à esquerda, ver o caso (azul sólido) à direita
c_voltar, _, c_dashboard = st.columns([3, 4.5, 2.5], vertical_alignment="center")
with c_voltar, st.container(key="btn_voltar_fila"):
    st.page_link(
        st.Page(f"{RAIZ_UI}/{PAGINA_FILA}"),
        label="Voltar para a Fila de Revisão",
        icon=":material/arrow_back:",
        width="stretch",
    )
with c_dashboard:
    if st.button(
        "Ver caso no Dashboard",
        key="rv_ver_dashboard",
        type="primary",
        icon=":material/open_in_new:",
        width="stretch",
    ):
        abrir_caso(documento_id)

st.title("Revisão do caso")

mensagem = st.session_state.pop("rv_resultado", None)
if mensagem:
    st.success(mensagem)

try:
    resp = requests.get(f"{API}/documentos/{quote(documento_id, safe='')}", timeout=30)
except requests.RequestException:
    st.error("Não consegui falar com a API.")
    st.stop()
if resp.status_code == 202:
    st.info("Este documento ainda está sendo processado. Volte em alguns segundos.")
    st.stop()
if resp.status_code != 200:
    st.warning("Resultado indisponível para este documento.")
    st.stop()
try:
    res = resp.json()
except ValueError:
    st.error("A API retornou uma resposta inválida.")
    st.stop()
if not isinstance(res, dict):
    st.error("A API retornou uma resposta inválida.")
    st.stop()

cl = _dict(res.get("classificacao"))
dec = _dict(res.get("decisao_roteamento"))
score = cl.get("score_confianca_classificacao")
score_ok = isinstance(score, (int, float)) and not isinstance(score, bool)
limite = limite_confianca()
status_bruto = res.get("status_documento") or res.get("status")
status_norm = str(status_bruto or "").strip().lower()
ja_decidido = status_norm in ("processado", "rejeitado") or (
    "requer_auditoria_humana" in dec and not dec.get("requer_auditoria_humana")
)
cor_selo_status = (
    "green"
    if status_norm == "processado"
    else "red"
    if "rejeit" in status_norm or "erro" in status_norm
    else "yellow"
)

st.markdown(
    f"<p class='rv-meta'>Documento <code>{html.escape(documento_id)}</code> · "
    f"{pill(_e(_rotulo(status_bruto)), cor_selo_status)}</p>",
    unsafe_allow_html=True,
)

# ------------------------------------------------------------------
# POR QUE ESTÁ EM REVISÃO / RESUMO DA DECISÃO
# ------------------------------------------------------------------
problemas = [p for p in (res.get("problemas") or []) if p]
justificativa = str(dec.get("justificativa_roteamento") or "").strip()

partes_meta = []
if cl.get("tipo_documento"):
    partes_meta.append(f"Tipo: <b>{_e(cl.get('tipo_documento'))}</b>")
if score_ok:
    partes_meta.append(
        pill(
            f"Confiança {score:.2f} (limite {limite:.2f})",
            "orange" if (score < limite and not ja_decidido) else "gray",
        )
    )
if ja_decidido and dec.get("destino_principal"):
    partes_meta.append(f"Destino: <b>{_e(dec.get('destino_principal'))}</b>")

titulo_card_motivos = "RESUMO DA DECISÃO" if ja_decidido else "POR QUE ESTÁ EM REVISÃO"

with st.container(key="card_rv_motivos"):
    st.markdown(
        f'<p class="card-title" style="font-weight:700;margin:0 0 .3rem">{titulo_card_motivos}</p>',
        unsafe_allow_html=True,
    )
    if partes_meta:
        st.markdown(
            f"<p class='rv-meta'>{' · '.join(partes_meta)}</p>", unsafe_allow_html=True
        )
    if ja_decidido:
        if justificativa:
            st.markdown(
                f'<p class="rv-just">{_e(justificativa[:400])}</p>',
                unsafe_allow_html=True,
            )
        else:
            st.caption("Decisão humana já registrada para este documento.")
    elif problemas:
        itens = "".join(f"<li>{_e(p)}</li>" for p in problemas)
        st.markdown(f'<ul class="rv-motivos">{itens}</ul>', unsafe_allow_html=True)
    elif justificativa:
        st.markdown(
            f'<p class="rv-just">{_e(justificativa[:400])}</p>',
            unsafe_allow_html=True,
        )
    else:
        st.caption("Nenhum motivo registrado pela API para este documento.")

st.write("")

# ------------------------------------------------------------------
# ORIGINAL (esquerda) x CONFERÊNCIA E DECISÃO (direita)
# ------------------------------------------------------------------
esquerda, direita = st.columns([5, 6], gap="large")

with esquerda, st.container(key="card_rv_original"):
    st.markdown(
        '<p class="card-title" style="font-weight:700;margin:0 0 .5rem">DOCUMENTO ORIGINAL</p>',
        unsafe_allow_html=True,
    )
    with st.container(height=ALTURA_ORIGINAL, border=True):
        mostrar_original(documento_id)

with direita:
    with st.container(key="card_rv_dados"):
        mostrar_conferencia(res)
    st.write("")
    with st.container(key="card_rv_decisao"):
        mostrar_painel_decisao(documento_id, ja_decidido=ja_decidido, dec=dec)

st.write("")
mostrar_trilha(documento_id)
