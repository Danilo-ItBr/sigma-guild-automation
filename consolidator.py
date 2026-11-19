from datetime import datetime, timedelta, date
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


def get_consolidation_week_range(reference_date=None):
    """
    Regra de Negócio do Ciclo da Guilda:
    - Se hoje for SEGUNDA-FEIRA (weekday == 0):
        Consolida a SEMANA ANTERIOR FECHADA (segunda passada a domingo passado).
        Tipo: 'fechamento'
    - Se hoje for de TERÇA a DOMINGO (weekday 1 a 6):
        Consolida a SEMANA ATUAL em tempo real (segunda desta semana até o próximo domingo).
        Tipo: 'em_andamento'
    """
    ref = reference_date or date.today()
    weekday = ref.weekday()  # Monday = 0, Sunday = 6

    if weekday == 0:  # Segunda-feira: Fechamento da semana anterior
        sunday_past = ref - timedelta(days=1)
        monday_past = sunday_past - timedelta(days=6)
        return monday_past, sunday_past, "fechamento"
    else:  # Terça a Domingo: Semana corrente em andamento
        monday_current = ref - timedelta(days=weekday)
        sunday_current = monday_current + timedelta(days=6)
        return monday_current, sunday_current, "em_andamento"


def consolidate_weekly(spreadsheet_id=None, credentials_file=None, meta=None, reference_date=None):
    """
    Lê g_doacoes e g_membros, aplica a janela correta (semana anterior se for segunda-feira,
    ou semana atual de terça a domingo), soma por jogador e retorna o dict estruturado.
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

    nomes_membros = []
    for row in membros_rows:
        if not row or not row[0]:
            continue
        nome = row[0].strip()
        if nome.lower() == "membro":
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

    # ── 3. Determina janela da semana e tipo ─────────────────────────────────
    monday, sunday, tipo_relatorio = get_consolidation_week_range(reference_date)
    print(f"Período de consolidação ({tipo_relatorio}): {monday.strftime('%d/%m/%Y')} a {sunday.strftime('%d/%m/%Y')}")

    # ── 4. Filtra e agrega doações do período ────────────────────────────────
    totais: dict[str, int] = {}

    for row in doacoes_rows:
        if not row or len(row) < 4:
            continue
        data_str, _hora, jogador, valor_str = row[0], row[1], row[2], row[3]
        jogador = jogador.strip()

        if data_str.lower() == "data" or not data_str:
            continue

        try:
            data_val = datetime.strptime(data_str.strip(), "%d/%m/%Y").date()
        except ValueError:
            continue

        if not (monday <= data_val <= sunday):
            continue

        valor = _parse_valor(valor_str)
        totais[jogador] = totais.get(jogador, 0) + valor

    # ── 5. Monta resultado ───────────────────────────────────────────────────
    resultado_membros   = {}
    resultado_nao_membros = {}

    for nome in nomes_membros:
        total = totais.get(nome, 0)
        resultado_membros[nome] = {
            "total":  total,
            "falta":  max(0, meta - total),
            "status": _classificar(total, meta)
        }

    for jogador, total in totais.items():
        if jogador not in nomes_membros:
            resultado_nao_membros[jogador] = total

    return {
        "semana":         {"inicio": monday, "fim": sunday},
        "tipo_relatorio": tipo_relatorio,
        "membros":        resultado_membros,
        "nao_membros":    resultado_nao_membros
    }


def _classificar(total: int, meta: int) -> str:
    if total >= meta:
        return "ok"
    elif total > 0:
        return "abaixo"
    else:
        return "zerado"


def _fmt(valor: int) -> str:
    return f"{valor:,}".replace(",", ".")


if __name__ == "__main__":
    resultado = consolidate_weekly()
    semana = resultado["semana"]
    print(f"\nTipo: {resultado['tipo_relatorio']} | Período: {semana['inicio'].strftime('%d/%m/%Y')} a {semana['fim'].strftime('%d/%m/%Y')}")
    print(f"\n{'Nome':<25} {'Total':>12} {'Falta':>12} {'Status'}")
    print("-" * 65)
    for nome, dados in sorted(resultado["membros"].items()):
        print(f"{nome:<25} {_fmt(dados['total']):>12} {_fmt(dados['falta']):>12} {dados['status']}")
