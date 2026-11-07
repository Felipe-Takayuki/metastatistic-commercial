import React, { useEffect, useMemo, useRef, useState } from 'react';
import type { EmbedProps, MetastatisticEmbedEvent } from './types.js';

export function buildEmbedUrl(props: {
  targetUrl: string;
  embedType: string;
  resourceId: string;
  tenantId?: string;
  token?: string;
  theme?: string;
  filters?: Record<string, any>;
}): string {
  const baseUrl = props.targetUrl.replace(/\/+$/, '');
  const path = `/embed/${props.embedType}/${encodeURIComponent(props.resourceId)}`;
  const searchParams = new URLSearchParams();

  if (props.theme) {
    searchParams.set('theme', props.theme);
  }
  if (props.tenantId) {
    searchParams.set('tenant', props.tenantId);
  }
  if (props.token) {
    searchParams.set('token', props.token);
  }
  if (props.filters && Object.keys(props.filters).length > 0) {
    searchParams.set('filters', JSON.stringify(props.filters));
  }

  const query = searchParams.toString();
  return query ? `${baseUrl}${path}?${query}` : `${baseUrl}${path}`;
}

export const MetastatisticEmbed: React.FC<EmbedProps> = ({
  targetUrl,
  embedType,
  resourceId,
  tenantId,
  token,
  theme = 'auto',
  filters,
  width = '100%',
  height = '600px',
  autoResize = true,
  className,
  style,
  onEvent,
  onError,
  onLoad,
}) => {
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const [dynamicHeight, setDynamicHeight] = useState<string | number>(height);

  const embedUrl = useMemo(() => {
    return buildEmbedUrl({
      targetUrl,
      embedType,
      resourceId,
      tenantId,
      token,
      theme,
      filters,
    });
  }, [targetUrl, embedType, resourceId, tenantId, token, theme, filters]);

  // Listener para postMessage
  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      // Ignora mensagens sem payload estruturado
      if (!event.data || typeof event.data !== 'object') {
        return;
      }

      const metaEvent = event.data as MetastatisticEmbedEvent;

      // Evento de ajuste automático de altura
      if (metaEvent.type === 'HEIGHT_CHANGE' && autoResize && metaEvent.payload?.height) {
        setDynamicHeight(`${metaEvent.payload.height}px`);
      }

      // Encaminha erros específicos
      if (metaEvent.type === 'ERROR') {
        onError?.(metaEvent.payload);
      }

      onEvent?.(metaEvent);
    };

    window.addEventListener('message', handleMessage);
    return () => {
      window.removeEventListener('message', handleMessage);
    };
  }, [autoResize, onEvent, onError]);

  // Sincroniza tema ou filtros via postMessage se mudarem dinamicamente
  useEffect(() => {
    if (iframeRef.current?.contentWindow) {
      iframeRef.current.contentWindow.postMessage(
        {
          action: 'UPDATE_CONFIG',
          theme,
          filters,
        },
        '*'
      );
    }
  }, [theme, filters]);

  return (
    <iframe
      ref={iframeRef}
      src={embedUrl}
      title={`MetaStatistic ${embedType} - ${resourceId}`}
      width={width}
      height={autoResize ? dynamicHeight : height}
      className={className}
      style={{
        border: 'none',
        display: 'block',
        width: typeof width === 'number' ? `${width}px` : width,
        height: typeof dynamicHeight === 'number' ? `${dynamicHeight}px` : dynamicHeight,
        borderRadius: '6px',
        ...style,
      }}
      sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
      onLoad={onLoad}
    />
  );
};

export default MetastatisticEmbed;
