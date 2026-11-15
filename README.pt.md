# Aschenbach Transcriptor

Ferramenta de transcrição de arquivos de áudio e vídeo com **Whisper** (local), **Google Gemini** e **AssemblyAI**. Funciona como um servidor web local com interface single-page.

> **[Read in English](README.md)**

---

## Funcionalidades

- Upload por arrastar e soltar ou seleção de arquivos de áudio e vídeo
- **Whisper (local):** transcrição offline usando [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — nenhum dado sai da sua máquina
- **Gemini:** transcrição via API do Google Generative AI
  - Modo síncrono (`gemini-3.5-transcribe`): diarização nativa de falantes e timestamps por palavra
  - Modo batch assíncrono (`gemini-3.5-flash`, `gemini-3.1-flash-lite`, `gemini-3.8-flash`): envie e volte depois; chunks de até 58 minutos
- **AssemblyAI:** API pré-gravada com escolha entre Universal-3 Pro e Universal-3.5 Pro, português (`pt`) e diarização opcional; até quatro transcrições simultâneas
- Exportação de transcrições como `.txt` ou `.md`, com ou sem timestamps
- Histórico de jobs persistido entre reinicializações (retenção configurável)
- Modelos Gemini configuráveis via `gemini_models.toml` sem alterar código

---

## Requisitos

- Python 3.11+
- Gerenciador de pacotes [uv](https://github.com/astral-sh/uv)
- Windows (para captura de áudio WASAPI, se usar funções ao vivo; a transcrição em si é multiplataforma)
- FFmpeg disponível no PATH (para extração de áudio de vídeos)

---

## Instalação

```bash
git clone https://github.com/aaschenbach/aschenbach-transcriptor.git
cd aschenbach-transcriptor
uv sync
```

---

## Configuração

Copie `.env.example` para `.env` e preencha os valores necessários:

```env
# Necessário para transcrição com Gemini
GEMINI_API_KEY=

# Necessário para transcrição com AssemblyAI
ASSEMBLYAI_API_KEY=

# Opcional: token do Hugging Face para modelos Whisper restritos
HUGGING_FACE_HUB_TOKEN=

# Chave do modelo Gemini padrão (veja gemini_models.toml: transcribe, recommended, lite, difficult)
GEMINI_DEFAULT_MODEL=recommended

# Quantos dias manter o histórico de jobs (padrão: 30)
HISTORY_RETENTION_DAYS=30
```

`GEMINI_API_KEY` só é necessário se você usar o Gemini. O Whisper funciona sem ele.

Para usar AssemblyAI na interface ou no script de lote, configure `ASSEMBLYAI_API_KEY` no `.env` (ou no ambiente). A interface permite escolher Universal-3 Pro ou Universal-3.5 Pro; o script usa Universal-3.5 Pro.

### Modelos Gemini

Edite `gemini_models.toml` para adicionar, remover ou atualizar modelos Gemini sem alterar nenhum código:

```toml
[[models]]
key         = "recommended"
id          = "gemini-3.5-flash"
label       = "Flash 3.5"
description = "Uso geral, melhor equilíbrio entre custo e precisão. Batch assíncrono."
mode        = "batch"
```

---

## Execução

```bash
uv run aa-transcript
```

Depois abra [http://127.0.0.1:8181](http://127.0.0.1:8181) no navegador.

### Lote AssemblyAI

Coloque arquivos `.mp3`, `.wav`, `.m4a`, `.flac`, `.ogg` ou `.webm` em `audios/` e execute:

```powershell
uv run python transcrever_lote.py
```

O script processa até quatro arquivos ao mesmo tempo e grava um `.txt` por arquivo em `transcricoes/`, com timestamps e cada fala marcada como `Falante A`, `Falante B` etc. Uma falha é informada no terminal sem interromper os demais arquivos. As letras distinguem vozes apenas dentro de cada arquivo; não são nomes reais nem permanecem consistentes entre arquivos. A identificação pode errar, especialmente em falas curtas ou sobrepostas. Para melhorar nomes próprios ou termos técnicos, adicione `keyterms_prompt=[...]` em `TranscriptionConfig` no script.

---

## Uso

1. Arraste arquivos de áudio ou vídeo para a área de upload, ou clique para selecionar.
2. Para cada arquivo, escolha um **backend** (Whisper, Gemini ou AssemblyAI) e um **modelo**. No AssemblyAI, a diarização vem ativada por padrão.
3. Clique em **Enviar para transcrição**.
4. Jobs do Whisper completam em segundos a minutos dependendo do tamanho do arquivo e do modelo. Jobs batch do Gemini rodam de forma assíncrona — clique em **Verificar agora** para consultar o resultado. Jobs AssemblyAI são processados em segundo plano enquanto o servidor estiver aberto.
5. Quando concluído, expanda o card do job para ler a transcrição e exportá-la.

### Modelos Whisper

| Modelo | Tamanho | Observações |
|---|---|---|
| tiny | ~75 MB | Mais rápido, menor precisão |
| base | ~145 MB | Bom padrão para tarefas rápidas |
| small | ~465 MB | Melhor precisão |
| medium | ~1,5 GB | Alta precisão, mais lento |
| large-v3 | ~3 GB | Melhor precisão disponível |

Os modelos baixados ficam em cache em `~/.cache/huggingface/hub/`. A primeira execução de cada modelo faz o download automaticamente.

### Modelos Gemini

| Modelo | Modo | Indicado para |
|---|---|---|
| `gemini-3.5-transcribe` | Síncrono | Arquivos curtos, necessita diarização |
| `gemini-3.5-flash` | Batch | Uso geral |
| `gemini-3.1-flash-lite` | Batch | Alto volume, menor custo |
| `gemini-3.8-flash` | Batch | Áudio ruidoso, sotaque forte |

O Transcribe 3.5 divide o áudio em blocos de até 2 minutos, procura pausas próximas dos cortes e mantém 2 segundos de sobreposição nas bordas. Com timestamps, trechos repetidos são atribuídos a um único bloco. O app permite até duas chamadas por janela de 60 segundos, inclusive entre arquivos em execução, mantendo margem para o limite de 10 mil tokens por minuto informado pelo projeto. Se a API responder `429`, o app respeita o prazo `Please retry in...` e faz até 5 novas tentativas. O limite de 100 requisições por dia é separado: arquivos muito longos ou outros consumidores da mesma cota podem esgotá-lo. Nesse caso, o app informa a falha; ainda não retoma automaticamente no dia seguinte. A cota é por projeto, não por chave de API.

Resultados batch expiram 48 horas após a conclusão do job no Google.

---

## Estrutura do projeto

```
src/aa_transcript/
├── main.py           # FastAPI app, endpoints (porta 8181)
├── gemini_backend.py # Lógica Gemini sync + batch
├── assemblyai_backend.py # Lógica AssemblyAI pré-gravada
├── transcriber.py    # Wrapper faster-whisper, listagem de modelos
├── whisper_backend.py # Execução do Whisper
├── jobs.py           # Dataclasses Job e Segment
├── store.py          # Persistência JSON, purga por idade
└── exporter.py       # Exportação .txt e .md

static/
└── index.html        # UI completa (HTML + CSS + JS, sem framework)

gemini_models.toml    # Configuração dos modelos Gemini
```

---

## Licença

Este software é de domínio público. Veja [LICENSE](LICENSE).

---

by [Alexandre Aschenbach](https://github.com/aaschenbach)
