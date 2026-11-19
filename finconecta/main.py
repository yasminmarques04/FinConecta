import traceback
import customtkinter as ctk
from tkinter import messagebox, simpledialog, filedialog
from datetime import date, datetime
from calendar import month_name
from . import database as db
from .qualidade import numero_br
import sqlite3
import logging
import webbrowser
from PIL import Image
from pathlib import Path

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")
MESES=["Janeiro","Fevereiro","Março","Abril","Maio","Junho","Julho","Agosto","Setembro","Outubro","Novembro","Dezembro"]

def moeda(v): return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
def numero(s): return numero_br(s)
def data_iso(s,opcional=False):
    s=s.strip()
    if not s and opcional: return None
    return datetime.strptime(s,"%d/%m/%Y").date().isoformat()
def data_br(s):
    return datetime.strptime(s,"%Y-%m-%d").strftime("%d/%m/%Y") if s else "—"


class FinConecta(ctk.CTk):

    def __init__(self):
        super().__init__()
        self.report_callback_exception = self.erro_interface
        db.criar_banco()

        self.title("FinConecta | Educação financeira e inclusão")
        self.geometry("1280x820")
        self.minsize(1050, 700)
        self.configure(fg_color="#071321")

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.menu = ctk.CTkFrame(
            self,
            width=310,
            corner_radius=0,
            fg_color="#091629"
        )
        self.menu.grid(row=0, column=0, sticky="nsew")
        self.grid_columnconfigure(0, minsize=310)
        self.menu.grid_propagate(False)

        self.area = ctk.CTkFrame(
            self,
            fg_color="transparent",
            corner_radius=0
        )
        self.area.grid(
            row=0,
            column=1,
            sticky="nsew",
            padx=22,
            pady=20
        )
        self.area.grid_columnconfigure(0, weight=1)

        self._menu()
        self.mostrar_painel()

    def erro_interface(self, tipo, erro, tb):
        logging.error("Falha na interface: %s", tipo.__name__)
        messagebox.showerror("FinConecta", "Não foi possível concluir a operação. Confira os dados ou tente novamente.", parent=self)

    def _menu(self):
        """Menu lateral com visual limpo, ícones maiores e navegação preservada."""
        self.menu_recolhido = getattr(self, "menu_recolhido", False)
        self.menu_item_ativo = getattr(self, "menu_item_ativo", "painel")
        self.menu_botoes = {}
        self.menu_grupos = []
        self.menu_icon_images = {}
        pasta_icones = Path(__file__).resolve().parent.parent / "assets" / "menu_icons"
        for chave in ("painel", "receitas", "despesas", "dividas", "planejamento", "metas", "relatorios", "educacao", "dicas", "backup"):
            arquivo = pasta_icones / f"{chave}.png"
            if arquivo.exists():
                original = Image.open(arquivo).convert("RGBA")
                self.menu_icon_images[chave] = ctk.CTkImage(
                    light_image=original, dark_image=original, size=(34, 34)
                )

        # Cabeçalho: logo em destaque, sem cartão de perfil para liberar espaço.
        self.menu_cabecalho = ctk.CTkFrame(self.menu, fg_color="transparent", height=94)
        self.menu_cabecalho.pack(fill="x", padx=10, pady=(14, 10))
        self.menu_cabecalho.pack_propagate(False)
        caminho_logo = Path(__file__).resolve().parent.parent / "assets" / "logo-finconecta.png"
        if caminho_logo.exists():
            imagem = Image.open(caminho_logo).convert("RGBA")
            self.logo_image = ctk.CTkImage(light_image=imagem, dark_image=imagem, size=(218, 73))
            self.logo_label = ctk.CTkLabel(self.menu_cabecalho, image=self.logo_image, text="")
        else:
            self.logo_label = ctk.CTkLabel(
                self.menu_cabecalho, text="FinConecta",
                font=ctk.CTkFont(size=23, weight="bold"), text_color="#F4F8FF"
            )
        self.logo_label.pack(side="left", padx=(2, 0), pady=7)
        self.botao_recolher = ctk.CTkButton(
            self.menu_cabecalho, text="‹", width=27, height=32,
            corner_radius=8, fg_color="transparent", hover_color="#1B3556",
            text_color="#DCEBFF", font=ctk.CTkFont(size=25, weight="bold"),
            command=self.alternar_menu
        )
        self.botao_recolher.pack(side="right", padx=(0, 2))

        # Área de navegação com rolagem.
        self.menu_conteudo = ctk.CTkScrollableFrame(
            self.menu, fg_color="transparent", corner_radius=0,
            scrollbar_button_color="#29415F", scrollbar_button_hover_color="#3A5F8B"
        )
        self.menu_conteudo.pack(fill="both", expand=True, padx=10, pady=(0, 5))

        grupos = [
            ("GERENCIAMENTO", [
                ("painel", "⌂", "Painel", self.mostrar_painel, "#69B7FF"),
                ("receitas", "↗", "Receitas", lambda: self.tela_movimento("receita"), "#35D39A"),
                ("despesas", "↘", "Despesas", lambda: self.tela_movimento("despesa"), "#F0A34A"),
                ("dividas", "▤", "Dívidas", self.tela_dividas, "#F07178"),
            ]),
            ("PLANEJAMENTO", [
                ("planejamento", "◷", "Planejamento 50/30/20", self.tela_planejamento, "#69B7FF"),
                ("metas", "◎", "Metas financeiras", self.tela_metas, "#B59AF7"),
            ]),
            ("ANÁLISES E CONHECIMENTO", [
                ("relatorios", "▥", "Relatórios", self.tela_relatorios, "#69B7FF"),
                ("educacao", "◇", "Educação financeira", self.tela_educacao, "#E5C36A"),
                ("dicas", "✧", "Dicas inteligentes", self.tela_dicas, "#E5C36A"),
            ]),
            ("UTILITÁRIOS", [
                ("backup", "☁", "Backup", self.tela_backup, "#9FB7D4"),
            ]),
        ]

        for titulo_grupo, itens in grupos:
            titulo = ctk.CTkLabel(
                self.menu_conteudo, text=titulo_grupo,
                text_color="#69B7FF", font=ctk.CTkFont(size=12, weight="bold"),
                anchor="w"
            )
            titulo.pack(fill="x", padx=10, pady=(17, 7))
            titulo._texto_original = titulo_grupo
            self.menu_grupos.append(titulo)

            for chave, icone, texto, comando, cor_icone in itens:
                ativo = chave == self.menu_item_ativo
                linha = ctk.CTkFrame(
                    self.menu_conteudo,
                    fg_color="#104FAF" if ativo else "transparent",
                    corner_radius=9, height=43
                )
                linha.pack(fill="x", pady=2)
                linha.pack_propagate(False)

                if chave in self.menu_icon_images:
                    icone_label = ctk.CTkLabel(
                        linha, image=self.menu_icon_images[chave], text="", width=46
                    )
                else:
                    # Fallback apenas se algum arquivo PNG estiver ausente.
                    icone_label = ctk.CTkLabel(
                        linha, text=icone, width=38,
                        font=ctk.CTkFont(family="Segoe UI Symbol", size=25, weight="normal"),
                        text_color="#FFFFFF" if ativo else cor_icone
                    )
                icone_label.pack(side="left", padx=(5, 1), pady=3)

                botao = ctk.CTkButton(
                    linha, text=texto, command=lambda k=chave, cmd=comando: self._navegar_menu(k, cmd),
                    anchor="w", height=41, corner_radius=8,
                    fg_color="transparent", hover_color="#173B68",
                    text_color="#FFFFFF" if ativo else "#E7EEF8",
                    font=ctk.CTkFont(size=13, weight="bold" if ativo else "normal"),
                    border_spacing=3
                )
                botao.pack(side="left", fill="both", expand=True, padx=(0, 4), pady=1)
                # Clique no ícone ou na área da linha também navega.
                icone_label.bind("<Button-1>", lambda _e, k=chave, cmd=comando: self._navegar_menu(k, cmd))
                self.menu_botoes[chave] = (botao, icone, texto, icone_label, linha, cor_icone, comando)

        self._atualizar_visual_menu()

    def _navegar_menu(self, chave, comando):
        self.menu_item_ativo = chave
        self._atualizar_visual_menu()
        comando()

    def _atualizar_visual_menu(self):
        recolhido = self.menu_recolhido
        for chave, dados in self.menu_botoes.items():
            botao, icone, texto, icone_label, linha, cor_icone, comando = dados
            ativo = chave == self.menu_item_ativo
            linha.configure(fg_color="#104FAF" if ativo and not recolhido else "transparent")
            botao.configure(
                text="" if recolhido else texto,
                anchor="center" if recolhido else "w",
                fg_color="transparent", hover_color="#173B68",
                text_color="#FFFFFF" if ativo else "#E7EEF8",
                font=ctk.CTkFont(size=13, weight="bold" if ativo else "normal")
            )
            if chave in self.menu_icon_images:
                icone_label.configure(
                    image=self.menu_icon_images[chave], text="",
                    width=46 if not recolhido else 48
                )
            else:
                icone_label.configure(
                    text=icone, text_color="#FFFFFF" if ativo else cor_icone,
                    width=38 if not recolhido else 48
                )
        for titulo in self.menu_grupos:
            titulo.configure(text="•" if recolhido else titulo._texto_original,
                             anchor="center" if recolhido else "w")

        if recolhido:
            self.logo_label.pack_forget()
            self.botao_recolher.configure(text="›")
        else:
            if not self.logo_label.winfo_manager():
                self.logo_label.pack(side="left", padx=(2, 0), pady=7)
            self.botao_recolher.configure(text="‹")

    def alternar_menu(self):
        self.menu_recolhido = not self.menu_recolhido
        largura = 76 if self.menu_recolhido else 310
        self.menu.configure(width=largura)
        self.grid_columnconfigure(0, minsize=largura)
        self._atualizar_visual_menu()

    def limpar(self):
        for w in self.area.winfo_children(): w.destroy()
    def titulo(self,t,sub=""):
        ctk.CTkLabel(self.area,text=t,font=ctk.CTkFont(size=29,weight="bold"),anchor="w").pack(fill="x")
        if sub: ctk.CTkLabel(self.area,text=sub,text_color="#9AA5B5",anchor="w").pack(fill="x",pady=(2,15))
    def card(self,pai,t,v,c):
        f=ctk.CTkFrame(pai,fg_color="#252A32",corner_radius=12); f.pack(side="left",fill="both",expand=True,padx=5)
        ctk.CTkLabel(f,text=t,text_color="#9AA5B5").pack(anchor="w",padx=14,pady=(13,3))
        ctk.CTkLabel(f,text=v,text_color=c,font=ctk.CTkFont(size=21,weight="bold")).pack(anchor="w",padx=14,pady=(0,13))
    def seletor_periodo(self,pai):
        f=ctk.CTkFrame(pai,fg_color="transparent")
        mes=ctk.CTkOptionMenu(f,values=MESES,width=140); mes.set(MESES[date.today().month-1])
        anos=[str(y) for y in range(date.today().year-5,date.today().year+3)]
        ano=ctk.CTkOptionMenu(f,values=anos,width=100); ano.set(str(date.today().year))
        mes.pack(side="left",padx=(0,8)); ano.pack(side="left")
        return f,mes,ano
    def periodo(self,m,a): return MESES.index(m.get())+1,int(a.get())

    def mostrar_painel(self):
        self.limpar()
        self.titulo("Meu painel", "Acompanhe sua situação financeira por mês.")

        seletor, mes_menu, ano_menu = self.seletor_periodo(self.area)
        seletor.pack(anchor="w", pady=(0, 10))

        conteudo = ctk.CTkScrollableFrame(
            self.area, fg_color="transparent", corner_radius=0
        )
        conteudo.pack(fill="both", expand=True)

        cards = ctk.CTkFrame(conteudo, fg_color="transparent")
        cards.pack(fill="x", pady=(0, 10))

        alerta_area = ctk.CTkFrame(conteudo, fg_color="transparent")
        alerta_area.pack(fill="x", pady=(0, 10))

        graficos = ctk.CTkFrame(conteudo, fg_color="transparent")
        graficos.pack(fill="x", pady=(0, 10))
        graficos.grid_columnconfigure((0, 1), weight=1, uniform="painel")

        vencimentos = ctk.CTkFrame(
            conteudo, fg_color="#252A32", corner_radius=12
        )
        vencimentos.pack(fill="x", pady=(0, 12))

        def limpar_frame(frame):
            for widget in frame.winfo_children():
                widget.destroy()

        def titulo_bloco(pai, texto, apoio=None):
            ctk.CTkLabel(
                pai, text=texto, font=ctk.CTkFont(size=17, weight="bold"),
                text_color="#F4F7FC"
            ).pack(anchor="w", padx=16, pady=(14, 2))
            if apoio:
                ctk.CTkLabel(
                    pai, text=apoio, text_color="#9AA5B5",
                    font=ctk.CTkFont(size=11)
                ).pack(anchor="w", padx=16, pady=(0, 8))

        def barra_horizontal(pai, rotulo, valor, maximo, cor, largura=1):
            linha = ctk.CTkFrame(pai, fg_color="transparent")
            linha.pack(fill="x", padx=16, pady=6)
            linha.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(
                linha, text=rotulo, text_color="#DCE4EF",
                font=ctk.CTkFont(size=12)
            ).grid(row=0, column=0, sticky="w")
            ctk.CTkLabel(
                linha, text=moeda(valor), text_color="#F4F7FC",
                font=ctk.CTkFont(size=12, weight="bold")
            ).grid(row=0, column=1, sticky="e")
            trilho = ctk.CTkFrame(
                linha, height=10, fg_color="#3A414C", corner_radius=8
            )
            trilho.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(5, 0))
            trilho.grid_propagate(False)
            preenchido = ctk.CTkFrame(
                trilho, height=10, fg_color=cor, corner_radius=8
            )
            proporcao = min(max(valor / maximo, 0), 1) if maximo > 0 else 0
            preenchido.place(relx=0, rely=0, relwidth=proporcao, relheight=1)

        def atualizar(*_):
            limpar_frame(cards)
            limpar_frame(alerta_area)
            limpar_frame(graficos)
            limpar_frame(vencimentos)

            mes, ano = self.periodo(mes_menu, ano_menu)
            receitas, despesas, dividas, pendentes = db.resumo_mes(ano, mes)
            saldo = receitas - despesas
            comprometimento = (despesas / receitas * 100) if receitas else 0
            saldo_atual = receitas - (despesas - pendentes)

            # Cartões: os valores são sempre calculados pelo banco de dados.
            metricas = [
                ("RECEITAS", moeda(receitas), "Total registrado no mês", "#35B982", "#20352F"),
                ("DESPESAS", moeda(despesas), "Total gasto no mês", "#E6A23C", "#3A3021"),
                ("SALDO PROJETADO", moeda(saldo), "Disponível após despesas", "#35B982" if saldo >= 0 else "#F07178", "#20352F" if saldo >= 0 else "#3A252B"),
                ("DÍVIDAS EM ABERTO", moeda(dividas), "Saldo de dívidas", "#F07178", "#3A252B"),
            ]
            for indice, (rotulo, valor, apoio, cor, fundo) in enumerate(metricas):
                card = ctk.CTkFrame(
                    cards, fg_color="#252A32", corner_radius=12,
                    border_width=1, border_color="#303946"
                )
                card.grid(row=0, column=indice, sticky="nsew", padx=4)
                cards.grid_columnconfigure(indice, weight=1, uniform="metricas")
                ctk.CTkLabel(
                    card, text=rotulo, text_color="#AAB6C6",
                    font=ctk.CTkFont(size=11, weight="bold")
                ).pack(anchor="w", padx=13, pady=(12, 3))
                ctk.CTkLabel(
                    card, text=valor, text_color=cor,
                    font=ctk.CTkFont(size=21, weight="bold")
                ).pack(anchor="w", padx=13, pady=(0, 1))
                ctk.CTkLabel(
                    card, text=apoio, text_color="#8F9BAD",
                    font=ctk.CTkFont(size=10)
                ).pack(anchor="w", padx=13, pady=(0, 11))

            # Alerta dinâmico preserva os cálculos e as regras existentes.
            if receitas <= 0 and despesas <= 0:
                titulo_alerta = "Acompanhe seu orçamento"
                mensagem = "Cadastre suas receitas e despesas para visualizar sua situação financeira."
                cor_alerta, fundo_alerta = "#60A5FA", "#202F43"
            elif saldo_atual < 0:
                titulo_alerta = "Atenção: seu saldo já está negativo"
                mensagem = f"As despesas pagas ultrapassaram suas receitas em {moeda(abs(saldo_atual))}. Revise os gastos e priorize as contas essenciais."
                cor_alerta, fundo_alerta = "#F07178", "#3A252B"
            elif saldo < 0:
                titulo_alerta = "Atenção: risco de saldo negativo"
                mensagem = f"Você tem {moeda(saldo_atual)} considerando despesas pagas e {moeda(pendentes)} pendentes. Após esses pagamentos, o saldo será {moeda(saldo)}."
                cor_alerta, fundo_alerta = "#E6A23C", "#3A3021"
            elif receitas > 0 and saldo <= receitas * 0.20:
                titulo_alerta = "Atenção: pouca margem no orçamento"
                mensagem = f"Restam {moeda(saldo)} após as despesas cadastradas. Evite novos gastos não essenciais."
                cor_alerta, fundo_alerta = "#E6A23C", "#3A3021"
            else:
                titulo_alerta = "Seu orçamento está equilibrado"
                mensagem = f"Depois das despesas cadastradas, você tem {moeda(saldo)} disponíveis. Continue acompanhando os vencimentos."
                cor_alerta, fundo_alerta = "#35B982", "#20352F"

            aviso = ctk.CTkFrame(
                alerta_area, fg_color=fundo_alerta, corner_radius=10,
                border_width=1, border_color=cor_alerta
            )
            aviso.pack(fill="x")
            ctk.CTkLabel(
                aviso, text=titulo_alerta, text_color=cor_alerta,
                font=ctk.CTkFont(size=14, weight="bold")
            ).pack(anchor="w", padx=14, pady=(9, 2))
            ctk.CTkLabel(
                aviso, text=mensagem, text_color="#E7EAF0",
                justify="left", wraplength=1400,
                font=ctk.CTkFont(size=11)
            ).pack(anchor="w", padx=14, pady=(0, 9))

            # Gráfico 1: comparação direta entre receitas e despesas.
            grafico_esquerdo = ctk.CTkFrame(
                graficos, fg_color="#252A32", corner_radius=12
            )
            grafico_esquerdo.grid(
                row=0, column=0, sticky="nsew", padx=(0, 5)
            )
            titulo_bloco(
                grafico_esquerdo, "Receitas x despesas",
                "Veja quanto entrou e quanto saiu no período selecionado."
            )
            escala = max(receitas, despesas, 1)
            barra_horizontal(
                grafico_esquerdo, "Receitas", receitas, escala, "#35B982"
            )
            barra_horizontal(
                grafico_esquerdo, "Despesas", despesas, escala, "#E6A23C"
            )
            rodape = ctk.CTkFrame(
                grafico_esquerdo, fg_color="#1D2631", corner_radius=8
            )
            rodape.pack(fill="x", padx=16, pady=(8, 14))
            ctk.CTkLabel(
                rodape,
                text=f"Renda comprometida: {comprometimento:.1f}%".replace(".", ","),
                text_color="#DCE4EF",
                font=ctk.CTkFont(size=12, weight="bold")
            ).pack(anchor="w", padx=10, pady=8)

            # Gráfico 2: dois meses, com escala compartilhada.
            anterior = mes - 1 if mes > 1 else 12
            ano_anterior = ano if mes > 1 else ano - 1
            receitas_ant, despesas_ant, _, _ = db.resumo_mes(ano_anterior, anterior)
            nome_mes_atual = MESES[mes - 1]
            nome_mes_ant = MESES[anterior - 1]
            grafico_direito = ctk.CTkFrame(
                graficos, fg_color="#252A32", corner_radius=12
            )
            grafico_direito.grid(
                row=0, column=1, sticky="nsew", padx=(5, 0)
            )
            titulo_bloco(
                grafico_direito, "Comparativo mensal",
                f"{nome_mes_ant} x {nome_mes_atual}"
            )
            legenda = ctk.CTkFrame(
                grafico_direito, fg_color="transparent"
            )
            legenda.pack(anchor="w", padx=16, pady=(0, 4))
            for texto, cor in (("Receitas", "#35B982"), ("Despesas", "#E6A23C")):
                item = ctk.CTkFrame(legenda, fg_color="transparent")
                item.pack(side="left", padx=(0, 14))
                ctk.CTkFrame(
                    item, width=9, height=9, fg_color=cor, corner_radius=3
                ).pack(side="left", padx=(0, 5))
                ctk.CTkLabel(
                    item, text=texto, text_color="#AAB6C6",
                    font=ctk.CTkFont(size=10)
                ).pack(side="left")
            escala_comparativa = max(receitas_ant, despesas_ant, receitas, despesas, 1)
            for nome, valor_r, valor_d in (
                (nome_mes_ant, receitas_ant, despesas_ant),
                (nome_mes_atual, receitas, despesas),
            ):
                grupo = ctk.CTkFrame(
                    grafico_direito, fg_color="#1D2631", corner_radius=8
                )
                grupo.pack(fill="x", padx=16, pady=5)
                ctk.CTkLabel(
                    grupo, text=nome, text_color="#F4F7FC",
                    font=ctk.CTkFont(size=11, weight="bold")
                ).pack(anchor="w", padx=10, pady=(7, 1))
                barra_horizontal(
                    grupo, "Receitas", valor_r, escala_comparativa,
                    "#35B982"
                )
                barra_horizontal(
                    grupo, "Despesas", valor_d, escala_comparativa,
                    "#E6A23C"
                )

            # Vencimentos: somente despesas pendentes do mês selecionado.
            titulo_bloco(
                vencimentos, "Próximos vencimentos",
                "Despesas pendentes cadastradas para o período selecionado."
            )
            movimentos = db.listar_movimentos("despesa", mes, ano)
            lista_pendentes = [
                item for item in movimentos
                if str(item["status"]).strip().lower() == "pendente"
            ]
            def chave_vencimento(item):
                venc = item["vencimento"]
                if not venc:
                    return (1, "9999-12-31")
                return (0, str(venc))
            lista_pendentes.sort(key=chave_vencimento)

            if not lista_pendentes:
                vazio = ctk.CTkFrame(
                    vencimentos, fg_color="#1D2631", corner_radius=8
                )
                vazio.pack(fill="x", padx=16, pady=(0, 14))
                ctk.CTkLabel(
                    vazio, text="Tudo em dia! Não há despesas pendentes neste mês.",
                    text_color="#35B982", font=ctk.CTkFont(size=12)
                ).pack(anchor="w", padx=12, pady=12)
            else:
                for item in lista_pendentes[:5]:
                    linha = ctk.CTkFrame(
                        vencimentos, fg_color="#1D2631", corner_radius=8
                    )
                    linha.pack(fill="x", padx=16, pady=3)
                    linha.grid_columnconfigure(0, weight=1)
                    descricao = str(item["descricao"])
                    vencimento = data_br(item["vencimento"]) if item["vencimento"] else "Sem vencimento"
                    ctk.CTkLabel(
                        linha, text=descricao, text_color="#F4F7FC",
                        font=ctk.CTkFont(size=12, weight="bold"),
                        anchor="w"
                    ).grid(row=0, column=0, sticky="w", padx=12, pady=(7, 0))
                    ctk.CTkLabel(
                        linha, text=f"Vencimento: {vencimento}",
                        text_color="#9AA5B5", font=ctk.CTkFont(size=10)
                    ).grid(row=1, column=0, sticky="w", padx=12, pady=(0, 7))
                    ctk.CTkLabel(
                        linha, text=moeda(float(item["valor"])),
                        text_color="#E6A23C",
                        font=ctk.CTkFont(size=12, weight="bold")
                    ).grid(row=0, column=1, rowspan=2, sticky="e", padx=12)
                if len(lista_pendentes) > 5:
                    ctk.CTkLabel(
                        vencimentos,
                        text=f"Mais {len(lista_pendentes) - 5} despesas pendentes no período.",
                        text_color="#9AA5B5", font=ctk.CTkFont(size=10)
                    ).pack(anchor="w", padx=18, pady=(5, 12))
                else:
                    ctk.CTkFrame(vencimentos, height=8, fg_color="transparent").pack()

        mes_menu.configure(command=atualizar)
        ano_menu.configure(command=atualizar)
        atualizar()

    def tela_movimento(self, tipo, edicao=None):
        self.limpar()
        nome = "Receitas" if tipo == "receita" else "Despesas"
        subtitulo = (
            "Organize suas entradas e acompanhe de onde vem seu dinheiro."
            if tipo == "receita"
            else "Registre seus gastos, acompanhe pagamentos e controle vencimentos."
        )
        self.titulo(nome, subtitulo)

        pagina = ctk.CTkScrollableFrame(self.area, fg_color="transparent", corner_radius=0)
        pagina.pack(fill="both", expand=True)

        dados = dict(edicao) if edicao else {}
        campos = {}

        form = ctk.CTkFrame(
            pagina, fg_color="#202B39", corner_radius=14,
            border_width=1, border_color="#2D3A4B"
        )
        form.pack(fill="x", pady=(0, 12))
        form.grid_columnconfigure((0, 1), weight=1, uniform="campos")

        ctk.CTkLabel(
            form, text="Nova movimentação" if not edicao else "Editar movimentação",
            font=ctk.CTkFont(size=16, weight="bold"), text_color="#F4F7FC"
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(13, 5))

        def campo(rotulo, row, col, placeholder="", valor=""):
            ctk.CTkLabel(
                form, text=rotulo, text_color="#C5D0DE",
                font=ctk.CTkFont(size=11, weight="bold")
            ).grid(row=row, column=col, sticky="w", padx=16, pady=(8, 3))
            entrada = ctk.CTkEntry(
                form, placeholder_text=placeholder, height=36,
                fg_color="#151F2D", border_color="#3A4A5E",
                text_color="#F4F7FC"
            )
            entrada.grid(row=row + 1, column=col, sticky="ew", padx=16, pady=(0, 3))
            if valor not in (None, ""):
                entrada.insert(0, str(valor))
            campos[rotulo] = entrada
            return entrada

        campo("Descrição", 1, 0, "Ex.: salário ou supermercado", dados.get("descricao", ""))
        campo("Valor (R$)", 1, 1, "Ex.: 250,00", str(dados["valor"]).replace(".", ",") if dados else "")
        campo("Data", 3, 0, "DD/MM/AAAA", data_br(dados.get("data", date.today().isoformat())))

        categorias = db.listar_categorias(tipo)
        nomes_categorias = [x["nome"] for x in categorias] or ["Outros"]
        ctk.CTkLabel(
            form, text="Categoria", text_color="#C5D0DE",
            font=ctk.CTkFont(size=11, weight="bold")
        ).grid(row=3, column=1, sticky="w", padx=16, pady=(8, 3))
        categoria_frame = ctk.CTkFrame(form, fg_color="transparent")
        categoria_frame.grid(row=4, column=1, sticky="ew", padx=16, pady=(0, 3))
        categoria_frame.grid_columnconfigure(0, weight=1)
        cat = ctk.CTkOptionMenu(
            categoria_frame, values=nomes_categorias, height=36,
            fg_color="#1765A5", button_color="#12558D"
        )
        cat.grid(row=0, column=0, sticky="ew", padx=(0, 7))
        if dados.get("categoria") in nomes_categorias:
            cat.set(dados["categoria"])
        ctk.CTkButton(
            categoria_frame, text="+ Categoria", width=108, height=36,
            command=lambda: self.nova_categoria(tipo, cat)
        ).grid(row=0, column=1)

        campo("Observação", 5, 0, "Opcional", dados.get("observacao", ""))
        ctk.CTkLabel(
            form, text="Tipo de movimentação", text_color="#C5D0DE",
            font=ctk.CTkFont(size=11, weight="bold")
        ).grid(row=5, column=1, sticky="w", padx=16, pady=(8, 3))
        recorrencia = ctk.CTkOptionMenu(
            form, values=["Fixa", "Variável"], height=36,
            fg_color="#1765A5", button_color="#12558D"
        )
        recorrencia.grid(row=6, column=1, sticky="ew", padx=16, pady=(0, 3))
        recorrencia.set(dados.get("tipo_recorrencia", "Variável"))

        situacao = None
        if tipo == "despesa":
            ctk.CTkLabel(
                form, text="Situação", text_color="#C5D0DE",
                font=ctk.CTkFont(size=11, weight="bold")
            ).grid(row=7, column=0, sticky="w", padx=16, pady=(8, 3))
            situacao = ctk.CTkOptionMenu(
                form, values=["Pago", "Pendente"], height=36,
                fg_color="#1765A5", button_color="#12558D"
            )
            situacao.grid(row=8, column=0, sticky="ew", padx=16, pady=(0, 3))
            situacao.set(dados.get("status", "Pago"))
            campo(
                "Vencimento", 7, 1, "DD/MM/AAAA (opcional)",
                data_br(dados.get("vencimento")) if dados.get("vencimento") else ""
            )
            campo("Forma de pagamento", 9, 0, "Pix, dinheiro, débito, crédito...", dados.get("forma_pagamento", ""))
            campo("Parcela atual", 9, 1, "Ex.: 1", dados.get("parcela_atual", ""))
            campo("Total de parcelas", 11, 0, "Ex.: 10", dados.get("total_parcelas", ""))

        def salvar():
            try:
                descricao = campos["Descrição"].get().strip()
                if not descricao:
                    raise ValueError("Informe a descrição.")
                valor = numero(campos["Valor (R$)"].get())
                if valor <= 0:
                    raise ValueError("O valor deve ser maior que zero.")
                data = data_iso(campos["Data"].get())
                categoria_id = next(
                    (x["id"] for x in db.listar_categorias(tipo) if x["nome"] == cat.get()),
                    None
                )
                vencimento = data_iso(campos["Vencimento"].get(), True) if tipo == "despesa" else None
                parcela = campos["Parcela atual"].get().strip() if tipo == "despesa" else ""
                total_parcelas = campos["Total de parcelas"].get().strip() if tipo == "despesa" else ""
                parcela = int(parcela) if parcela else None
                total_parcelas = int(total_parcelas) if total_parcelas else None
                if parcela and (not total_parcelas or parcela > total_parcelas or parcela < 1):
                    raise ValueError("Confira a parcela atual e o total de parcelas.")
                argumentos = (
                    descricao, valor, data, categoria_id,
                    campos["Observação"].get().strip(), recorrencia.get(),
                    situacao.get() if situacao else "Pago", vencimento,
                    campos["Forma de pagamento"].get().strip() if tipo == "despesa" else "",
                    parcela, total_parcelas
                )
                if edicao:
                    db.salvar_edicao_movimento(tipo, dados["id"], *argumentos)
                else:
                    db.inserir_movimento(tipo, *argumentos)
                messagebox.showinfo("FinConecta", "Movimentação salva com sucesso.")
                self.tela_movimento(tipo)
            except (ValueError, TypeError) as erro:
                messagebox.showerror("Confira os dados", str(erro))

        botao_texto = "Salvar alterações" if edicao else ("Adicionar receita" if tipo == "receita" else "Adicionar despesa")
        ctk.CTkButton(
            form, text=botao_texto, command=salvar, height=39,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#1765A5", hover_color="#12558D"
        ).grid(
            row=13 if tipo == "despesa" else 7,
            column=0, columnspan=2, sticky="ew",
            padx=16, pady=(13, 16)
        )

        # Barra de pesquisa e filtros.
        filtros = ctk.CTkFrame(
            pagina, fg_color="#202B39", corner_radius=12,
            border_width=1, border_color="#2D3A4B"
        )
        filtros.pack(fill="x", pady=(0, 9))
        filtros.grid_columnconfigure(0, weight=1)
        busca = ctk.CTkEntry(
            filtros, placeholder_text="Buscar por descrição...",
            height=35, fg_color="#151F2D", border_color="#3A4A5E"
        )
        busca.grid(row=0, column=0, sticky="ew", padx=(12, 6), pady=10)
        filtro_periodo, menu_mes, menu_ano = self.seletor_periodo(filtros)
        filtro_periodo.grid(row=0, column=1, padx=4, pady=10)
        todos = False

        lista = ctk.CTkFrame(pagina, fg_color="transparent")
        lista.pack(fill="both", expand=True)

        def carregar(*_):
            for widget in lista.winfo_children():
                widget.destroy()
            mes = MESES.index(menu_mes.get()) + 1
            ano = int(menu_ano.get())
            registros = db.listar_movimentos(
                tipo, None if todos else mes, None if todos else ano, busca.get()
            )
            total = sum(float(x["valor"]) for x in registros)
            cabecalho = ctk.CTkFrame(lista, fg_color="#202B39", corner_radius=12)
            cabecalho.pack(fill="x", pady=(0, 8))
            ctk.CTkLabel(
                cabecalho, text=f"{len(registros)} lançamento(s)",
                text_color="#AAB6C6", font=ctk.CTkFont(size=11, weight="bold")
            ).pack(side="left", padx=14, pady=11)
            ctk.CTkLabel(
                cabecalho, text=f"Total do período  {moeda(total)}",
                text_color="#35B982" if tipo == "receita" else "#E6A23C",
                font=ctk.CTkFont(size=14, weight="bold")
            ).pack(side="right", padx=14, pady=11)

            if not registros:
                vazio = ctk.CTkFrame(lista, fg_color="#202B39", corner_radius=12)
                vazio.pack(fill="x", pady=4)
                ctk.CTkLabel(
                    vazio, text="Nenhuma movimentação encontrada para este filtro.",
                    text_color="#AAB6C6"
                ).pack(anchor="w", padx=16, pady=20)
                return

            for registro in registros:
                cartao = ctk.CTkFrame(
                    lista, fg_color="#202B39", corner_radius=11,
                    border_width=1, border_color="#2D3A4B"
                )
                cartao.pack(fill="x", pady=4)
                cartao.grid_columnconfigure(0, weight=1)
                cor_valor = "#35B982" if tipo == "receita" else "#E6A23C"
                info_secundaria = f'{registro["categoria"]}  •  {data_br(registro["data"])}'
                if tipo == "despesa":
                    info_secundaria += f'  •  {registro["status"]}  •  {registro["tipo_recorrencia"]}'
                ctk.CTkLabel(
                    cartao, text=str(registro["descricao"]),
                    text_color="#F4F7FC", font=ctk.CTkFont(size=13, weight="bold"),
                    anchor="w"
                ).grid(row=0, column=0, sticky="w", padx=14, pady=(10, 1))
                ctk.CTkLabel(
                    cartao, text=info_secundaria, text_color="#9AA5B5",
                    font=ctk.CTkFont(size=10), anchor="w"
                ).grid(row=1, column=0, sticky="w", padx=14, pady=(0, 10))
                ctk.CTkLabel(
                    cartao, text=moeda(float(registro["valor"])),
                    text_color=cor_valor, font=ctk.CTkFont(size=14, weight="bold")
                ).grid(row=0, column=1, rowspan=2, padx=12)
                acoes = ctk.CTkFrame(cartao, fg_color="transparent")
                acoes.grid(row=0, column=2, rowspan=2, padx=10)
                ctk.CTkButton(
                    acoes, text="Editar", width=70, height=30,
                    command=lambda x={k: registro[k] for k in registro.keys()}: self.tela_movimento(tipo, x)
                ).pack(side="left", padx=3)
                ctk.CTkButton(
                    acoes, text="Excluir", width=70, height=30,
                    fg_color="#963B45", hover_color="#7B2E37",
                    command=lambda x=registro["id"]: self.excluir(tipo, x)
                ).pack(side="left", padx=3)

        def filtrar_periodo(*_):
            nonlocal todos
            todos = False
            carregar()

        def mostrar_todos():
            nonlocal todos
            todos = True
            carregar()

        ctk.CTkButton(
            filtros, text="Todos", width=68, height=35,
            command=mostrar_todos
        ).grid(row=0, column=2, padx=4, pady=10)
        ctk.CTkButton(
            filtros, text="Buscar", width=76, height=35,
            command=carregar
        ).grid(row=0, column=3, padx=(4, 12), pady=10)
        busca.bind("<Return>", carregar)
        menu_mes.configure(command=filtrar_periodo)
        menu_ano.configure(command=filtrar_periodo)
        carregar()

    def nova_categoria(self,tipo,menu=None):
        nome=simpledialog.askstring("Nova categoria","Digite o nome da categoria:",parent=self)
        if nome:
            try:
                db.adicionar_categoria(tipo,nome)
                if menu is not None:
                    nomes=[x["nome"] for x in db.listar_categorias(tipo)]
                    menu.configure(values=nomes)
                    menu.set(nome.strip())
                messagebox.showinfo("Categoria","Categoria adicionada e selecionada com sucesso.")
            except ValueError as e:
                messagebox.showerror("Categoria",str(e))
    def excluir(self,tipo,mid):
        if messagebox.askyesno("Confirmar exclusão","Deseja realmente excluir este lançamento?"):
            db.backup_banco()
            db.excluir_movimento(tipo,mid); self.tela_movimento(tipo)

    def tela_dividas(self):
        self.limpar()
        self.titulo("Dívidas", "Tenha uma visão clara dos valores, pagamentos e saldos em aberto.")

        pagina = ctk.CTkScrollableFrame(self.area, fg_color="transparent", corner_radius=0)
        pagina.pack(fill="both", expand=True)

        dividas = db.listar_dividas()
        total_original = sum(float(item["valor_total"]) for item in dividas)
        total_pago = sum(float(item["pago"]) for item in dividas)
        total_aberto = sum(float(item["saldo"]) for item in dividas)

        resumo = ctk.CTkFrame(pagina, fg_color="transparent")
        resumo.pack(fill="x", pady=(0, 12))
        indicadores = [
            ("TOTAL DAS DÍVIDAS", moeda(total_original), "#AFC8E8"),
            ("TOTAL PAGO", moeda(total_pago), "#35B982"),
            ("SALDO EM ABERTO", moeda(total_aberto), "#F07178"),
        ]
        for indice, (rotulo, valor, cor) in enumerate(indicadores):
            resumo.grid_columnconfigure(indice, weight=1, uniform="dividas")
            card = ctk.CTkFrame(
                resumo, fg_color="#202B39", corner_radius=12,
                border_width=1, border_color="#2D3A4B"
            )
            card.grid(row=0, column=indice, sticky="nsew", padx=4)
            ctk.CTkLabel(
                card, text=rotulo, text_color="#9AA5B5",
                font=ctk.CTkFont(size=10, weight="bold")
            ).pack(anchor="w", padx=13, pady=(12, 3))
            ctk.CTkLabel(
                card, text=valor, text_color=cor,
                font=ctk.CTkFont(size=19, weight="bold")
            ).pack(anchor="w", padx=13, pady=(0, 12))

        form = ctk.CTkFrame(
            pagina, fg_color="#202B39", corner_radius=14,
            border_width=1, border_color="#2D3A4B"
        )
        form.pack(fill="x", pady=(0, 12))
        form.grid_columnconfigure((0, 1), weight=1, uniform="campos_divida")
        ctk.CTkLabel(
            form, text="Cadastrar nova dívida",
            font=ctk.CTkFont(size=16, weight="bold"), text_color="#F4F7FC"
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(13, 5))

        campos = {}
        definicoes = [
            ("Credor", "Banco ou instituição"),
            ("Descrição", "Empréstimo, cartão..."),
            ("Valor total", "Ex.: 5.000,00"),
            ("Vencimento", "DD/MM/AAAA (opcional)"),
            ("Quantidade de parcelas", "Ex.: 12"),
            ("Valor da parcela", "Ex.: 450,00"),
            ("Juros (%)", "Ex.: 2,5"),
        ]
        for indice, (rotulo, placeholder) in enumerate(definicoes):
            linha = 1 + (indice // 2) * 2
            coluna = indice % 2
            ctk.CTkLabel(
                form, text=rotulo, text_color="#C5D0DE",
                font=ctk.CTkFont(size=11, weight="bold")
            ).grid(row=linha, column=coluna, sticky="w", padx=16, pady=(8, 3))
            entrada = ctk.CTkEntry(
                form, placeholder_text=placeholder, height=36,
                fg_color="#151F2D", border_color="#3A4A5E"
            )
            entrada.grid(row=linha + 1, column=coluna, sticky="ew", padx=16, pady=(0, 3))
            campos[rotulo] = entrada

        def cadastrar():
            try:
                credor = campos["Credor"].get().strip()
                descricao = campos["Descrição"].get().strip()
                if not credor or not descricao:
                    raise ValueError("Informe o credor e a descrição da dívida.")
                valor = numero(campos["Valor total"].get())
                vencimento = data_iso(campos["Vencimento"].get(), True)
                quantidade = int(campos["Quantidade de parcelas"].get()) if campos["Quantidade de parcelas"].get().strip() else None
                valor_parcela = numero(campos["Valor da parcela"].get()) if campos["Valor da parcela"].get().strip() else None
                juros = numero(campos["Juros (%)"].get()) if campos["Juros (%)"].get().strip() else 0
                if valor <= 0 or (quantidade is not None and quantidade <= 0) or juros < 0:
                    raise ValueError("Confira os valores informados.")
                db.inserir_divida(
                    credor, descricao, valor, vencimento, "",
                    quantidade, valor_parcela, juros
                )
                self.tela_dividas()
            except (ValueError, TypeError) as erro:
                messagebox.showerror("Dívidas", str(erro))

        ctk.CTkButton(
            form, text="Cadastrar dívida", command=cadastrar, height=39,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#1765A5", hover_color="#12558D"
        ).grid(row=9, column=0, columnspan=2, sticky="ew", padx=16, pady=(13, 16))

        ctk.CTkLabel(
            pagina, text="Dívidas cadastradas",
            font=ctk.CTkFont(size=17, weight="bold"), text_color="#F4F7FC"
        ).pack(anchor="w", pady=(5, 7))

        lista = ctk.CTkFrame(pagina, fg_color="transparent")
        lista.pack(fill="both", expand=True)

        if not dividas:
            vazio = ctk.CTkFrame(lista, fg_color="#202B39", corner_radius=12)
            vazio.pack(fill="x", pady=4)
            ctk.CTkLabel(
                vazio, text="Nenhuma dívida cadastrada. Seus registros aparecerão aqui.",
                text_color="#AAB6C6"
            ).pack(anchor="w", padx=16, pady=20)

        for divida in dividas:
            percentual = min(
                float(divida["pago"]) / float(divida["valor_total"]), 1
            ) if divida["valor_total"] else 0
            quitada = float(divida["saldo"]) <= 0.009
            cartao = ctk.CTkFrame(
                lista, fg_color="#202B39", corner_radius=12,
                border_width=1, border_color="#2D3A4B"
            )
            cartao.pack(fill="x", pady=5)
            cartao.grid_columnconfigure(0, weight=1)

            ctk.CTkLabel(
                cartao, text=str(divida["credor"]),
                text_color="#F4F7FC", font=ctk.CTkFont(size=14, weight="bold"),
                anchor="w"
            ).grid(row=0, column=0, sticky="w", padx=15, pady=(12, 1))
            ctk.CTkLabel(
                cartao, text=str(divida["descricao"]),
                text_color="#9AA5B5", font=ctk.CTkFont(size=11),
                anchor="w"
            ).grid(row=1, column=0, sticky="w", padx=15, pady=(0, 8))
            status_texto = "QUITADA" if quitada else "EM ABERTO"
            status_cor = "#35B982" if quitada else "#F0A35B"
            ctk.CTkLabel(
                cartao, text=status_texto, text_color=status_cor,
                font=ctk.CTkFont(size=10, weight="bold")
            ).grid(row=0, column=1, padx=15, pady=(12, 0), sticky="e")

            valores = ctk.CTkFrame(cartao, fg_color="#182434", corner_radius=8)
            valores.grid(row=2, column=0, columnspan=2, sticky="ew", padx=13, pady=(0, 8))
            for coluna, (rotulo, valor, cor) in enumerate([
                ("VALOR ORIGINAL", moeda(float(divida["valor_total"])), "#DCE4EF"),
                ("JÁ PAGO", moeda(float(divida["pago"])), "#35B982"),
                ("RESTANTE", moeda(float(divida["saldo"])), "#F07178" if not quitada else "#35B982"),
            ]):
                valores.grid_columnconfigure(coluna, weight=1, uniform="valores")
                bloco = ctk.CTkFrame(valores, fg_color="transparent")
                bloco.grid(row=0, column=coluna, sticky="ew", padx=10, pady=8)
                ctk.CTkLabel(
                    bloco, text=rotulo, text_color="#8F9BAD",
                    font=ctk.CTkFont(size=9, weight="bold")
                ).pack(anchor="w")
                ctk.CTkLabel(
                    bloco, text=valor, text_color=cor,
                    font=ctk.CTkFont(size=12, weight="bold")
                ).pack(anchor="w")

            progresso = ctk.CTkProgressBar(
                cartao, height=9,
                progress_color="#35B982" if quitada else "#278B69"
            )
            progresso.grid(row=3, column=0, columnspan=2, sticky="ew", padx=15, pady=(2, 3))
            progresso.set(percentual)
            parcelas = divida["quantidade_parcelas"] or "Não informadas"
            juros_texto = f'{float(divida["juros"]):.2f}%'.replace(".", ",")
            vencimento_texto = data_br(divida["vencimento"]) if divida["vencimento"] else "Não informado"
            ctk.CTkLabel(
                cartao,
                text=f"{percentual * 100:.1f}% quitado  •  Parcelas: {parcelas}  •  Juros: {juros_texto}  •  Vencimento: {vencimento_texto}",
                text_color="#AAB6C6", font=ctk.CTkFont(size=10)
            ).grid(row=4, column=0, columnspan=2, sticky="w", padx=15, pady=(3, 8))

            if not quitada:
                acoes = ctk.CTkFrame(cartao, fg_color="transparent")
                acoes.grid(row=5, column=0, columnspan=2, sticky="ew", padx=11, pady=(0, 11))
                valor_pagamento = ctk.CTkEntry(
                    acoes, placeholder_text="Valor do pagamento",
                    width=190, height=34, fg_color="#151F2D",
                    border_color="#3A4A5E"
                )
                valor_pagamento.pack(side="left", padx=3)

                def registrar_pagamento(did=divida["id"], entrada=valor_pagamento):
                    try:
                        valor = numero(entrada.get())
                        if valor <= 0:
                            raise ValueError("Informe um valor maior que zero.")
                        db.registrar_pagamento(
                            did, valor, date.today().isoformat()
                        )
                        self.tela_dividas()
                    except ValueError as erro:
                        messagebox.showerror("Pagamento", str(erro))

                ctk.CTkButton(
                    acoes, text="Registrar pagamento",
                    command=registrar_pagamento, width=155, height=34
                ).pack(side="left", padx=3)
            else:
                acoes = ctk.CTkFrame(cartao, fg_color="transparent")
                acoes.grid(row=5, column=0, columnspan=2, sticky="ew", padx=11, pady=(0, 11))

            ctk.CTkButton(
                acoes, text="Ver histórico",
                command=lambda did=divida["id"]: self.ver_historico_divida(did),
                width=110, height=34, fg_color="#34465C",
                hover_color="#405773"
            ).pack(side="left", padx=3)

    def ver_historico_divida(self,did):
        rows=db.historico_pagamentos(did)
        txt="\n".join(f'{data_br(x["data"])} • {moeda(x["valor"])}' for x in rows) or "Nenhum pagamento registrado."
        messagebox.showinfo("Histórico de pagamentos",txt)

    def tela_planejamento(self):
        self.limpar()
        self.titulo(
            "Planejamento 50/30/20",
            "Distribua sua renda entre necessidades, desejos e metas com mais clareza."
        )

        pagina = ctk.CTkScrollableFrame(self.area, fg_color="transparent", corner_radius=0)
        pagina.pack(fill="both", expand=True)

        intro = ctk.CTkFrame(
            pagina, fg_color="#202B39", corner_radius=14,
            border_width=1, border_color="#2D3A4B"
        )
        intro.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(
            intro, text="Comece informando sua renda mensal",
            text_color="#F4F7FC", font=ctk.CTkFont(size=16, weight="bold")
        ).pack(anchor="w", padx=16, pady=(14, 3))
        ctk.CTkLabel(
            intro, text="A regra 50/30/20 é uma referência: 50% para necessidades, 30% para desejos e 20% para metas e prioridades.",
            text_color="#AAB6C6", wraplength=1000, justify="left"
        ).pack(anchor="w", padx=16, pady=(0, 10))

        ctk.CTkLabel(
            intro, text="Renda mensal (R$)", text_color="#C5D0DE",
            font=ctk.CTkFont(size=11, weight="bold")
        ).pack(anchor="w", padx=16, pady=(3, 3))
        renda = ctk.CTkEntry(
            intro, placeholder_text="Ex.: 3.200,00", height=38,
            fg_color="#151F2D", border_color="#3A4A5E"
        )
        renda.pack(fill="x", padx=16, pady=(0, 8))
        filtros, menu_mes, menu_ano = self.seletor_periodo(intro)
        filtros.pack(anchor="w", padx=16, pady=(0, 12))

        saida = ctk.CTkFrame(pagina, fg_color="transparent")
        saida.pack(fill="both", expand=True)

        def calcular():
            for widget in saida.winfo_children():
                widget.destroy()
            try:
                valor_renda = numero(renda.get())
                mes, ano = self.periodo(menu_mes, menu_ano)
                if valor_renda <= 0:
                    raise ValueError("Informe uma renda mensal maior que zero.")

                _, total_despesas, _, pendentes = db.resumo_mes(ano, mes)
                categorias = db.totais_categoria(ano, mes)
                mapa = {item["categoria"]: float(item["total"]) for item in categorias}

                grupos = [
                    ("Necessidades", 0.50, "#3B9BD8",
                     ["Moradia", "Alimentação", "Transporte", "Saúde", "Educação",
                      "Água e energia", "Internet e telefone"]),
                    ("Desejos", 0.30, "#B28AE8",
                     ["Lazer", "Compras pessoais", "Assinaturas"]),
                    ("Metas e prioridades", 0.20, "#35B982",
                     ["Investimentos", "Reserva de emergência"]),
                ]

                resumo = ctk.CTkFrame(saida, fg_color="transparent")
                resumo.pack(fill="x", pady=(0, 10))
                indicadores = [
                    ("RENDA INFORMADA", moeda(valor_renda), "#DCE4EF"),
                    ("DESPESAS DO MÊS", moeda(total_despesas), "#E6A23C"),
                    ("DESPESAS PENDENTES", moeda(pendentes), "#F07178"),
                ]
                for indice, (rotulo, texto, cor) in enumerate(indicadores):
                    resumo.grid_columnconfigure(indice, weight=1, uniform="planejamento")
                    card = ctk.CTkFrame(
                        resumo, fg_color="#202B39", corner_radius=12,
                        border_width=1, border_color="#2D3A4B"
                    )
                    card.grid(row=0, column=indice, sticky="nsew", padx=4)
                    ctk.CTkLabel(
                        card, text=rotulo, text_color="#9AA5B5",
                        font=ctk.CTkFont(size=10, weight="bold")
                    ).pack(anchor="w", padx=13, pady=(11, 3))
                    ctk.CTkLabel(
                        card, text=texto, text_color=cor,
                        font=ctk.CTkFont(size=17, weight="bold")
                    ).pack(anchor="w", padx=13, pady=(0, 11))

                ctk.CTkLabel(
                    saida, text="Distribuição sugerida da sua renda",
                    text_color="#F4F7FC", font=ctk.CTkFont(size=17, weight="bold")
                ).pack(anchor="w", pady=(5, 7))

                for nome, proporcao, cor, nomes in grupos:
                    limite = valor_renda * proporcao
                    gasto = sum(mapa.get(categoria, 0) for categoria in nomes)
                    diferenca = limite - gasto
                    percentual = min(gasto / limite, 1) if limite else 0

                    cartao = ctk.CTkFrame(
                        saida, fg_color="#202B39", corner_radius=12,
                        border_width=1, border_color="#2D3A4B"
                    )
                    cartao.pack(fill="x", pady=5)
                    cartao.grid_columnconfigure(0, weight=1)

                    topo = ctk.CTkFrame(cartao, fg_color="transparent")
                    topo.pack(fill="x", padx=14, pady=(11, 2))
                    ctk.CTkLabel(
                        topo, text=nome, text_color="#F4F7FC",
                        font=ctk.CTkFont(size=13, weight="bold")
                    ).pack(side="left")
                    ctk.CTkLabel(
                        topo, text=f"{proporcao*100:.0f}%",
                        text_color=cor, font=ctk.CTkFont(size=14, weight="bold")
                    ).pack(side="right")

                    ctk.CTkLabel(
                        cartao,
                        text=f"Planejado: {moeda(limite)}     •     Identificado nas categorias: {moeda(gasto)}",
                        text_color="#AAB6C6", font=ctk.CTkFont(size=11)
                    ).pack(anchor="w", padx=14, pady=(1, 7))

                    barra = ctk.CTkProgressBar(cartao, height=10, progress_color=cor)
                    barra.pack(fill="x", padx=14, pady=(0, 7))
                    barra.set(percentual)

                    if diferenca >= 0:
                        situacao = f"Dentro do limite • Restam {moeda(diferenca)}"
                        cor_situacao = "#35B982"
                    else:
                        situacao = f"Acima do planejado em {moeda(abs(diferenca))}"
                        cor_situacao = "#F07178"
                    ctk.CTkLabel(
                        cartao, text=situacao, text_color=cor_situacao,
                        font=ctk.CTkFont(size=11, weight="bold")
                    ).pack(anchor="w", padx=14, pady=(0, 11))

                ctk.CTkLabel(
                    saida,
                    text=(
                        "Atenção: a comparação por grupo considera apenas as categorias mapeadas em cada grupo. "
                        "Categorias personalizadas ou não listadas não entram nesses três indicadores. "
                        "O total geral de despesas continua sendo exibido acima."
                    ),
                    text_color="#8F9BAD", wraplength=1050, justify="left",
                    font=ctk.CTkFont(size=10)
                ).pack(anchor="w", pady=(9, 12))

            except (ValueError, TypeError) as erro:
                messagebox.showerror("Planejamento", str(erro))

        ctk.CTkButton(
            intro, text="Calcular meu planejamento", command=calcular,
            height=39, font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#1765A5", hover_color="#12558D"
        ).pack(fill="x", padx=16, pady=(0, 15))

    def tela_metas(self):
        self.limpar()
        self.titulo(
            "Metas financeiras",
            "Transforme seus planos em objetivos e acompanhe cada conquista."
        )

        pagina = ctk.CTkScrollableFrame(self.area, fg_color="transparent", corner_radius=0)
        pagina.pack(fill="both", expand=True)

        metas = db.listar_metas()
        total_objetivos = sum(float(meta["valor_objetivo"]) for meta in metas)
        total_guardado = sum(float(meta["valor_atual"]) for meta in metas)
        total_falta = max(total_objetivos - total_guardado, 0)

        resumo = ctk.CTkFrame(pagina, fg_color="transparent")
        resumo.pack(fill="x", pady=(0, 12))
        indicadores = [
            ("METAS CADASTRADAS", str(len(metas)), "#DCE4EF"),
            ("TOTAL JÁ GUARDADO", moeda(total_guardado), "#35B982"),
            ("FALTA ALCANÇAR", moeda(total_falta), "#69B8F0"),
        ]
        for indice, (rotulo, valor, cor) in enumerate(indicadores):
            resumo.grid_columnconfigure(indice, weight=1, uniform="metas")
            card = ctk.CTkFrame(
                resumo, fg_color="#202B39", corner_radius=12,
                border_width=1, border_color="#2D3A4B"
            )
            card.grid(row=0, column=indice, sticky="nsew", padx=4)
            ctk.CTkLabel(
                card, text=rotulo, text_color="#9AA5B5",
                font=ctk.CTkFont(size=10, weight="bold")
            ).pack(anchor="w", padx=13, pady=(11, 3))
            ctk.CTkLabel(
                card, text=valor, text_color=cor,
                font=ctk.CTkFont(size=18, weight="bold")
            ).pack(anchor="w", padx=13, pady=(0, 11))

        form = ctk.CTkFrame(
            pagina, fg_color="#202B39", corner_radius=14,
            border_width=1, border_color="#2D3A4B"
        )
        form.pack(fill="x", pady=(0, 13))
        form.grid_columnconfigure((0, 1), weight=1, uniform="campos_meta")
        ctk.CTkLabel(
            form, text="Criar uma nova meta",
            text_color="#F4F7FC", font=ctk.CTkFont(size=16, weight="bold")
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(13, 5))

        campos = {}
        definicoes = [
            ("Nome da meta", "Ex.: Reserva de emergência"),
            ("Valor desejado", "Ex.: 5.000,00"),
            ("Valor inicial guardado", "Ex.: 0,00"),
            ("Prazo", "DD/MM/AAAA (opcional)"),
        ]
        for indice, (rotulo, placeholder) in enumerate(definicoes):
            linha = 1 + (indice // 2) * 2
            coluna = indice % 2
            ctk.CTkLabel(
                form, text=rotulo, text_color="#C5D0DE",
                font=ctk.CTkFont(size=11, weight="bold")
            ).grid(row=linha, column=coluna, sticky="w", padx=16, pady=(8, 3))
            entrada = ctk.CTkEntry(
                form, placeholder_text=placeholder, height=37,
                fg_color="#151F2D", border_color="#3A4A5E"
            )
            entrada.grid(row=linha + 1, column=coluna, sticky="ew", padx=16, pady=(0, 3))
            campos[rotulo] = entrada

        def criar():
            try:
                nome = campos["Nome da meta"].get().strip()
                objetivo = numero(campos["Valor desejado"].get())
                inicial = numero(campos["Valor inicial guardado"].get()) if campos["Valor inicial guardado"].get().strip() else 0
                prazo = data_iso(campos["Prazo"].get(), True)
                if not nome or objetivo <= 0 or inicial < 0 or inicial > objetivo:
                    raise ValueError("Confira o nome e os valores. O valor inicial não pode superar o objetivo.")
                db.inserir_meta(nome, objetivo, inicial, prazo)
                self.tela_metas()
            except (ValueError, TypeError) as erro:
                messagebox.showerror("Meta financeira", str(erro))

        ctk.CTkButton(
            form, text="Criar meta financeira", command=criar, height=39,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#1765A5", hover_color="#12558D"
        ).grid(row=5, column=0, columnspan=2, sticky="ew", padx=16, pady=(13, 16))

        cabecalho = ctk.CTkFrame(pagina, fg_color="transparent")
        cabecalho.pack(fill="x", pady=(3, 6))
        ctk.CTkLabel(
            cabecalho, text="Acompanhe suas metas",
            text_color="#F4F7FC", font=ctk.CTkFont(size=17, weight="bold")
        ).pack(side="left")
        ctk.CTkLabel(
            cabecalho, text=f"{len(metas)} objetivo(s)",
            text_color="#8F9BAD", font=ctk.CTkFont(size=10)
        ).pack(side="right")

        lista = ctk.CTkFrame(pagina, fg_color="transparent")
        lista.pack(fill="both", expand=True)

        if not metas:
            vazio = ctk.CTkFrame(lista, fg_color="#202B39", corner_radius=12)
            vazio.pack(fill="x", pady=4)
            ctk.CTkLabel(
                vazio, text="Você ainda não criou uma meta. Cadastre seu primeiro objetivo acima.",
                text_color="#AAB6C6"
            ).pack(anchor="w", padx=16, pady=22)

        for meta in metas:
            objetivo = float(meta["valor_objetivo"])
            guardado = float(meta["valor_atual"])
            percentual = min(guardado / objetivo, 1) if objetivo else 0
            falta = max(objetivo - guardado, 0)
            concluida = percentual >= 1

            cartao = ctk.CTkFrame(
                lista, fg_color="#202B39", corner_radius=13,
                border_width=1, border_color="#2D3A4B"
            )
            cartao.pack(fill="x", pady=5)
            cartao.grid_columnconfigure(0, weight=1)

            topo = ctk.CTkFrame(cartao, fg_color="transparent")
            topo.pack(fill="x", padx=15, pady=(12, 2))
            ctk.CTkLabel(
                topo, text=str(meta["nome"]), text_color="#F4F7FC",
                font=ctk.CTkFont(size=14, weight="bold")
            ).pack(side="left")
            ctk.CTkLabel(
                topo, text="CONCLUÍDA" if concluida else f"{percentual*100:.0f}% alcançado",
                text_color="#35B982" if concluida else "#69B8F0",
                font=ctk.CTkFont(size=10, weight="bold")
            ).pack(side="right")

            ctk.CTkLabel(
                cartao, text=f"{moeda(guardado)} de {moeda(objetivo)}",
                text_color="#DCE4EF", font=ctk.CTkFont(size=12, weight="bold")
            ).pack(anchor="w", padx=15, pady=(5, 7))

            barra = ctk.CTkProgressBar(
                cartao, height=10, progress_color="#35B982"
            )
            barra.pack(fill="x", padx=15, pady=(0, 7))
            barra.set(percentual)

            prazo_texto = data_br(meta["prazo"]) if meta["prazo"] else "Não definido"
            texto_status = "Objetivo alcançado!" if concluida else f"Faltam {moeda(falta)}"
            ctk.CTkLabel(
                cartao, text=f"{texto_status}   •   Prazo: {prazo_texto}",
                text_color="#35B982" if concluida else "#AAB6C6",
                font=ctk.CTkFont(size=10, weight="bold" if concluida else "normal")
            ).pack(anchor="w", padx=15, pady=(0, 9))

            acoes = ctk.CTkFrame(cartao, fg_color="transparent")
            acoes.pack(fill="x", padx=12, pady=(0, 12))
            if not concluida:
                deposito = ctk.CTkEntry(
                    acoes, placeholder_text="Valor do depósito",
                    width=190, height=35, fg_color="#151F2D",
                    border_color="#3A4A5E"
                )
                deposito.pack(side="left", padx=3)

                def registrar_deposito(mid=meta["id"], entrada=deposito):
                    try:
                        valor = numero(entrada.get())
                        if valor <= 0:
                            raise ValueError("Informe um valor de depósito maior que zero.")
                        db.adicionar_a_meta(mid, valor)
                        self.tela_metas()
                    except (ValueError, TypeError) as erro:
                        messagebox.showerror("Depósito", str(erro))

                ctk.CTkButton(
                    acoes, text="Adicionar valor",
                    command=registrar_deposito, width=130, height=35
                ).pack(side="left", padx=3)

            ctk.CTkButton(
                acoes, text="Ver histórico",
                command=lambda mid=meta["id"]: self.ver_historico_meta(mid),
                width=112, height=35, fg_color="#34465C",
                hover_color="#405773"
            ).pack(side="left", padx=3)

    def ver_historico_meta(self,mid):
        rows=db.historico_meta(mid)
        messagebox.showinfo("Histórico de depósitos","\n".join(f'{data_br(x["data"])} • {moeda(x["valor"])}' for x in rows) or "Sem depósitos registrados.")

    def tela_relatorios(self):
        self.limpar()
        self.titulo("Relatórios financeiros", "Acompanhe os resultados do mês e entenda para onde seu dinheiro está indo.")
        pagina = ctk.CTkScrollableFrame(self.area, fg_color="transparent", corner_radius=0)
        pagina.pack(fill="both", expand=True)
        filtros, menu_mes, menu_ano = self.seletor_periodo(pagina)
        filtros.pack(anchor="w", pady=(0, 12))
        conteudo = ctk.CTkFrame(pagina, fg_color="transparent")
        conteudo.pack(fill="both", expand=True)

        def atualizar(*_):
            for widget in conteudo.winfo_children():
                widget.destroy()
            mes, ano = self.periodo(menu_mes, menu_ano)
            receitas, despesas, _, pendentes = db.resumo_mes(ano, mes)
            resultado = receitas - despesas
            categorias = db.totais_categoria(ano, mes)

            faixa = ctk.CTkFrame(conteudo, fg_color="transparent")
            faixa.pack(fill="x", pady=(0, 12))
            indicadores = [
                ("RECEITAS", moeda(receitas), "#35B982"),
                ("DESPESAS", moeda(despesas), "#E6A23C"),
                ("RESULTADO DO MÊS", moeda(resultado), "#69B8F0" if resultado >= 0 else "#F07178"),
                ("DESPESAS PENDENTES", moeda(pendentes), "#F07178"),
            ]
            for i, (rotulo, valor, cor) in enumerate(indicadores):
                faixa.grid_columnconfigure(i, weight=1, uniform="relatorio")
                card = ctk.CTkFrame(faixa, fg_color="#202B39", corner_radius=12, border_width=1, border_color="#2D3A4B")
                card.grid(row=0, column=i, sticky="nsew", padx=4)
                ctk.CTkLabel(card, text=rotulo, text_color="#9AA5B5", font=ctk.CTkFont(size=9, weight="bold")).pack(anchor="w", padx=12, pady=(11, 3))
                ctk.CTkLabel(card, text=valor, text_color=cor, font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", padx=12, pady=(0, 11))

            painel = ctk.CTkFrame(conteudo, fg_color="#202B39", corner_radius=14, border_width=1, border_color="#2D3A4B")
            painel.pack(fill="x", pady=(0, 12))
            ctk.CTkLabel(painel, text="Visão geral do período", text_color="#F4F7FC", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", padx=16, pady=(14, 8))
            escala = max(receitas, despesas, 1)
            for nome, valor, cor in [("Receitas", receitas, "#35B982"), ("Despesas", despesas, "#E6A23C")]:
                linha = ctk.CTkFrame(painel, fg_color="transparent")
                linha.pack(fill="x", padx=16, pady=5)
                ctk.CTkLabel(linha, text=f"{nome}  •  {moeda(valor)}", text_color="#DCE4EF", font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", pady=(0, 5))
                barra = ctk.CTkProgressBar(linha, height=10, progress_color=cor)
                barra.pack(fill="x")
                barra.set(valor / escala)

            cat_card = ctk.CTkFrame(conteudo, fg_color="#202B39", corner_radius=14, border_width=1, border_color="#2D3A4B")
            cat_card.pack(fill="x", pady=(0, 12))
            ctk.CTkLabel(cat_card, text="Despesas por categoria", text_color="#F4F7FC", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", padx=16, pady=(14, 3))
            ctk.CTkLabel(cat_card, text="Categorias com maior participação nos gastos do período.", text_color="#9AA5B5", font=ctk.CTkFont(size=10)).pack(anchor="w", padx=16, pady=(0, 8))
            if categorias:
                maior = max(float(x["total"]) for x in categorias) or 1
                for item in sorted(categorias, key=lambda x: float(x["total"]), reverse=True):
                    valor = float(item["total"])
                    linha = ctk.CTkFrame(cat_card, fg_color="transparent")
                    linha.pack(fill="x", padx=16, pady=5)
                    topo = ctk.CTkFrame(linha, fg_color="transparent")
                    topo.pack(fill="x")
                    ctk.CTkLabel(topo, text=str(item["categoria"]), text_color="#DCE4EF", font=ctk.CTkFont(size=11, weight="bold")).pack(side="left")
                    ctk.CTkLabel(topo, text=moeda(valor), text_color="#E6A23C", font=ctk.CTkFont(size=11, weight="bold")).pack(side="right")
                    barra = ctk.CTkProgressBar(linha, height=8, progress_color="#E6A23C")
                    barra.pack(fill="x", pady=(5, 2))
                    barra.set(valor / maior)
            else:
                ctk.CTkLabel(cat_card, text="Não há despesas por categoria neste período.", text_color="#9AA5B5").pack(anchor="w", padx=16, pady=15)

            ctk.CTkButton(conteudo, text="Exportar relatório em CSV", command=lambda: self.exportar(ano, mes), height=38, fg_color="#1765A5", hover_color="#12558D", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", pady=(0, 12))

        menu_mes.configure(command=atualizar)
        menu_ano.configure(command=atualizar)
        atualizar()

    def exportar(self,ano,mes):
        path=filedialog.asksaveasfilename(defaultextension=".csv",filetypes=[("CSV","*.csv")],initialfile=f"finconecta_{ano}_{mes:02d}.csv")
        if path:
            try: db.exportar_csv(path,ano,mes); messagebox.showinfo("Exportação","Arquivo CSV exportado.")
            except Exception as e: messagebox.showerror("Exportação",str(e))

    def tela_educacao(self):
        self.limpar()
        self.titulo(
            "Educação financeira",
            "Dicas práticas para entender melhor seu dinheiro e fazer escolhas com mais tranquilidade."
        )

        pagina = ctk.CTkScrollableFrame(
            self.area, fg_color="transparent", corner_radius=0
        )
        pagina.pack(fill="both", expand=True)

        intro = ctk.CTkFrame(
            pagina, fg_color="#172B40", corner_radius=14,
            border_width=1, border_color="#254563"
        )
        intro.pack(fill="x", pady=(0, 14))
        self._adicionar_hover_animacao(
            intro, cor_normal="#172B40", cor_hover="#1D3852",
            borda_normal="#254563", borda_hover="#4A83B8"
        )
        ctk.CTkLabel(
            intro, text="Cuidar do dinheiro começa com pequenas decisões",
            text_color="#F4F7FC", font=ctk.CTkFont(size=21, weight="bold"),
            anchor="w"
        ).pack(fill="x", padx=18, pady=(14, 5))
        ctk.CTkLabel(
            intro,
            text="Não precisa mudar tudo de uma vez. Entender para onde o dinheiro vai, conhecer os juros e se preparar para imprevistos já faz diferença.",
            text_color="#C3D1E0", font=ctk.CTkFont(size=15),
            justify="left", anchor="w", wraplength=1100
        ).pack(fill="x", padx=18, pady=(0, 14))

        ctk.CTkLabel(
            pagina, text="Assuntos importantes para o seu dia a dia",
            text_color="#F4F7FC", font=ctk.CTkFont(size=18, weight="bold")
        ).pack(anchor="w", pady=(2, 7))

        conteudos = [
            ("Juros: quanto uma dívida realmente custa",
             "Juros são o valor cobrado pelo uso do dinheiro. Por isso, uma compra parcelada ou um empréstimo pode custar bem mais do que o valor inicial.",
             "Antes de contratar, compare o valor total que será pago, a taxa de juros e o Custo Efetivo Total (CET). Não escolha olhando somente se a parcela cabe no bolso.",
             "Exemplo: uma parcela pequena pode parecer vantajosa, mas muitas parcelas podem fazer o preço final ficar muito maior.",
             "#69B8F0"),
            ("Cartão de crédito: use sem perder o controle",
             "O cartão facilita as compras, mas cada compra compromete uma parte da renda dos próximos meses. A fatura reúne gastos que, separados, podem passar despercebidos.",
             "Anote ou acompanhe as compras durante o mês. Sempre que possível, pague o valor integral da fatura e evite usar o limite como se fosse renda extra.",
             "Dica: antes de parcelar, confira se as parcelas antigas já não ocupam boa parte do seu orçamento.",
             "#B28AE8"),
            ("Endividamento: organize antes de negociar",
             "Quando existem várias dívidas, fica difícil saber por onde começar. Ter todas as informações reunidas ajuda a enxergar o tamanho do compromisso.",
             "Faça uma lista com o nome do credor, saldo restante, valor da parcela, juros e vencimento. Depois, avalie quais dívidas têm o custo mais alto.",
             "Dica: só aceite uma renegociação depois de conferir se o novo valor cabe no orçamento até o fim do contrato.",
             "#F07178"),
            ("Reserva de emergência: prepare-se para imprevistos",
             "A reserva é um dinheiro separado para situações inesperadas, como um conserto urgente, uma despesa médica ou um período sem renda.",
             "Comece com um valor possível, mesmo que pequeno. Guarde um pouco com frequência e mantenha esse dinheiro separado das despesas do dia a dia.",
             "Exemplo: guardar R$ 30 por semana já ajuda a criar o hábito e formar uma reserva aos poucos.",
             "#35B982"),
            ("Investimentos: escolha de acordo com seus objetivos",
             "Antes de investir, pense para que precisa do dinheiro e quando pretende usá-lo. Prazo, possibilidade de resgate, riscos e custos fazem diferença.",
             "Entenda o produto antes de aplicar. Desconfie de promessas de lucro alto, rápido e garantido. Se não entender como funciona, procure informação antes de decidir.",
             "Lembrete: primeiro organize as contas e a reserva para imprevistos; depois avalie investimentos adequados ao seu perfil.",
             "#E6B85C"),
        ]

        for indice, (titulo, explicacao, acao, exemplo, cor) in enumerate(conteudos):
            card = ctk.CTkFrame(
                pagina, fg_color="#202B39", corner_radius=12,
                border_width=1, border_color="#2D3A4B"
            )
            card.pack(fill="x", pady=8)
            self._adicionar_hover_animacao(card)

            ctk.CTkLabel(
                card, text=titulo, text_color=cor,
                font=ctk.CTkFont(size=18, weight="bold"),
                anchor="w", justify="left"
            ).pack(fill="x", padx=16, pady=(16, 7))

            ctk.CTkLabel(
                card, text=explicacao, text_color="#DCE4EF",
                font=ctk.CTkFont(size=15), justify="left",
                anchor="w", wraplength=1150
            ).pack(fill="x", padx=16, pady=(0, 10))

            ctk.CTkLabel(
                card, text="O que fazer na prática",
                text_color="#69B8F0", font=ctk.CTkFont(size=15, weight="bold"),
                anchor="w"
            ).pack(fill="x", padx=16, pady=(0, 3))
            ctk.CTkLabel(
                card, text=acao, text_color="#C5D0DE",
                font=ctk.CTkFont(size=15), justify="left",
                anchor="w", wraplength=1150
            ).pack(fill="x", padx=16, pady=(0, 10))

            exemplo_box = ctk.CTkFrame(card, fg_color="#182638", corner_radius=8)
            exemplo_box.pack(fill="x", padx=16, pady=(0, 13))
            ctk.CTkLabel(
                exemplo_box, text=exemplo, text_color="#B7C8D9",
                font=ctk.CTkFont(size=14), justify="left",
                anchor="w", wraplength=1120
            ).pack(fill="x", padx=11, pady=9)

        fechamento = ctk.CTkFrame(
            pagina, fg_color="#172B40", corner_radius=12,
            border_width=1, border_color="#254563"
        )
        fechamento.pack(fill="x", pady=(10, 16))
        ctk.CTkLabel(
            fechamento, text="Uma sugestão para começar hoje",
            text_color="#F4F7FC", font=ctk.CTkFont(size=18, weight="bold"),
            anchor="w"
        ).pack(fill="x", padx=16, pady=(12, 4))
        ctk.CTkLabel(
            fechamento,
            text="Abra suas receitas e despesas no FinConecta e confira se todos os gastos dos últimos dias foram registrados. Escolha um pequeno ajuste possível para esta semana.",
            text_color="#C3D1E0", font=ctk.CTkFont(size=15),
            justify="left", anchor="w", wraplength=1100
        ).pack(fill="x", padx=16, pady=(0, 12))

    def _adicionar_hover_animacao(self, widget, cor_normal="#202B39",
                                  cor_hover="#29394B",
                                  borda_normal="#2D3A4B",
                                  borda_hover="#4A83B8"):
        """Realça suavemente um cartão quando o mouse passa sobre ele."""
        estado = {"hover": False, "after": None, "passo": 0}

        def cor_rgb(valor):
            valor = valor.lstrip("#")
            return tuple(int(valor[i:i + 2], 16) for i in (0, 2, 4))

        def para_hex(rgb):
            return "#{:02X}{:02X}{:02X}".format(*rgb)

        def misturar(a, b, fator):
            ca, cb = cor_rgb(a), cor_rgb(b)
            return para_hex(tuple(round(x + (y - x) * fator) for x, y in zip(ca, cb)))

        def animar(passo, entrando):
            fator = passo / 5
            if not entrando:
                fator = 1 - fator
            widget.configure(
                fg_color=misturar(cor_normal, cor_hover, fator),
                border_color=misturar(borda_normal, borda_hover, fator)
            )
            if passo < 5:
                estado["after"] = widget.after(
                    18, lambda: animar(passo + 1, entrando)
                )
            else:
                estado["after"] = None

        def entrar(_event=None):
            estado["hover"] = True
            if estado["after"] is not None:
                try:
                    widget.after_cancel(estado["after"])
                except Exception:
                    pass
                estado["after"] = None
            animar(1, True)

        def sair(_event=None):
            # Pequeno atraso evita piscar ao mover o mouse entre textos do cartão.
            if estado["after"] is not None:
                try:
                    widget.after_cancel(estado["after"])
                except Exception:
                    pass
            estado["after"] = widget.after(90, sair_confirmado)

        def sair_confirmado():
            if estado["hover"]:
                estado["hover"] = False
                animar(1, False)

        def ligar(widget_atual):
            try:
                widget_atual.bind("<Enter>", entrar, add="+")
                widget_atual.bind("<Leave>", sair, add="+")
                for filho in widget_atual.winfo_children():
                    ligar(filho)
            except Exception:
                pass

        ligar(widget)

    def tela_dicas(self):
        self.limpar()
        self.titulo(
            "Dicas inteligentes",
            "Uma leitura rápida dos seus registros para ajudar você a decidir o que merece atenção."
        )

        pagina = ctk.CTkScrollableFrame(
            self.area, fg_color="transparent", corner_radius=0
        )
        pagina.pack(fill="both", expand=True)

        mes = date.today().month
        ano = date.today().year
        receitas, despesas, dividas, pendentes = db.resumo_mes(ano, mes)
        alertas = []

        if receitas <= 0:
            alertas.append((
                "Comece pelas receitas",
                "Ainda não há receitas registradas neste mês. Cadastre salário, benefício ou outras entradas para que o resumo mostre melhor sua situação.",
                "Próximo passo: acesse Receitas e registre o que entrou no mês.",
                "#69B8F0"
            ))
        else:
            comprometimento = despesas / receitas * 100
            if comprometimento > 70:
                alertas.append((
                    "Boa parte da renda já está comprometida",
                    f"As despesas registradas representam {comprometimento:.1f}% das suas receitas. Vale conferir se ainda há contas importantes para vencer.",
                    "Próximo passo: revise as despesas e veja se existe algum gasto que pode esperar ou ser reduzido.",
                    "#F07178"
                ))
            elif comprometimento > 50:
                alertas.append((
                    "Atenção ao ritmo dos gastos",
                    f"Até agora, suas despesas representam {comprometimento:.1f}% das receitas registradas. Acompanhe os próximos gastos para não apertar o orçamento.",
                    "Próximo passo: confira as despesas variáveis, como lazer, compras e alimentação fora de casa.",
                    "#E6A23C"
                ))
            else:
                alertas.append((
                    "Você está acompanhando bem o orçamento",
                    f"As despesas registradas representam {comprometimento:.1f}% das receitas deste mês. Isso deixa uma parte da renda sem comprometimento nos lançamentos atuais.",
                    "Próximo passo: mantenha os registros atualizados e reserve uma parte do saldo para seus objetivos, se possível.",
                    "#35B982"
                ))

        if pendentes > 0:
            alertas.append((
                "Confira as contas que ainda faltam pagar",
                f"Há {moeda(pendentes)} em despesas marcadas como pendentes.",
                "Próximo passo: abra Despesas, confira os vencimentos e atualize a situação das contas que já foram pagas.",
                "#E6A23C"
            ))

        if dividas > 0:
            alertas.append((
                "Não perca as dívidas de vista",
                f"O sistema mostra {moeda(dividas)} em dívidas em aberto.",
                "Próximo passo: confira parcelas, juros e vencimentos. Se estiver difícil pagar, procure o credor para entender as opções de negociação.",
                "#F07178"
            ))

        if not alertas:
            alertas.append((
                "Continue mantendo seus registros em dia",
                "Ainda não há informações suficientes para montar recomendações específicas.",
                "Próximo passo: registre receitas e despesas conforme acontecerem.",
                "#69B8F0"
            ))

        topo = ctk.CTkFrame(
            pagina, fg_color="#172B40", corner_radius=14,
            border_width=1, border_color="#254563"
        )
        topo.pack(fill="x", pady=(0, 15))
        ctk.CTkLabel(
            topo, text="O que merece sua atenção neste mês",
            text_color="#F4F7FC", font=ctk.CTkFont(size=21, weight="bold"),
            anchor="w"
        ).pack(fill="x", padx=17, pady=(16, 6))
        ctk.CTkLabel(
            topo,
            text=f"Resumo calculado com base nos lançamentos de {date.today().strftime('%m/%Y')}.",
            text_color="#B7C8D9", font=ctk.CTkFont(size=15), anchor="w"
        ).pack(fill="x", padx=17, pady=(0, 16))

        for titulo, mensagem, proximo_passo, cor in alertas:
            card = ctk.CTkFrame(
                pagina, fg_color="#202B39", corner_radius=12,
                border_width=1, border_color="#2D3A4B"
            )
            card.pack(fill="x", pady=8)
            self._adicionar_hover_animacao(card)

            cabecalho = ctk.CTkFrame(card, fg_color="transparent")
            cabecalho.pack(fill="x", padx=16, pady=(15, 6))
            ctk.CTkLabel(
                cabecalho, text=titulo, text_color=cor,
                font=ctk.CTkFont(size=18, weight="bold"), anchor="w"
            ).pack(side="left", fill="x", expand=True)

            ctk.CTkLabel(
                card, text=mensagem, text_color="#DCE4EF",
                font=ctk.CTkFont(size=15), justify="left",
                anchor="w", wraplength=1120
            ).pack(fill="x", padx=16, pady=(0, 10))

            acao_box = ctk.CTkFrame(card, fg_color="#182638", corner_radius=8)
            acao_box.pack(fill="x", padx=16, pady=(0, 15))
            ctk.CTkLabel(
                acao_box, text=proximo_passo, text_color="#B7C8D9",
                font=ctk.CTkFont(size=14), justify="left",
                anchor="w", wraplength=1090
            ).pack(fill="x", padx=11, pady=9)

        nota = ctk.CTkLabel(
            pagina,
            text="Essas sugestões usam somente os dados cadastrados no sistema. Se algum lançamento estiver faltando ou incorreto, o resumo também pode mudar.",
            text_color="#8998AA", wraplength=1100, justify="left",
            anchor="w", font=ctk.CTkFont(size=14)
        )
        nota.pack(fill="x", anchor="w", pady=(10, 18))

    def tela_backup(self):
        self.limpar()
        self.titulo("Cópia de segurança", "Mantenha seus dados protegidos criando cópias do banco de dados.")
        pagina = ctk.CTkFrame(self.area, fg_color="transparent")
        pagina.pack(fill="both", expand=True)

        aviso = ctk.CTkFrame(pagina, fg_color="#172B40", corner_radius=14, border_width=1, border_color="#254563")
        aviso.pack(fill="x", pady=(0, 14))
        ctk.CTkLabel(aviso, text="Por que fazer backup?", text_color="#F4F7FC", font=ctk.CTkFont(size=17, weight="bold")).pack(anchor="w", padx=18, pady=(15, 5))
        ctk.CTkLabel(aviso, text="Uma cópia de segurança ajuda a recuperar seus registros caso aconteça algum problema no computador ou no banco de dados. Guarde o arquivo em um local seguro.", text_color="#B7C8D9", wraplength=950, justify="left").pack(anchor="w", padx=18, pady=(0, 15))

        cartao = ctk.CTkFrame(pagina, fg_color="#202B39", corner_radius=14, border_width=1, border_color="#2D3A4B")
        cartao.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(cartao, text="Criar uma cópia do banco", text_color="#F4F7FC", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", padx=18, pady=(16, 4))
        ctk.CTkLabel(cartao, text="Escolha onde deseja salvar o arquivo de backup. O banco original não será alterado.", text_color="#9AA5B5", wraplength=900, justify="left").pack(anchor="w", padx=18, pady=(0, 12))

        def salvar_backup():
            caminho = filedialog.asksaveasfilename(defaultextension=".db", filetypes=[("Banco SQLite", "*.db")], initialfile="finconecta_backup.db", title="Salvar cópia de segurança")
            if caminho:
                try:
                    db.backup_banco(caminho)
                    messagebox.showinfo("Backup concluído", "A cópia de segurança foi criada e verificada com sucesso.")
                except (ValueError, OSError) as erro:
                    messagebox.showerror("Erro ao criar backup", str(erro))

        ctk.CTkButton(cartao, text="Criar backup agora", command=salvar_backup, height=42, width=210, fg_color="#1765A5", hover_color="#12558D", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=18, pady=(0, 17))

        lembrete = ctk.CTkFrame(pagina, fg_color="#202B39", corner_radius=12, border_width=1, border_color="#2D3A4B")
        lembrete.pack(fill="x")
        ctk.CTkLabel(lembrete, text="Boas práticas", text_color="#69B8F0", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=16, pady=(12, 4))
        ctk.CTkLabel(lembrete, text="• Faça cópias regularmente.\n• Mantenha uma cópia fora do computador.\n• Não compartilhe o arquivo: ele contém seus registros financeiros.", text_color="#B9C5D3", justify="left").pack(anchor="w", padx=16, pady=(0, 13))

