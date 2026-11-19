from datetime import date
import config


def _fmt(valor: int) -> str:
    """Formata inteiro como '4.000.000' (padrão br do jogo)."""
    return f"{valor:,}".replace(",", ".")


def build_weekly_message(consolidation_data: dict, meta: int = None) -> str:
    """
    Constrói a mensagem semanal de doações para envio no WhatsApp.
    Se for segunda-feira ('fechamento'), gera o relatório oficial de encerramento da semana anterior.
    De terça a domingo ('em_andamento'), gera o relatório de acompanhamento diário.
    """
    meta = meta or config.META_SEMANAL

    semana         = consolidation_data["semana"]
    tipo_relatorio = consolidation_data.get("tipo_relatorio", "em_andamento")
    membros        = consolidation_data["membros"]
    inicio         = semana["inicio"].strftime("%d/%m")
    fim            = semana["fim"].strftime("%d/%m/%Y")

    # Separa membros por categoria
    ok      = [(n, d) for n, d in membros.items() if d["status"] == "ok"]
    abaixo  = [(n, d) for n, d in membros.items() if d["status"] == "abaixo"]
    zerados = [(n, d) for n, d in membros.items() if d["status"] == "zerado"]

    ok.sort(key=lambda x: x[0])
    abaixo.sort(key=lambda x: x[1]["total"])   # ordena do menor para o maior
    zerados.sort(key=lambda x: x[0])

    linhas = []

    # ── Cabeçalho Dinâmico ────────────────────────────────────────────────
    if tipo_relatorio == "fechamento":
        linhas.append("🏆 *FECHAMENTO SEMANAL DA GUILDA* 🏆")
        linhas.append(f"📅 Ciclo Encerrado: *{inicio} a {fim}*")
        linhas.append(f"🎯 Meta estipulada: *{_fmt(meta)}*")
    else:
        linhas.append("🏰 *RELATÓRIO SEMANAL DE DOAÇÕES* 🏰")
        linhas.append(f"📅 Semana: {inicio} a {fim}")
        linhas.append(f"🎯 Meta por membro: *{_fmt(meta)}*")
    linhas.append("─" * 32)

    # ── Membros sem nenhuma doação ────────────────────────────────────────
    if zerados:
        if tipo_relatorio == "fechamento":
            linhas.append(f"\n❌ *NÃO DOARAM NO CICLO ({len(zerados)} membros):*")
        else:
            linhas.append(f"\n❌ *SEM DOAÇÕES ({len(zerados)} membros):*")
        for nome, _ in zerados:
            linhas.append(f"   • {nome} — faltam *{_fmt(meta)}*")

    # ── Membros abaixo da meta ────────────────────────────────────────────
    if abaixo:
        if tipo_relatorio == "fechamento":
            linhas.append(f"\n⚠️ *NÃO ATINGIRAM A META ({len(abaixo)} membros):*")
        else:
            linhas.append(f"\n⚠️ *ABAIXO DA META ({len(abaixo)} membros):*")
        for nome, dados in abaixo:
            pct = int(dados["total"] / meta * 100)
            linhas.append(
                f"   • {nome} — doou *{_fmt(dados['total'])}* "
                f"({pct}%) — faltam *{_fmt(dados['falta'])}*"
            )

    # ── Membros que atingiram a meta ──────────────────────────────────────
    if ok:
        linhas.append(f"\n✅ *META ATINGIDA ({len(ok)} membros):*")
        for nome, dados in ok:
            linhas.append(f"   • {nome} — {_fmt(dados['total'])} 🎉")

    # ── Rodapé ───────────────────────────────────────────────────────────
    total_geral = sum(d["total"] for d in membros.values())
    n_ok        = len(ok)
    n_total     = len(membros)

    linhas.append("\n" + "─" * 32)
    linhas.append(f"📊 Total arrecadado no ciclo: *{_fmt(total_geral)}*")
    linhas.append(f"🏅 Aproveitamento da guilda: *{n_ok}/{n_total} membros ({int(n_ok/n_total*100 if n_total else 0)}%)*")

    # Alertas de prazo (apenas para dias em andamento)
    if tipo_relatorio == "em_andamento":
        hoje = date.today()
        dias_restantes = (semana["fim"] - hoje).days
        if dias_restantes == 0:
            linhas.append("\n🚨 *Hoje é o último dia para atingir a meta!*")
        elif dias_restantes == 1:
            linhas.append("\n⏰ *Atenção: falta 1 dia para encerrar a semana!*")
    else:
        linhas.append("\n📌 _Ciclo finalizado. Um novo ciclo semanal já está valendo!_")

    linhas.append("\n🤖 _Robô Sigma — Guilda Red Moon II_")

    return "\n".join(linhas)


if __name__ == "__main__":
    from consolidator import consolidate_weekly
    dados = consolidate_weekly()
    msg = build_weekly_message(dados)
    print(msg)
