import asyncio
import gspread
from playwright.async_api import async_playwright
import config

TARGET_SHEET_MEMBROS = "g_membros"


async def navigate_to_members(page):
    """
    Navega para a aba MEMBROS dentro do painel da Guilda.
    Se o painel ainda não estiver aberto, abre via Mundo -> Guilda primeiro.
    """
    print("Verificando se o painel da Guilda está aberto...")
    is_dossie_open = await page.evaluate('''() => {
        const aside = document.querySelector("aside.dossie");
        return aside && aside.offsetParent !== null;
    }''')

    if not is_dossie_open:
        print("1. Abrindo menu 'Mundo'...")
        mundo_btn = page.locator('button[title*="Mundo"]')
        if await mundo_btn.count() > 0:
            await mundo_btn.click()
            await page.wait_for_timeout(1000)

            print("2. Clicando em 'Guilda'...")
            await page.evaluate('''() => {
                const all = Array.from(document.querySelectorAll('*'));
                const g = all.find(el =>
                    el.innerText &&
                    el.innerText.trim().startsWith('Guilda') &&
                    el.tagName !== 'SPAN'
                );
                if (g) g.click();
            }''')
            await page.wait_for_timeout(2000)

    # Clica no botão MEMBROS no menu lateral esquerdo da Guilda
    print("3. Clicando em 'MEMBROS' no menu lateral...")
    clicked = await page.evaluate('''() => {
        // Tenta encontrar o botão de membros na nav lateral da guilda
        const buttons = Array.from(document.querySelectorAll(
            'aside.dossie nav button, aside.dossie button, div.guilda-nav button, nav.guilda-nav button'
        ));
        const btn = buttons.find(b =>
            b.innerText && b.innerText.toLowerCase().includes('membros')
        );
        if (btn) {
            btn.scrollIntoView();
            btn.click();
            return true;
        }
        return false;
    }''')

    if not clicked:
        # Fallback: procura qualquer elemento com texto "membros" visível
        print("   Fallback: procurando elemento 'membros' em toda a tela...")
        await page.evaluate('''() => {
            const all = Array.from(document.querySelectorAll('button, a, div[role="button"]'));
            const btn = all.find(el =>
                el.innerText && el.innerText.trim().toLowerCase() === 'membros'
            );
            if (btn) { btn.scrollIntoView(); btn.click(); }
        }''')

    await page.wait_for_timeout(2000)
    print("Aba MEMBROS aberta.")


async def scrape_all_members(page):
    """
    Extrai a lista completa de membros da guilda na aba MEMBROS.
    Faz scroll para garantir que todos os membros (mesmo os de baixo) sejam carregados.
    Retorna lista de dicts com: membro, cargo, nivel, hoje, esta_semana, visto.
    """
    print("Iniciando extração dos membros...")

    # Scroll para o container de membros para garantir carregamento de todos
    await page.evaluate('''() => {
        const lista = document.querySelector(
            'div.guilda-lista, div.guilda-corpo div.guilda-bloco, div.guilda-elenco'
        );
        if (lista) {
            lista.scrollTop = 0;
        }
    }''')
    await page.wait_for_timeout(1000)

    # Função de extração via JS — percorre todas as linhas de membros
    members = await page.evaluate(r'''() => {
        const result = [];

        // Encontra o container da lista de membros
        const lista = document.querySelector(
            'div.guilda-lista, div.guilda-bloco.guilda-elenco div.guilda-lista, div.guilda-elenco'
        );
        if (!lista) {
            // Fallback: tenta encontrar via todas as linhas com classe guilda-linha
            const linhas = Array.from(document.querySelectorAll('div.guilda-linha'));
            for (let i = 0; i < linhas.length; i++) {
                const r = linhas[i];
                // Pula cabeçalho
                const btn = r.querySelector('button.guilda-nome-perfil, b');
                if (!btn) continue;

                let name = btn.innerText.trim().split('\n')[0].trim();
                if (!name || name.toLowerCase() === 'membro') continue;

                // Coleta spans/textos da linha para cargo, nivel, etc.
                const spans = Array.from(r.querySelectorAll('span, b')).map(el => el.innerText.trim());
                const cargo_el = r.querySelector('[class*="cargo"], [class*="rank"], span.guilda-cargo');
                const cargo = cargo_el ? cargo_el.innerText.trim() : '';

                result.push({ nome: name, cargo: cargo });
            }
            return result;
        }

        const linhas = Array.from(lista.querySelectorAll('div.guilda-linha'));

        for (let i = 0; i < linhas.length; i++) {
            const r = linhas[i];

            // Encontra o nome do membro
            const nameEl = r.querySelector('button.guilda-nome-perfil') || r.querySelector('b');
            if (!nameEl) continue;

            // Limpa nome: remove "· você", newlines extras, etc.
            let nome = nameEl.innerText.trim().split('\n')[0].trim();
            if (!nome || nome.toLowerCase() === 'membro') continue;

            // Cargo (Líder, Oficial, Membro)
            const cargoEl = r.querySelector(
                'span[class*="cargo"], div[class*="cargo"], button[class*="cargo"], span.badge, span[class*="rank"]'
            );
            let cargo = cargoEl ? cargoEl.innerText.trim() : '';

            // Se não achou cargo, tenta pelo texto de outros elementos
            if (!cargo) {
                const allText = Array.from(r.querySelectorAll('span, button')).map(el => el.innerText.trim());
                const cargos = ['Líder', 'Oficial', 'Membro'];
                cargo = allText.find(t => cargos.includes(t)) || '';
            }

            // Coleta todos os textos numéricos da linha (nível, hoje, esta_semana)
            // A ordem esperada das colunas: Membro | Cargo | Nível | Hoje | Esta semana | Visto
            const allTexts = Array.from(r.querySelectorAll('div, span, td'))
                .map(el => el.innerText.trim())
                .filter(t => t && t !== nome && t !== cargo && !t.includes(nome));

            // Tenta extrair valores numéricos diretamente da linha em sequência
            const rawTexts = r.innerText.split('\n').map(s => s.trim()).filter(Boolean);

            result.push({
                nome: nome,
                cargo: cargo,
                raw: rawTexts
            });
        }
        return result;
    }''')

    if not members:
        print("⚠️ Aviso: Nenhum membro encontrado. Tentando abordagem alternativa...")
        members = await _fallback_scrape_members(page)

    # Pós-processamento: estrutura os dados corretamente
    structured = []
    for m in members:
        raw = m.get('raw', [])
        nome = m.get('nome', '').strip()
        cargo = m.get('cargo', '').strip()

        # Extrai valores numéricos da raw data
        nums = []
        for txt in raw:
            # Pula textos que são nome, cargo ou "você"
            if txt in [nome, cargo, '· você', 'você']:
                continue
            # Verifica se é número
            clean = txt.replace('.', '').replace(',', '')
            if clean.isdigit():
                nums.append(txt)
            elif txt in ['min', 'h', 'd', 's'] or any(c.isdigit() for c in txt):
                nums.append(txt)

        nivel = nums[0] if len(nums) > 0 else ''
        hoje = nums[1] if len(nums) > 1 else ''
        esta_semana = nums[2] if len(nums) > 2 else ''
        visto = nums[3] if len(nums) > 3 else ''

        structured.append({
            'nome': nome,
            'cargo': cargo,
            'nivel': nivel,
            'hoje': hoje,
            'esta_semana': esta_semana,
            'visto': visto
        })

    print(f"Total de membros extraídos: {len(structured)}")
    return structured


async def _fallback_scrape_members(page):
    """Extração alternativa usando JS mais simples."""
    return await page.evaluate(r'''() => {
        const result = [];
        const linhas = Array.from(document.querySelectorAll('div.guilda-linha'));
        for (const r of linhas) {
            const btn = r.querySelector('button.guilda-nome-perfil, b');
            if (!btn) continue;
            const nome = btn.innerText.trim().split('\n')[0].trim();
            if (!nome) continue;
            const rawTexts = r.innerText.split('\n').map(s => s.trim()).filter(Boolean);
            result.push({ nome, cargo: '', raw: rawTexts });
        }
        return result;
    }''')


def save_members_to_sheets(members):
    """
    Salva/substitui a lista de membros na aba g_membros.
    Sempre sobrescreve (a lista é a fonte de verdade mais recente).
    """
    if not members:
        print("Aviso: Nenhum membro para salvar.")
        return

    print(f"Salvando {len(members)} membros no Google Sheets (aba '{TARGET_SHEET_MEMBROS}')...")
    gc = gspread.service_account(filename=config.CREDENTIALS_FILE)
    sh = gc.open_by_key(config.SPREADSHEET_ID)

    try:
        ws = sh.worksheet(TARGET_SHEET_MEMBROS)
    except gspread.exceptions.WorksheetNotFound:
        print(f"Criando nova aba '{TARGET_SHEET_MEMBROS}'...")
        ws = sh.add_worksheet(title=TARGET_SHEET_MEMBROS, rows="200", cols="10")

    header = ["membro", "cargo", "nivel", "hoje", "esta_semana", "visto"]
    rows = [header]
    for m in members:
        rows.append([
            m.get('nome', ''),
            m.get('cargo', ''),
            m.get('nivel', ''),
            m.get('hoje', ''),
            m.get('esta_semana', ''),
            m.get('visto', '')
        ])

    ws.clear()
    ws.update(rows, "A1")
    print(f"Aba '{TARGET_SHEET_MEMBROS}' atualizada com {len(members)} membros.")


async def scrape_and_save_members(page):
    """
    Função principal: navega até MEMBROS, extrai e salva na planilha.
    Recebe a 'page' já conectada ao Chrome via CDP.
    """
    await navigate_to_members(page)
    members = await scrape_all_members(page)
    save_members_to_sheets(members)
    return members


# ── Teste isolado ────────────────────────────────────────────────────────────
async def _test():
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp(config.CDP_URL)
        except Exception as e:
            print(f"Erro ao conectar ao Chrome: {e}")
            return
        # Encontra a página do jogo
        page = None
        for ctx in browser.contexts:
            for pg in ctx.pages:
                try:
                    t = await pg.title()
                    if "sigma" in t.lower() or "sigma" in pg.url.lower():
                        page = pg
                        break
                except Exception:
                    continue
            if page:
                break
        if not page:
            print("Página do Sigma Project não encontrada.")
            return
        members = await scrape_and_save_members(page)
        for m in members:
            print(m)


if __name__ == "__main__":
    asyncio.run(_test())
