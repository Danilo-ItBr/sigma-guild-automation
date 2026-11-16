from datetime import datetime, timedelta
import gspread
import config

SHEET_DOACOES  = "g_doacoes"
SHEET_MEMBROS  = "g_membros"


def _parse_valor(valor_str: str) -> int:
    """
    Converte '1.000.000' → 1000000, '300.000' → 300000, etc.
    Remove pontos e converte para inteiro.
    """
    if not valor_str:
        return 0
    return int(str(valor_str).replace(".", "").replace(",", "").strip())


def get_current_week_range():
    """
    Retorna (segunda-feira desta semana, domingo desta semana) como objetos date.
    A semana vai de segunda (00:00) a domingo (23:59) no horário de Brasília.
    """
    today = datetime.now().date()
    # weekday(): Monday = 0, Sunday = 6
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


def consolidate_weekly(spreadsheet_id=None, credentials_file=None, meta=None):
    """
    Lê g_doacoes e g_membros, filtra doações da semana atual (seg–dom),
    soma por jogador e retorna um dict estruturado.

    Retorno:
    {
        "semana": {"inicio": date, "fim": date},
        "membros": {
            "NomeDoJogador": {
                "total":  int,   # total doado na semana
                "falta":  int,   # quanto falta para a meta (0 se já atingiu)
                "status": str    # "ok", "abaixo", "zerado"
            },
            ...
        },
        "nao_membros": {
            "OutroJogador": int  # doadores que não estão na lista de membros
        }
    }
    """
    spreadsheet_id   = spreadsheet_id   or config.SPREADSHEET_ID
    credentials_file = credentials_file or config.CREDENTIALS_FILE
    meta             = meta             or config.META_SEMANAL

    print("Conectando ao Google Sheets para consolidação...")
    gc = gspread.service_account(filename=credentials_file)
    sh = gc.open_by_key(spreadsheet_id)

    # ── 1. Lê membros ────────────────────────────────────────────────────────
    try:
        ws_membros = sh.worksheet(SHEET_MEMBROS)
        membros_rows = ws_membros.get_all_values()
    except gspread.exceptions.WorksheetNotFound:
        print(f"⚠️ Aba '{SHEET_MEMBROS}' não encontrada. Rode members_scraper primeiro.")
        membros_rows = []

    # Extrai nomes (pula cabeçalho se existir)
    nomes_membros = []
    for row in membros_rows:
        if not row or not row[0]:
            continue
        nome = row[0].strip()
        if nome.lower() == "membro":   # linha de cabeçalho
            continue
        nomes_membros.append(nome)

    print(f"Membros encontrados na planilha: {len(nomes_membros)}")

    # ── 2. Lê doações ────────────────────────────────────────────────────────
    try:
        ws_doacoes = sh.worksheet(SHEET_DOACOES)
        doacoes_rows = ws_doacoes.get_all_values()
    except gspread.exceptions.WorksheetNotFound:
        print(f"⚠️ Aba '{SHEET_DOACOES}' não encontrada.")
        doacoes_rows = []

    # ── 3. Determina janela semanal ──────────────────────────────────────────
    monday, sunday = get_current_week_range()
    print(f"Semana atual: {monday.strftime('%d/%m/%Y')} a {sunday.strftime('%d/%m/%Y')}")

    # ── 4. Filtra e agrega doações da semana ─────────────────────────────────
    totais: dict[str, int] = {}

    for row in doacoes_rows:
        if not row or len(row) < 4:
            continue
        data_str, _hora, jogador, valor_str = row[0], row[1], row[2], row[3]
        jogador = jogador.strip()

        # Pula cabeçalho
        if data_str.lower() == "data" or not data_str:
            continue

        # Converte data
        try:
            data = datetime.strptime(data_str.strip(), "%d/%m/%Y").date()
        except ValueError:
            continue

        # Filtra pela semana atual
        if not (monday <= data <= sunday):
            continue

        valor = _parse_valor(valor_str)
        totais[jogador] = totais.get(jogador, 0) + valor

    # ── 5. Monta resultado ───────────────────────────────────────────────────
    resultado_membros   = {}
    resultado_nao_membros = {}

    # Inicializa todos os membros com total zero
    for nome in nomes_membros:
        resultado_membros[nome] = {
            "total":  totais.get(nome, 0),
            "falta":  max(0, meta - totais.get(nome, 0)),
            "status": _classificar(totais.get(nome, 0), meta)
        }

    # Doadores que não estão na lista de membros
    for jogador, total in totais.items():
        if jogador not in nomes_membros:
            resultado_nao_membros[jogador] = total

    return {
        "semana":      {"inicio": monday, "fim": sunday},
        "membros":     resultado_membros,
        "nao_membros": resultado_nao_membros
    }


def _classificar(total: int, meta: int) -> str:
    """Classifica o membro em 'ok', 'abaixo' ou 'zerado'."""
    if total >= meta:
        return "ok"
    elif total > 0:
        return "abaixo"
    else:
        return "zerado"


def _fmt(valor: int) -> str:
    """Formata inteiro como '4.000.000' (padrão do jogo)."""
    return f"{valor:,}".replace(",", ".")


# ── Teste isolado ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import json
    resultado = consolidate_weekly()
    semana = resultado["semana"]
    print(f"\nSemana: {semana['inicio'].strftime('%d/%m/%Y')} a {semana['fim'].strftime('%d/%m/%Y')}")
    print(f"\n{'Nome':<25} {'Total':>12} {'Falta':>12} {'Status'}")
    print("-" * 65)
    for nome, dados in sorted(resultado["membros"].items()):
        print(f"{nome:<25} {_fmt(dados['total']):>12} {_fmt(dados['falta']):>12} {dados['status']}")
    if resultado["nao_membros"]:
        print("\nDoadores fora da lista de membros:")
        for nome, total in resultado["nao_membros"].items():
            print(f"  {nome}: {_fmt(total)}")
