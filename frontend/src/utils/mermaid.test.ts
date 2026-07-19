import {describe, expect, it, vi} from 'vitest';
import {startIsolatedMermaidRender, type MermaidClient} from './mermaid';

function fakeContainer() {
  return {remove: vi.fn()} as unknown as HTMLElement;
}

function fakeMermaid(overrides: Partial<MermaidClient> = {}) {
  const initialize = vi.fn();
  const parse = vi.fn().mockResolvedValue({diagramType: 'flowchart-v2'});
  const render = vi.fn().mockResolvedValue({svg: '<svg>valid diagram</svg>'});
  return {
    client: {initialize, parse, render, ...overrides} as MermaidClient,
    initialize,
    parse,
    render,
  };
}

describe('startIsolatedMermaidRender', () => {
  it('parses before rendering a valid diagram into the supplied local container', async () => {
    const mermaid = fakeMermaid();
    const container = fakeContainer();
    const session = startIsolatedMermaidRender({
      mermaid: mermaid.client,
      source: 'flowchart LR\nA-->B',
      renderId: 'diagram-1',
      container,
      isCurrent: () => true,
    });

    await expect(session.result).resolves.toEqual({
      status: 'success',
      svg: '<svg>valid diagram</svg>',
      bindFunctions: undefined,
    });
    expect(mermaid.initialize).toHaveBeenCalledWith(expect.objectContaining({
      startOnLoad: false,
      suppressErrorRendering: true,
    }));
    expect(mermaid.parse).toHaveBeenCalledWith('flowchart LR\nA-->B', {suppressErrors: true});
    expect(mermaid.render).toHaveBeenCalledWith('diagram-1', 'flowchart LR\nA-->B', container);
    expect(mermaid.parse.mock.invocationCallOrder[0]).toBeLessThan(mermaid.render.mock.invocationCallOrder[0]);
    expect(container.remove).toHaveBeenCalledTimes(1);
  });

  it('does not render or leak a temporary node when parsing fails', async () => {
    const mermaid = fakeMermaid({parse: vi.fn().mockResolvedValue(false)});
    const container = fakeContainer();
    const session = startIsolatedMermaidRender({
      mermaid: mermaid.client,
      source: 'not valid mermaid',
      renderId: 'diagram-invalid',
      container,
      isCurrent: () => true,
    });

    await expect(session.result).resolves.toEqual({status: 'invalid'});
    expect(mermaid.render).not.toHaveBeenCalled();
    expect(container.remove).toHaveBeenCalledTimes(1);
  });

  it('does not append Mermaid error markup to document.body', async () => {
    const body = {appendChild: vi.fn(), innerHTML: ''};
    vi.stubGlobal('document', {body});
    const mermaid = fakeMermaid({parse: vi.fn().mockResolvedValue(false)});
    const session = startIsolatedMermaidRender({
      mermaid: mermaid.client,
      source: 'invalid',
      renderId: 'body-safe',
      container: fakeContainer(),
      isCurrent: () => true,
    });

    await expect(session.result).resolves.toEqual({status: 'invalid'});
    expect(body.appendChild).not.toHaveBeenCalled();
    expect(body.innerHTML).not.toContain('Syntax error in text');
    vi.unstubAllGlobals();
  });

  it('cleans the isolated container when rendering fails after a valid parse', async () => {
    const failingRender = vi.fn().mockRejectedValue(new Error('draw failed'));
    const mermaid = fakeMermaid({render: failingRender});
    const container = fakeContainer();
    const session = startIsolatedMermaidRender({
      mermaid: mermaid.client,
      source: 'flowchart LR\nA-->B',
      renderId: 'draw-failure',
      container,
      isCurrent: () => true,
    });

    await expect(session.result).resolves.toEqual({status: 'failed'});
    expect(failingRender).toHaveBeenCalledWith('draw-failure', 'flowchart LR\nA-->B', container);
    expect(container.remove).toHaveBeenCalledTimes(1);
  });

  it('cleans every local container across three repeated invalid renders', async () => {
    const mermaid = fakeMermaid({parse: vi.fn().mockResolvedValue(false)});
    const containers = [fakeContainer(), fakeContainer(), fakeContainer()];
    const results = await Promise.all(containers.map((container, index) => (
      startIsolatedMermaidRender({
        mermaid: mermaid.client,
        source: 'invalid',
        renderId: `invalid-${index}`,
        container,
        isCurrent: () => true,
      }).result
    )));

    expect(results).toEqual([{status: 'invalid'}, {status: 'invalid'}, {status: 'invalid'}]);
    expect(mermaid.render).not.toHaveBeenCalled();
    for (const container of containers) expect(container.remove).toHaveBeenCalledTimes(1);
  });

  it('recovers from invalid content when the next resource is valid', async () => {
    const invalid = fakeMermaid({parse: vi.fn().mockResolvedValue(false)});
    const valid = fakeMermaid();
    const invalidResult = startIsolatedMermaidRender({
      mermaid: invalid.client, source: 'invalid', renderId: 'invalid', container: fakeContainer(), isCurrent: () => true,
    }).result;
    const validResult = startIsolatedMermaidRender({
      mermaid: valid.client, source: 'flowchart LR\nA-->B', renderId: 'valid', container: fakeContainer(), isCurrent: () => true,
    }).result;

    await expect(invalidResult).resolves.toEqual({status: 'invalid'});
    await expect(validResult).resolves.toEqual(expect.objectContaining({status: 'success'}));
  });

  it('does not return a stale asynchronous render result after a resource switch', async () => {
    let resolveRender!: (value: {svg: string}) => void;
    const slowRender = vi.fn().mockReturnValue(new Promise((resolve) => { resolveRender = resolve; }));
    const mermaid = fakeMermaid({
      render: slowRender,
    });
    const container = fakeContainer();
    let current = true;
    const session = startIsolatedMermaidRender({
      mermaid: mermaid.client,
      source: 'flowchart LR\nA-->B',
      renderId: 'slow-diagram',
      container,
      isCurrent: () => current,
    });

    await vi.waitFor(() => expect(slowRender).toHaveBeenCalledOnce());
    current = false;
    resolveRender({svg: '<svg>old diagram</svg>'});

    await expect(session.result).resolves.toEqual({status: 'stale'});
    expect(container.remove).toHaveBeenCalledTimes(1);
  });

  it('removes the temporary container immediately when cancelled on unmount', async () => {
    let resolveParse!: (value: false) => void;
    const mermaid = fakeMermaid({
      parse: vi.fn().mockReturnValue(new Promise((resolve) => { resolveParse = resolve; })),
    });
    const container = fakeContainer();
    const session = startIsolatedMermaidRender({
      mermaid: mermaid.client,
      source: 'pending',
      renderId: 'pending-diagram',
      container,
      isCurrent: () => true,
    });

    session.cancel();
    expect(container.remove).toHaveBeenCalledOnce();
    resolveParse(false);
    await expect(session.result).resolves.toEqual({status: 'stale'});
    expect(container.remove).toHaveBeenCalledTimes(1);
  });
});
