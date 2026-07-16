import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {connectTaskEvents} from './sse';
import type {TaskEvent} from '@/types/api';

type Listener = (event: MessageEvent<string>) => void;

class FakeEventSource {
  static instances: FakeEventSource[] = [];

  readonly url: string;
  readonly close = vi.fn();
  onmessage: Listener | null = null;
  onerror: ((event: Event) => void) | null = null;
  private readonly listeners = new Map<string, Listener[]>();

  constructor(url: URL | string) {
    this.url = String(url);
    FakeEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: EventListener) {
    const listeners = this.listeners.get(type) ?? [];
    listeners.push(listener as Listener);
    this.listeners.set(type, listeners);
  }

  emit(type: string, event: TaskEvent) {
    const message = {data: JSON.stringify(event)} as MessageEvent<string>;
    for (const listener of this.listeners.get(type) ?? []) listener(message);
    if (type === 'message') this.onmessage?.(message);
  }

  fail() {
    this.onerror?.({type: 'error'} as Event);
  }
}

function taskEvent(sequence: number, status: string, eventType: TaskEvent['event_type'] = 'agent'): TaskEvent {
  return {
    event_id: `event-${sequence}`,
    task_id: 'task-1',
    sequence,
    event_type: eventType,
    status,
    progress: status === 'started' ? 10 : 100,
    message: `event ${sequence}`,
    agent: eventType === 'agent' ? 'quiz_agent' : 'orchestrator_agent',
    resource_type: eventType === 'agent' ? 'quiz' : null,
    error: null,
    created_at: '2026-07-16T00:00:00Z',
  };
}

describe('connectTaskEvents', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    FakeEventSource.instances = [];
    vi.stubGlobal('EventSource', FakeEventSource);
  });

  afterEach(() => {
    vi.clearAllTimers();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('deduplicates events and resumes from the last sequence after reconnecting', async () => {
    const onEvent = vi.fn();
    const stop = connectTaskEvents('/api/tasks/task-1/events', {
      onEvent,
      onTerminal: vi.fn(),
      onError: vi.fn(),
    });
    const first = FakeEventSource.instances[0];

    first.emit('agent', taskEvent(1, 'started'));
    first.emit('agent', taskEvent(1, 'started'));
    expect(onEvent).toHaveBeenCalledTimes(1);

    first.fail();
    await vi.advanceTimersByTimeAsync(1000);
    const resumed = FakeEventSource.instances[1];
    expect(new URL(resumed.url).searchParams.get('after')).toBe('1');

    resumed.emit('agent', taskEvent(2, 'completed'));
    expect(onEvent.mock.calls.map(([event]) => event.sequence)).toEqual([1, 2]);
    stop();
  });

  it.each(['completed', 'partial_success', 'failed'])('handles %s as a stable terminal state', (status) => {
    const onEvent = vi.fn();
    const onTerminal = vi.fn();
    connectTaskEvents('/api/tasks/task-1/events', {
      onEvent,
      onTerminal,
      onError: vi.fn(),
    });
    const source = FakeEventSource.instances[0];

    source.emit('task', taskEvent(1, status, 'task'));
    source.emit('task', taskEvent(2, status, 'task'));

    expect(onEvent).toHaveBeenCalledTimes(1);
    expect(onTerminal).toHaveBeenCalledTimes(1);
    expect(source.close).toHaveBeenCalledTimes(1);
  });

  it('does not treat an individual agent completion or failure as a task terminal state', () => {
    const onEvent = vi.fn();
    const onTerminal = vi.fn();
    connectTaskEvents('/api/tasks/task-1/events', {
      onEvent,
      onTerminal,
      onError: vi.fn(),
    });
    const source = FakeEventSource.instances[0];

    source.emit('agent', taskEvent(1, 'completed'));
    source.emit('agent', taskEvent(2, 'failed'));

    expect(onEvent).toHaveBeenCalledTimes(2);
    expect(onTerminal).not.toHaveBeenCalled();
    expect(source.close).not.toHaveBeenCalled();
  });

  it('stops reconnecting after three retries without inventing a terminal event', async () => {
    const onError = vi.fn();
    const onTerminal = vi.fn();
    connectTaskEvents('/api/tasks/task-1/events', {
      onEvent: vi.fn(),
      onTerminal,
      onError,
    });

    for (const delay of [1000, 2000, 3000]) {
      FakeEventSource.instances.at(-1)?.fail();
      await vi.advanceTimersByTimeAsync(delay);
    }
    FakeEventSource.instances.at(-1)?.fail();

    expect(FakeEventSource.instances).toHaveLength(4);
    expect(onError).toHaveBeenCalledTimes(1);
    expect(onTerminal).not.toHaveBeenCalled();
    expect(vi.getTimerCount()).toBe(0);
  });
});
