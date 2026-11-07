# @metastatistic/react-embed

Componente React oficial para incorporação segura e de alta performance de relatórios, dashboards, gráficos e tabelas APA da plataforma MetaStatistic em aplicações externas.

## Instalação

```bash
pnpm add @metastatistic/react-embed
# ou
npm install @metastatistic/react-embed
```

## Exemplo de Uso

```tsx
import React from 'react';
import { MetastatisticEmbed } from '@metastatistic/react-embed';

export function ClinicalPortal() {
  return (
    <MetastatisticEmbed
      targetUrl="https://analytics.metastatistic.com"
      embedType="report"
      resourceId="rep_clinical_trial_01"
      tenantId="hospital-sph"
      token="jwt_secure_token"
      theme="light"
      filters={{ cohort: 'treatment-arm' }}
      onEvent={(evt) => console.log('Embed event:', evt)}
    />
  );
}
```

## Recursos
- `sandbox` seguro configurado por padrão.
- Sincronização bidirecional via `postMessage`.
- Redimensionamento dinâmico automático (`autoResize`).
- Suporte a temas (`light`, `dark`, `auto`).
