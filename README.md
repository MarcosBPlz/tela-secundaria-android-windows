# Tela Tablet

Transforma um tablet ou celular Android velho num **painel de mesa** ligado ao seu PC com Windows: relógio, clima, agenda, lista de compras, o que está tocando no PC, uso de CPU/RAM/temperatura e um assistente de voz simples, tudo com fundo animado e visual de vidro.

O PC roda um servidor pequeno em Python. O tablet (ou o próprio navegador do PC) abre o painel pela rede Wi-Fi de casa. Nada vai para a nuvem: lista, agenda e ajustes ficam salvos no seu PC.

## O que tem

- **Relógio e clima** (Open-Meteo, sem chave de API) com a cidade que você escolher.
- **Agenda do dia** e **lista de compras** compartilhadas entre PC, tablet e celular.
- **Tocando agora**: música do Spotify ou do navegador, pela sessão de mídia do Windows.
- **Seu computador**: uso de processador, memória e temperatura (GPU NVIDIA automática; CPU com o LibreHardwareMonitor).
- **Bateria do mouse** Attack Shark/Xenta (opcional).
- **Assistente de voz "Chat"**: “põe café na lista”, “marca dentista amanhã às duas da tarde”, “o que tenho amanhã?”. Funciona por regras locais, sem IA paga.
- **Layout editável**: no PC, arraste e redimensione os quadros; o tablet mostra igualzinho.
- **Layout vertical** automático no celular/tablet em pé.
- **Fundos** em vídeo, GIF ou imagem.
- **Ícone na bandeja do Windows**: o servidor roda escondido, sem janela de terminal.

## Requisitos

- Windows 10 ou 11 com **Python 3.11+** ([python.org](https://www.python.org/downloads/), marque “Add Python to PATH”).
- Tablet/celular **Android 8+** na mesma rede Wi-Fi do PC.
- Para compilar o app: **Android Studio**.

## Como usar

### 1. No PC

1. Baixe o projeto (botão **Code → Download ZIP**) e extraia numa pasta.
2. Dê dois cliques em **`abrir_windows.bat`**.
   - Na primeira vez ele instala a integração de música do Windows (precisa de internet).
   - Aparece um ícone roxo perto do relógio do Windows (na setinha **^** dos ícones ocultos) e o painel abre.
3. Clique com o botão direito no ícone → **Copiar endereço do tablet**. É algo como `http://192.168.0.20:47811`.
4. Se o Windows perguntar sobre o firewall, permita em **rede privada**.

Menu do ícone: abrir painel, copiar endereço, abrir pasta, **iniciar com o Windows** e sair.
Se algo der errado, rode `iniciar.bat` (mostra o terminal com os erros) ou veja `data/tray.log`.

### 2. No tablet/celular

1. Abra a pasta `android/` no **Android Studio**.
2. Menu **Build → Generate App Bundles or APKs → Generate APKs**.
3. Instale o `app-debug.apk` gerado no aparelho.
4. Abra o app, cole o endereço do PC e toque em **Conectar**.

Sem instalar nada, também dá para abrir o endereço direto no navegador do tablet (mas a voz funciona melhor no app).

### Ajustes

Toque na engrenagem discreta no **canto inferior direito** (ou deslize da borda direita para a esquerda). Ali você muda cidade, cor, fundo, tamanho dos elementos, quais quadros aparecem e, no app, a orientação da tela.

### Assistente de voz

Toque no microfone e fale, começando ou não com “Chat”:

| Você diz | O que acontece |
|---|---|
| põe arroz, feijão e leite na lista | adiciona os três |
| tira o leite / comprei o café | remove / risca |
| o que tem na lista? | lê a lista |
| marca dentista amanhã às duas da tarde | cria o compromisso |
| reunião sexta às 9 e meia | cria o compromisso |
| o que tenho amanhã? / cancela o dentista | consulta / cancela |

O reconhecimento de fala é feito pelo serviço do Google no aparelho; o entendimento do pedido acontece no seu PC (`voice_assistant.py`).

### Temperatura do PC

- **Placa NVIDIA**: aparece sozinha (“Temperatura GPU”).
- **CPU**: abra o [LibreHardwareMonitor](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor) e ligue *Options → Remote Web Server → Run* (porta 8085).

## Estrutura

```
server.py            servidor HTTP e APIs (status, lista, agenda, ajustes, voz)
tray.py              ícone na bandeja do Windows (inicia o servidor escondido)
index.html           o painel (HTML/CSS/JS, um arquivo só)
voice_assistant.py   interpreta os comandos de voz
temperature.py       leitura de temperatura (LibreHardwareMonitor / NVIDIA)
media_sessions.py    “tocando agora” via Windows Media Session
attackshark_battery/ bateria do mouse Attack Shark (MIT, projeto Attack Shark Battery Tray)
android/             app Android (WebView + reconhecimento e síntese de voz)
data/                seus dados (lista, agenda, ajustes) — não vão para o Git
media/               seus fundos — não vão para o Git
```

A porta padrão é `47811` (mude com a variável de ambiente `TABLET_PANEL_PORT`).

## Licença

MIT. A pasta `attackshark_battery/` deriva do projeto Attack Shark Battery Tray, também sob licença MIT (veja o `LICENSE` dentro dela).
