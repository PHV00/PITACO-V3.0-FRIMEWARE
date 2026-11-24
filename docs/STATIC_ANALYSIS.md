# Análise estática e Quality Gate do firmware PITACO

**Estado:** implementação proposta em PR, sem alterar código de produção, limiares G1 ou APIs do dispositivo.

## Execução unificada

O workflow principal é \`.github/workflows/pitaco24-g1.yml\`, acionado em PRs de firmware e em push na main. Uma única execução GitHub Actions apresenta:

1. **host:** testes G1 compilados com g++, testes Python USB/BLE/PPG/bridge e verificações de scripts.
2. **esp32c3:** compilação real Arduino CLI para o ESP32-C3 canônico e sketch ESP32 legado, com Espressif Arduino core 3.3.9.
3. **static-analysis:** workflow reutilizável \`.github/workflows/firmware-static-analysis.yml\`, chamado apenas pelo pipeline principal; gera base de compilação do sketch e executa Cppcheck + Clang-Tidy G1.
4. **quality-gate:** resultado final obrigatório que somente passa quando os três jobs anteriores terminam com sucesso.

Não executamos dois pipelines de compilação/testes independentes para o mesmo PR. A etapa estática precisa compilar seu próprio sketch para obter o \`compile_commands.json\` no runner isolado.

## Atribuição correta dos alertas

**Relatório inspecionado (run 45402264452, 24/11/2026):**

- Cppcheck reportou **77** achados.
- **75** estavam em arquivos da plataforma Arduino/ESP32 3.3.9, não escritos pela equipe do projeto.
- **2** foram avisos de estilo \`cstyleCast\` no arquivo autoral \`frimeware2.4/communication/pitaco_ble_ota.ino\`, linhas 89 e 155 na versão analisada.
- Clang-Tidy sobre o sketch completo falhou no parser de argumentos GCC \`-fno-tree-switch-conversion\`, \`-fstrict-volatile-bitfields\` e na localização de \`<algorithm>\` no ambiente cruzado. Seu resultado anterior **não era válido como análise concluída do sketch inteiro**.

Por isso a análise nova tem escopos distintos e declarados:

- **Cppcheck:** unidade compilada completa \`frimeware2.4.ino.cpp\`, incluindo cabeçalhos do core ESP32. O parser separa arquivos de código autoral, vendor, toolchain e fontes geradas.
- **Clang-Tidy:** o mesmo **código de produção do Gate 01**, incluído e compilado pelo teste C++ de host \`test/test_sqi_gate1.cpp\`, com \`clang-analyzer-*\` e \`bugprone-*\`. Esta etapa **não representa uma auditoria do firmware ESP32 inteiro**.

## Critério verificável

A Action reprova quando ocorrer qualquer condição:

- Falha de teste host, compilação ESP32-C3 ou compilação ESP32 legado.
- Falta de XML Cppcheck válido ou de status de qualquer analisador.
- Código de saída incompatível com execução do Cppcheck (retornos 0 ou 2 são esperados; 2 representa diagnósticos quando \`--error-exitcode=2\`).
- Clang-Tidy G1 não executa com sucesso.
- Pelo menos **um alerta classificado severity=error em arquivo autoral** no XML ou saída Clang-Tidy.

As categorias warning/style/performance/portability são **visíveis e exigem triagem**, mas ainda não reprovam automaticamente; os 75 avisos externos do core não são atribuídos falsamente ao firmware próprio. Não há pontuação fictícia ou supressão silenciosa dos problemas.

## Visualização na interface GitHub

Abra **Actions → PITACO firmware — testes, build e qualidade de código**:

- A página de execução mostra resultado **host / esp32c3 / static-analysis / quality-gate**.
- O job static-analysis publica a tabela Markdown em **Job Summary**, com alertas do código autoral, motivo de bloqueio, contagens por ferramenta e categoria.
- Alertas do código autoral com localização física válida são publicados como **annotations**, quando possível.
- O artifact \`pitaco-esp32c3-static-analysis\` contém \`report.html\` com **todas** as ocorrências, \`issues.json\`, XML Cppcheck, texto Clang-Tidy, versões e manifesto de cobertura.
- GitHub compacta artifacts em ZIP. **Não é necessário baixar o ZIP para ler o resumo da Action**; baixe somente para abrir o HTML detalhado ou processar os arquivos brutos.

O HTML é autocontido e pode ser aberto no navegador após extrair o artifact. Para histórico permanente ou dashboards futuros pode-se converter apenas os achados autorais com localização confiável em SARIF para Code Scanning; isso exige nova validação de mapeamento para arquivos .ino e não foi ativado nesta etapa.

## Testes do próprio Quality Gate

Os cenários automáticos em \`test/test_firmware_quality_report.py\` verificam:

- relatório limpo (PASS);
- aviso de estilo (registrado, não bloqueante);
- erro de código autoral (FAIL);
- falha de execução do Clang-Tidy (FAIL);
- XML inválido ou ausente (FAIL).

Estes testes são executados pelo job host já existente através de \`python3 -m unittest discover\`.

## Limitações

- Compilação e análise estática não provam leitura correta do sensor MAX30105, temporização real, FIFO sem perdas ou segurança clínica.
- Um job verde não significa "zero avisos": significa que os critérios documentados foram satisfeitos.
- A inspeção do Clang-Tidy no sketch completo permanece uma melhoria futura, dependente de preparar uma base Clang/C++ adequada para a toolchain RISCV ESP32.
- Testes HIL reais no ESP32-C3, comparação com sinais de referência e rastreabilidade do binário físico continuam necessários.
