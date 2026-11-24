# Análise estática do firmware PITACO

**Status: configuração inicial em PR, ainda sem validação do primeiro run.** Esta documentação não constitui relatório de resultados nem prova de ausência de problemas.

## Objetivo

Executar **Cppcheck** e **Clang-Tidy** por GitHub Actions, mantendo os testes atuais do G1, Python/bridge e compilação Arduino CI **inalterados**. A análise adicional ocorre no workflow `.github/workflows/firmware-static-analysis.yml`, não substitui a Action existente `pitaco24-g1.yml` nem modifica código de produção.

## Por que gerar C++ a partir do sketch

O firmware canônico usa `frimeware2.4/frimeware2.4.ino` com outros módulos autorais `.ino` incluídos explicitamente em subdiretórios. Analisá-los separadamente como se cada um fosse unidade independente pode causar erros espúrios e omitir contexto. Por isso, esta primeira etapa:

1. configura Arduino CLI e a mesma plataforma **ESP32-C3** da compilação de referência, fixando **arduino-esp32 3.3.9**; o core 4.0.0 alterou a interface BLE e não aceita diretamente o código existente;
2. compila o sketch real em um diretório de build separado;
3. gera `compile_commands.json` com `arduino-cli compile --only-compilation-database`;
4. exige que a entrada **frimeware2.4.ino.cpp** exista no banco e no disco, contendo funções-chave do firmware;
5. executa Cppcheck no sketch gerado, usando o banco de compilação;
6. executa Clang-Tidy no mesmo sketch em modo **exploratório**, utilizando a mesma base de argumentos;
7. publica arquivos XML, texto, versões das ferramentas e manifesto de cobertura como artefato GitHub.

**Limite:** a preparação do build e a análise do sketch não garantem auditoria individual de todo o driver SparkFun vendorizado. O objetivo primário é código **autoral** do firmware e sua árvore de inclusões. Em caso de inconsistência de cobertura, corrigir o comando antes de declarar a análise aprovada.

## Políticas de CI

- **Build e descoberta do arquivo real são obrigatórios.** Falha na geração do `compile_commands.json` ou ausência da unidade do firmware causa falha no job.
- **Cppcheck e Clang-Tidy começam não bloqueantes** para criar baseline; os relatórios não podem ser considerados um status de aprovação de segurança.
- Depois de revisar alertas legítimos e falsos positivos, registrar decisões e estabelecer gatilho de falha para novas ocorrências críticas.
- Clang-Tidy pode exigir ajustes em flags/headers de ferramentas ESP32 e versões de Clang; erros de infraestrutura devem ser reportados, não silenciados.
- Nenhuma ferramenta aqui valida qualidade de PPG/SQI, BPM, acurácia de SpO₂ ou segurança clínica.

## Onde ficam as evidências

Em Actions → **PITACO firmware - static analysis (Cppcheck / Clang-Tidy)** → execução → artifact `pitaco-esp32c3-static-analysis`:

| Arquivo | Finalidade |
| --- | --- |
| `coverage-manifest.txt` | Unidade gerada, origem e banco de compilação |
| `cppcheck.xml` | Achados reportados por Cppcheck |
| `cppcheck-version.txt` | Versão Cppcheck do runner |
| `clang-tidy.txt` | Saída de execução Clang-Tidy |
| `clang-tidy-version.txt` | Versão Clang-Tidy do runner |
| `SUMMARY.md` | Síntese da execução e ressalvas |

## Próxima etapa

Verificar que o primeiro run realmente identifica `frimeware2.4.ino.cpp`, que o XML é válido, e que o Clang-Tidy não aborta por toolchain desconhecida. Registrar no [hub documental](https://github.com/PHV00/RFC-IBlueIt-Pitaco3.0-Multimodal) o link do run com commit/versão e classificação dos achados. Só então considerar quality gate.
