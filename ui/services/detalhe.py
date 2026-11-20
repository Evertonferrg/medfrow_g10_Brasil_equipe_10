"""Caso em cards (tema claro e escuro): busca na API, detalhe e documento original.

Tudo que vem da API é escapado antes de entrar no HTML.
"""

import html
import importlib
import json
import os
from urllib.parse import quote

import requests
import streamlit as st

from services.estilo import pill

API = os.getenv("API_URL", "http://localhost:8000").rstrip("/")


def _importar(modulo: str, nome: str):
    """Importa um componente da equipe, com ou sem o prefixo 'ui.'."""
    for prefixo in ("componentes", "ui.componentes"):
        try:
            return getattr(importlib.import_module(f"{prefixo}.{modulo}"), nome)
        except (ImportError, AttributeError):
            continue
    return None


exibir_classificacao = _importar("classificacao", "exibir_classificacao")
ROTULO_STATUS = _importar("fila", "ROTULO_STATUS") or {}
mostrar_original = _importar("original", "mostrar_original")

COR_PRIORIDADE = {
    "urgente": "red",
    "emergência": "red",
    "emergencia": "red",
    "alta": "orange",
    "rotina": "green",
    "baixa": "green",
}

CSS = """
<style>
    .card-title { font-size: .95rem; font-weight: 700; letter-spacing: .02em;
                  color: inherit; margin: 0; }
    .topo { display: flex; justify-content: space-between; align-items: center;
            margin-bottom: .6rem; gap: .5rem; }
    .linha { margin: .35rem 0; font-size: .95rem; color: inherit; }
    .linha b { color: inherit; }
    .grade { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
             gap: .9rem 1.2rem; }
    .grade .rot { display: block; font-size: .8rem; opacity: .7; }
    .grade .val { font-size: 1.1rem; font-weight: 600; }

    /* JSON com um leve tom próprio, para não sumir dentro do card branco */
    div[class*="st-key-card_json"] [data-testid="stCode"],
    div[class*="st-key-card_json"] pre {
        background: color-mix(in srgb, currentColor 3%, transparent) !important;
    }
</style>
"""


# ------------------------------------------------------------------
# Helpers de formatação
# ------------------------------------------------------------------
def _e(valor) -> str:
    """Texto seguro para HTML; '—' quando vazio."""
    return "—" if valor in (None, "") else html.escape(str(valor))


def _dict(valor) -> dict:
    return valor if isinstance(valor, dict) else {}


def _linha(rotulo: str, valor) -> str:
    return f'<p class="linha"><b>{rotulo}:</b> {_e(valor)}</p>'


def _cor_prioridade(nivel) -> str:
    return COR_PRIORIDADE.get(str(nivel or "").lower(), "gray")


def _confianca(valor) -> str:
    try:
        return f"{float(valor):.2f}"
    except (TypeError, ValueError):
        return _e(valor)


def _idade(valor):
    return f"{valor} anos" if isinstance(valor, int) else valor


def _tabela(cabecalhos: list[str], linhas: list[list[str]]) -> str:
    cab = "".join(f"<th>{c}</th>" for c in cabecalhos)
    corpo = "".join(
        "<tr>" + "".join(f"<td>{c}</td>" for c in linha) + "</tr>" for linha in linhas
    )
    return (
        '<div class="tabela-wrap"><table class="docs">'
        f"<thead><tr>{cab}</tr></thead><tbody>{corpo}</tbody></table></div>"
    )


def cor_status(status) -> str:
    s = str(status or "").lower()
    if "erro" in s or "rejeit" in s:
        return "red"
    if "revis" in s or "pend" in s:
        return "yellow"
    if s == "processado":
        return "green"
    if "receb" in s or "process" in s or "fila" in s:
        return "blue"
    return "gray"


def rotulo_status(status) -> str:
    bruto = str(status or "")
    if not bruto:
        return "—"
    return str(ROTULO_STATUS.get(bruto, bruto.replace("_", " ").capitalize()))


def selo_status(res: dict) -> str:
    """Pílula com o estágio do documento (H2.3.2 T5)."""
    bruto = res.get("status_documento") or res.get("status")
    return pill(_e(rotulo_status(bruto)), cor_status(bruto)) if bruto else ""


# ------------------------------------------------------------------
# Chamadas à API
# ------------------------------------------------------------------
def buscar_resultado(doc_id: str) -> tuple[str, dict | None]:
    """GET /documentos/{id}. Estados: ok, processando, nao_encontrado, invalido, erro."""
    try:
        r = requests.get(f"{API}/documentos/{quote(doc_id, safe='')}", timeout=30)
    except requests.RequestException:
        return "erro", None
    if r.status_code == 200:
        try:
            dados = r.json()
        except ValueError:
            return "erro", None
        return ("ok", dados) if isinstance(dados, dict) else ("erro", None)
    if r.status_code == 202:
        return "processando", None
    if r.status_code == 404:
        return "nao_encontrado", None
    if r.status_code == 400:
        return "invalido", None
    return "erro", None


def canal_de_origem(doc_id: str) -> str | None:
    """A origem não vem no resultado: busca na listagem (como fazia a tela Caso)."""
    try:
        lista = requests.get(f"{API}/documentos", timeout=10).json()
    except (requests.RequestException, ValueError):
        return None
    if not isinstance(lista, list):
        return None
    return next(
        (
            d.get("canal_origem")
            for d in lista
            if isinstance(d, dict) and d.get("documento_id") == doc_id
        ),
        None,
    )


@st.cache_data(ttl=60, max_entries=5, show_spinner=False)
def buscar_original(doc_id: str):
    """GET /documentos/{id}/original: (bytes, content-type) ou None."""
    try:
        r = requests.get(
            f"{API}/documentos/{quote(doc_id, safe='')}/original", timeout=15
        )
        r.raise_for_status()
    except requests.RequestException:
        return None
    return r.content, r.headers.get("content-type", "")


def mostrar_original_do_caso(doc_id: str) -> None:
    dados = buscar_original(doc_id)
    if dados is None:
        st.info("Documento original indisponível.")
        return
    conteudo, tipo = dados
    if mostrar_original:
        mostrar_original(st, conteudo, tipo)
    elif tipo.startswith("image/"):
        st.image(conteudo)
    else:
        st.download_button(
            "Baixar documento original",
            conteudo,
            file_name=doc_id,
            mime=tipo or "application/octet-stream",
            key=f"orig_{doc_id}",
        )


# ------------------------------------------------------------------
# Detalhe em cards
# ------------------------------------------------------------------
def mostrar_detalhe(res: dict) -> None:
    st.markdown(CSS, unsafe_allow_html=True)

    cl = _dict(res.get("classificacao"))
    dec = _dict(res.get("decisao_roteamento"))
    dados = _dict(res.get("dados_extraidos"))
    pac = _dict(dados.get("paciente"))
    med = _dict(dados.get("medico_solicitante"))
    medicamentos = [m for m in (dados.get("medicamentos") or []) if isinstance(m, dict)]
    exames = [
        e
        for e in (dados.get("exames") or dados.get("exames_solicitados") or [])
        if isinstance(e, dict)
    ]
    problemas = res.get("problemas") or []

    if _dict(res.get("armazenamento_oci")).get("status_backup") == "falha":
        st.warning("Não foi possível salvar o backup do documento.")

    # ---------------- DESTINO ----------------
    if dec:
        destino = dec.get("destino_principal")
        if destino == "Fila_Emergencia_Medica":
            cor = "red"
        elif dec.get("requer_auditoria_humana"):
            cor = "yellow"
        else:
            cor = "green"
        corpo = f'<div class="topo"><p class="card-title">DESTINO</p>{pill(_e(destino), cor)}</div>'
        if dec.get("justificativa_roteamento"):
            corpo += _linha("Por quê?", dec["justificativa_roteamento"])
        if dec.get("regra_aplicada"):
            corpo += _linha("Regra aplicada", dec["regra_aplicada"])
        with st.container(key="card_det_destino"):
            st.markdown(corpo, unsafe_allow_html=True)

    # ---------------- CLASSIFICAÇÃO ----------------
    if cl:
        if cl.get("tipo_documento") == "Não identificado":
            st.warning(
                "Documento fora das categorias clínicas (Não identificado): "
                "separado para revisão humana."
            )
        with st.container(key="card_det_classificacao"):
            st.markdown(
                '<p class="card-title">CLASSIFICAÇÃO</p>', unsafe_allow_html=True
            )
            if exibir_classificacao:
                # componente da equipe: score formatado e aviso de confiança abaixo do limite
                exibir_classificacao(cl)
            else:
                st.markdown(
                    '<div class="grade">'
                    f'<div><span class="rot">Tipo do documento</span><span class="val">{_e(cl.get("tipo_documento"))}</span></div>'
                    f'<div><span class="rot">Especialidade provável</span><span class="val">{_e(cl.get("especialidade"))}</span></div>'
                    f'<div><span class="rot">Prioridade</span>{pill(_e(cl.get("nivel_prioridade")), _cor_prioridade(cl.get("nivel_prioridade")))}</div>'
                    f'<div><span class="rot">Confiança</span><span class="val">{_confianca(cl.get("score_confianca_classificacao"))}</span></div>'
                    "</div>",
                    unsafe_allow_html=True,
                )
    else:
        st.warning("Sem classificação: o documento foi para revisão humana.")

    # ---------------- PACIENTE E MÉDICO ----------------
    col_pac, col_med = st.columns(2, gap="medium")
    with col_pac, st.container(key="card_det_paciente"):
        st.markdown(
            '<p class="card-title">PACIENTE</p>'
            + _linha("Nome", pac.get("nome"))
            + _linha("Idade", _idade(pac.get("idade")))
            + _linha("Data de nascimento", pac.get("data_nascimento")),
            unsafe_allow_html=True,
        )
    with col_med, st.container(key="card_det_medico"):
        st.markdown(
            '<p class="card-title">MÉDICO SOLICITANTE</p>'
            + _linha("Nome", med.get("nome"))
            + _linha("CRM", med.get("crm")),
            unsafe_allow_html=True,
        )

    # ---------------- DIAGNÓSTICO ----------------
    diag = dados.get("diagnostico_principal")
    cid = dados.get("cid_sugerido") or dados.get("cid")
    if diag or cid:
        origem = dados.get("cid_origem") or dados.get("origem_cid")
        with st.container(key="card_det_diagnostico"):
            st.markdown(
                '<p class="card-title">DIAGNÓSTICO</p>'
                + _linha("Diagnóstico principal", diag)
                + _linha("CID", f"{cid} ({origem})" if cid and origem else cid),
                unsafe_allow_html=True,
            )

    # ---------------- MEDICAMENTOS ----------------
    if medicamentos:
        linhas = [
            [
                _e(m.get("nome")),
                _e(m["dose"]) if m.get("dose") else pill("sem dose", "orange"),
                _e(m.get("via")),
                _e(m.get("frequencia")),
                _e(m.get("duracao")),
            ]
            for m in medicamentos
        ]
        with st.container(key="card_det_medicamentos"):
            st.markdown(
                '<p class="card-title" style="margin-bottom:.5rem">MEDICAMENTOS</p>'
                + _tabela(
                    ["Medicamento", "Dose", "Via", "Frequência", "Duração"], linhas
                ),
                unsafe_allow_html=True,
            )
    elif cl.get("tipo_documento") == "Receituário Médico":
        with st.container(key="card_det_medicamentos"):
            st.markdown(
                '<p class="card-title">MEDICAMENTOS</p>', unsafe_allow_html=True
            )
            st.caption("Nenhum medicamento identificado nesta receita.")

    # ---------------- EXAMES ----------------
    if exames:
        linhas = [[_e(e.get("nome")), _e(e.get("codigo_tuss"))] for e in exames]
        with st.container(key="card_det_exames"):
            st.markdown(
                '<p class="card-title" style="margin-bottom:.5rem">EXAMES E PROCEDIMENTOS</p>'
                + _tabela(["Exame", "Código TUSS"], linhas),
                unsafe_allow_html=True,
            )

    # ---------------- PONTOS DE ATENÇÃO ----------------
    if problemas:
        itens = "".join(f"<li>{_e(p)}</li>" for p in problemas)
        with st.container(key="card_det_problemas"):
            st.markdown(
                f'<div class="topo"><p class="card-title">PONTOS DE ATENÇÃO</p>'
                f"{pill(str(len(problemas)), 'orange')}</div>"
                f'<ul class="linha" style="padding-left:1.2rem">{itens}</ul>',
                unsafe_allow_html=True,
            )

    # ---------------- JSON ----------------
    with st.container(key="card_json"):
        st.markdown(
            '<p class="card-title" style="margin-bottom:.5rem">VISUALIZAÇÃO DO JSON</p>',
            unsafe_allow_html=True,
        )
        st.code(
            json.dumps(res, indent=2, ensure_ascii=False),
            language="json",
            height=340,
        )
        st.download_button(
            "Baixar resultado (JSON)",
            json.dumps(res, ensure_ascii=False, indent=2),
            file_name=f"{res.get('documento_id') or 'resultado'}.json",
            mime="application/json",
            type="primary",
            key=f"dl_{res.get('documento_id') or 'resultado'}",
        )
