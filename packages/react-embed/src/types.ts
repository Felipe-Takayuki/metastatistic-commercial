import type React from 'react';

export type EmbedType = 'report' | 'dashboard' | 'chart' | 'apa_table';

export type EmbedTheme = 'light' | 'dark' | 'auto';

export interface MetastatisticEmbedEvent {
  type: 'LOADED' | 'FILTER_CHANGE' | 'ROW_SELECT' | 'HEIGHT_CHANGE' | 'ERROR';
  payload?: any;
  sourceResource?: string;
}

export interface EmbedProps {
  /**
   * URL base do Gateway ou serviço MetaStatistic (ex.: "https://api.metastatistic.com" ou "http://localhost:8080")
   */
  targetUrl: string;

  /**
   * Tipo de recurso a ser embutido
   */
  embedType: EmbedType;

  /**
   * Identificador do recurso (ID do relatório, dashboard ou tabela)
   */
  resourceId: string;

  /**
   * Identificador do tenant para isolamento multi-tenant
   */
  tenantId?: string;

  /**
   * Token JWT de autenticação para acesso seguro
   */
  token?: string;

  /**
   * Tema visual do iframe embutido
   * @default 'auto'
   */
  theme?: EmbedTheme;

  /**
   * Filtros predefinidos aplicados aos dados exibidos
   */
  filters?: Record<string, any>;

  /**
   * Largura do container do iframe
   * @default '100%'
   */
  width?: string | number;

  /**
   * Altura do container do iframe. Se autoResize for verdadeiro, ajusta dinamicamente via postMessage.
   * @default '600px'
   */
  height?: string | number;

  /**
   * Se verdadeiro, escuta eventos de HEIGHT_CHANGE do conteúdo interno e ajusta a altura do iframe automaticamente.
   * @default true
   */
  autoResize?: boolean;

  /**
   * Classes CSS adicionais
   */
  className?: string;

  /**
   * Estilos CSS inline adicionais
   */
  style?: React.CSSProperties;

  /**
   * Callback disparado quando eventos ocorrem dentro do recurso embutido
   */
  onEvent?: (event: MetastatisticEmbedEvent) => void;

  /**
   * Callback disparado em caso de falha de carregamento ou erro reportado
   */
  onError?: (error: any) => void;

  /**
   * Callback disparado quando o iframe termina de carregar
   */
  onLoad?: () => void;
}
