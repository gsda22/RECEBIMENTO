import streamlit as st
import gspread
import pandas as pd
import datetime
import pytz
import hashlib 

# --- CONFIGURAÇÕES DA PLANILHA (CONFIRME) ---
PLANILHA_ID = "1pvPr2wDSnPpO4Vi0vE4kHwVCk79YIMs1XtoZ8TYmAsg"
NOME_ABA = "Página1"
FUSO_BRASILIA = pytz.timezone('America/Sao_Paulo')

# ----------------------------------------------------
# 1. FUNÇÕES DE CONEXÃO E UTILIDADES
# ----------------------------------------------------

@st.cache_resource(ttl=3600)
def get_sheets_client():
    """Conecta ao Google Sheets, lendo as credenciais de st.secrets."""
    
    try:
        # Tenta ler as credenciais de st.secrets
        creds_dict = dict(st.secrets["gcp_service_account"])
    except KeyError:
        st.error("ERRO: As credenciais do Google Sheets não foram configuradas nos Secrets do Streamlit Cloud.")
        st.stop()
        
    if 'private_key' in creds_dict and creds_dict['private_key']:
        # Limpeza para garantir que o gspread aceite a chave
        creds_dict['private_key'] = creds_dict['private_key'].replace('\\n', '\n')
    
    try:
        gc = gspread.service_account_from_dict(creds_dict)
        return gc
    except Exception as e:
        st.error(f"Falha na Autenticação (gspread). Verifique o formato do segredo. Erro: {e}")
        st.stop()


def initialize_session_state():
    """Inicializa o estado da sessão do Streamlit."""
    # Garante que a aplicação inicie na Fase 1 se não estiver definida
    if 'items_nota' not in st.session_state:
        st.session_state.items_nota = []
    if 'fase' not in st.session_state:
        st.session_state.fase = 1
    if 'dados_nota' not in st.session_state:
        st.session_state.dados_nota = {}

def formatar_para_registro(dados_nota, item, dados_finais, data_lancamento, hora_lancamento):
    """Formata uma linha de dados para ser inserida na planilha."""
    # ORDEM: Data Lançamento, Hora Lançamento, Fornecedor, Nº da Nota, Valor Total NF, Produto, Qtd NF, Qtd Recebida (Físico), Divergência (Qtd), Encarregado, Auditor (PP)
    return [
        data_lancamento,
        hora_lancamento,
        dados_nota.get('fornecedor', ''),
        dados_nota.get('numero_nota', ''),
        dados_nota.get('valor_total', 0.0),
        item.get('produto', ''),
        item.get('qtd_nota', 0),
        item.get('qtd_fisico', 0),
        item.get('divergencia', 0),
        dados_finais.get('encarregado', ''),
        dados_finais.get('auditor', '')
    ]


# ----------------------------------------------------
# 2. FLUXO PRINCIPAL DA APLICAÇÃO (Onde o Script Começa)
# ----------------------------------------------------

def main():
    
    st.set_page_config(page_title="Lançamento de Recebimento", layout="wide")
    st.title("Sistema de Lançamento de Recebimento de Mercadorias")

    initialize_session_state()

    # Tenta a conexão com o Google Sheets
    gc = get_sheets_client()
    try:
        sh = gc.open_by_key(PLANILHA_ID)
        aba = sh.worksheet(NOME_ABA)
    except gspread.exceptions.WorksheetNotFound:
        st.error(f"ERRO: A aba '{NOME_ABA}' não foi encontrada. Verifique o nome da aba.")
        st.stop()
    except Exception as e:
        st.error(f"ERRO: Não foi possível abrir a planilha. Verifique o ID da planilha e o compartilhamento. Erro: {e}")
        st.stop()
        
    # --- FASE 1: DADOS DA NOTA ---
    if st.session_state.fase == 1:
        st.header("1. Dados Fixos da Nota")
        
        with st.form(key='form_dados_nota'):
            col1, col2 = st.columns(2)
            with col1:
                fornecedor = st.text_input("Nome do Fornecedor:", key='fornecedor_input')
                numero_nota = st.text_input("Número da Nota Fiscal:", key='nf_input')
            with col2:
                valor_total = st.number_input("Valor Total da Nota (R$):", min_value=0.0, format="%.2f", key='valor_input')
                data_nf = st.date_input("Data da NF (Emissão):", datetime.date.today())

            submitted_nota = st.form_submit_button("Continuar para Itens da Nota")

            if submitted_nota:
                if fornecedor and numero_nota:
                    st.session_state.dados_nota = {
                        'fornecedor': fornecedor,
                        'numero_nota': numero_nota,
                        'valor_total': valor_total,
                        'data_nf': data_nf.strftime("%d/%m/%Y")
                    }
                    st.session_state.fase = 2
                    st.rerun()
                else:
                    st.warning("Preencha Fornecedor e Número da Nota para continuar.")

    # --- FASE 2: LANÇAMENTO DOS ITENS (LOOP) ---
    elif st.session_state.fase == 2:
        st.header(f"2. Lançamento de Itens da NF {st.session_state.dados_nota.get('numero_nota', 'N/D')}")
        
        # Exibe os itens já lançados
        if st.session_state.items_nota:
            df_display = pd.DataFrame(st.session_state.items_nota)
            df_display['Divergência (Qtd)'] = df_display['qtd_fisico'] - df_display['qtd_nota']
            df_display.rename(columns={'produto': 'Produto', 'qtd_nota': 'Qtd NF', 'qtd_fisico': 'Qtd Recebida'}, inplace=True)
            st.subheader("Itens Lançados:")
            st.dataframe(df_display[['Produto', 'Qtd NF', 'Qtd Recebida', 'Divergência (Qtd)']], hide_index=True)

        st.subheader("Novo Item")
        with st.form(key='form_itens_nota'):
            col_p, col_nf, col_fisico = st.columns(3)
            
            with col_p:
                produto = st.text_input("Descrição do Produto:", key='produto_input')
            
            with col_nf:
                qtd_nota = st.number_input("Quantidade na NF:", min_value=0, step=1, key='qtd_nf_input')
            
            with col_fisico:
                qtd_fisico = st.number_input("Quantidade no Físico (Recebida):", min_value=0, step=1, key='qtd_fisico_input')

            divergencia = qtd_fisico - qtd_nota
            st.info(f"Divergência de Quantidade: **{divergencia}**")
            
            st.markdown("---")

            col_add, col_finalizar = st.columns(2)
            
            with col_add:
                add_item = st.form_submit_button("➕ Adicionar Este Produto")
            with col_finalizar:
                finalizar_nota = st.form_submit_button("✅ Finalizar Lançamento da Nota")

        # Lógica para adicionar item
        if add_item:
            if produto and (qtd_nota >= 0) and (qtd_fisico >= 0):
                novo_item = {
                    'produto': produto,
                    'qtd_nota': qtd_nota,
                    'qtd_fisico': qtd_fisico,
                    'divergencia': divergencia
                }
                st.session_state.items_nota.append(novo_item)
                st.success(f"Produto '{produto}' adicionado! Adicione o próximo ou finalize.")
                
                # Limpa os campos do formulário após adicionar o item
                st.session_state.produto_input = ""
                st.session_state.qtd_nf_input = 0
                st.session_state.qtd_fisico_input = 0
                st.rerun()

        # Lógica para finalizar
        if finalizar_nota:
            # Se houver dados no formulário atual, adicione-os antes de finalizar
            if produto and (qtd_nota >= 0) and (qtd_fisico >= 0):
                 novo_item = {
                    'produto': produto,
                    'qtd_nota': qtd_nota,
                    'qtd_fisico': qtd_fisico,
                    'divergencia': divergencia
                 }
                 st.session_state.items_nota.append(novo_item)

            if st.session_state.items_nota:
                st.session_state.fase = 3
                st.rerun()
            else:
                st.warning("Adicione pelo menos um produto antes de finalizar a nota.")


    # --- FASE 3: FECHAMENTO E AUDITORIA ---
    elif st.session_state.fase == 3:
        st.header("3. Fechamento e Auditoria")
        st.info(f"Pronto para registrar {len(st.session_state.items_nota)} itens da NF {st.session_state.dados_nota.get('numero_nota', 'N/D')}.")
        
        with st.form(key='form_fechamento'):
            col_e, col_a = st.columns(2)
            with col_e:
                encarregado = st.text_input("Nome do Encarregado (Acompanhou o Recebimento):", key='encarregado_input')
            with col_a:
                auditor = st.text_input("Nome do Auditor (Prevenção de Perdas):", key='auditor_input')
                
            submitted_fechamento = st.form_submit_button("🚀 Registrar Lançamento na Planilha")

            if submitted_fechamento:
                if encarregado and auditor:
                    st.session_state.dados_finais = {
                        'encarregado': encarregado,
                        'auditor': auditor
                    }
                    
                    # --- CAPTURA DE DATA E HORA DE BRASÍLIA ---
                    agora = datetime.datetime.now(FUSO_BRASILIA)
                    data_lancamento = agora.strftime("%d/%m/%Y")
                    hora_lancamento = agora.strftime("%H:%M:%S")

                    # --- PREPARAÇÃO E REGISTRO NA PLANILHA ---
                    linhas_para_inserir = []
                    
                    for item in st.session_state.items_nota:
                        linha = formatar_para_registro(
                            st.session_state.dados_nota,
                            item,
                            st.session_state.dados_finais,
                            data_lancamento,
                            hora_lancamento
                        )
                        linhas_para_inserir.append(linha)
                    
                    try:
                        aba.append_rows(linhas_para_inserir)
                        st.success(f"🎉 Sucesso! {len(linhas_para_inserir)} linhas da NF {st.session_state.dados_nota['numero_nota']} registradas na planilha.")
                        st.balloons()
                        st.session_state.fase = 4 # Próxima fase: Limpeza
                        st.rerun()
                    except Exception as e:
                        st.error(f"Falha ao registrar na Planilha. Erro: {e}")
                else:
                    st.warning("Preencha o nome do Encarregado e do Auditor para registrar.")

    # --- FASE 4: CONCLUSÃO E REINÍCIO ---
    elif st.session_state.fase == 4:
        st.header("Lançamento Concluído!")
        st.write("O registro foi salvo com sucesso na sua planilha.")
        
        if st.button("Iniciar Novo Lançamento"):
            # Limpa todos os dados de sessão
            for key in list(st.session_state.keys()):
                if key not in ['gcp_service_account']: # Deixa apenas o secret
                    del st.session_state[key]
            st.rerun()

if __name__ == '__main__':
    main()
