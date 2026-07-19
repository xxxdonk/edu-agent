export interface MermaidClient {
  initialize(config: {
    startOnLoad: boolean;
    securityLevel: 'strict';
    theme: 'neutral';
    suppressErrorRendering: boolean;
  }): void;
  parse(source: string, options: {suppressErrors: boolean}): Promise<unknown | false>;
  render(
    id: string,
    source: string,
    container: HTMLElement,
  ): Promise<{svg: string; bindFunctions?: (element: Element) => void}>;
}

export type MermaidRenderOutcome =
  | {status: 'success'; svg: string; bindFunctions?: (element: Element) => void}
  | {status: 'invalid' | 'failed' | 'stale'};

export interface MermaidRenderSession {
  cancel(): void;
  result: Promise<MermaidRenderOutcome>;
}

interface MermaidRenderOptions {
  mermaid: MermaidClient;
  source: string;
  renderId: string;
  container: HTMLElement;
  isCurrent: () => boolean;
}

export function startIsolatedMermaidRender(options: MermaidRenderOptions): MermaidRenderSession {
  let cancelled = false;
  let cleaned = false;
  const isLive = () => !cancelled && options.isCurrent();
  const cleanup = () => {
    if (cleaned) return;
    cleaned = true;
    options.container.remove();
  };

  const result = (async (): Promise<MermaidRenderOutcome> => {
    try {
      options.mermaid.initialize({
        startOnLoad: false,
        securityLevel: 'strict',
        theme: 'neutral',
        suppressErrorRendering: true,
      });

      const parsed = await options.mermaid.parse(options.source, {suppressErrors: true});
      if (!isLive()) return {status: 'stale'};
      if (!parsed) return {status: 'invalid'};

      const rendered = await options.mermaid.render(
        options.renderId,
        options.source,
        options.container,
      );
      if (!isLive()) return {status: 'stale'};
      return {status: 'success', svg: rendered.svg, bindFunctions: rendered.bindFunctions};
    } catch {
      return {status: isLive() ? 'failed' : 'stale'};
    } finally {
      cleanup();
    }
  })();

  return {
    cancel() {
      cancelled = true;
      cleanup();
    },
    result,
  };
}
