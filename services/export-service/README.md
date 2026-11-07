# MetaStatistic Export Service (`export-service`)

Microsserviço de exportação multi-formato de relatórios analíticos da plataforma MetaStatistic.

## Formatos Suportados
- **HTML/PDF**: Paged media CSS (`@page { size: A4; margin: 2.5cm; }`), formatação editorial estrita conforme normas APA 7th (tabelas sem linhas verticais, bordas horizontais superior/inferior/cabeçalho, notas de tabela).
- **LaTeX**: Documento acadêmico compilável com pacotes `booktabs`, `amsmath`, `geometry`, tabelas com `\toprule`, `\midrule`, `\bottomrule`, equações e seções hierárquicas.
- **DOCX**: Geração de documentos Microsoft Word com estilos tipográficos profissionais, tabelas formatadas e metadados.
- **Markdown**: Formatação GitHub Flavored Markdown (GFM) com tabelas em texto e blocos KaTeX.

## Portas
- Interna: `8006`
- Externa (Compose): `8016`
