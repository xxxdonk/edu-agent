import {absoluteApiUrl} from './config';
import type {TaskEvent} from '@/types/api';

export type StreamConnectionStatus = 'connecting' | 'connected' | 'reconnecting' | 'disconnected' | 'closed';

interface StreamHandlers {
  onEvent: (event: TaskEvent) => void;
  onTerminal: () => void;
  onError: (message: string) => void;
  onConnectionChange?: (status: StreamConnectionStatus) => void;
}

const terminalStatuses = new Set(['completed', 'partial_success', 'failed']);

export function connectTaskEvents(eventsUrl: string, handlers: StreamHandlers): () => void {
  let source: EventSource | null = null;
  let stopped = false;
  let lastSequence = 0;
  let retries = 0;
  let terminalNotified = false;
  const seenEventKeys = new Set<string>();
  let reconnectTimer: ReturnType<typeof globalThis.setTimeout> | null = null;

  const eventKey = (event: TaskEvent): string => {
    const sequence = Number(event.sequence);
    if (Number.isFinite(sequence)) return `sequence:${sequence}`;
    if (event.event_id) return `event:${event.event_id}`;
    return [event.event_type, event.status, event.agent, event.resource_type, event.created_at, event.message].join('|');
  };

  const notifyTerminal = () => {
    if (terminalNotified) return;
    terminalNotified = true;
    stopped = true;
    source?.close();
    if (reconnectTimer !== null) globalThis.clearTimeout(reconnectTimer);
    reconnectTimer = null;
    handlers.onConnectionChange?.('closed');
    handlers.onTerminal();
  };

  const open = () => {
    if (stopped) return;
    handlers.onConnectionChange?.(retries > 0 ? 'reconnecting' : 'connecting');
    const url = new URL(absoluteApiUrl(eventsUrl));
    if (lastSequence > 0) url.searchParams.set('after', String(lastSequence));
    source = new EventSource(url);

    const handle = (message: MessageEvent<string>) => {
      if (stopped) return;
      try {
        const event = JSON.parse(message.data) as TaskEvent;
        retries = 0;
        handlers.onConnectionChange?.('connected');
        const sequence = Number(event.sequence);
        const hasSequence = Number.isFinite(sequence);
        if (hasSequence && sequence <= lastSequence) return;
        const key = eventKey(event);
        if (seenEventKeys.has(key)) return;
        seenEventKeys.add(key);
        if (hasSequence) lastSequence = sequence;
        handlers.onEvent(event);
        if (event.event_type === 'task' && terminalStatuses.has(event.status)) {
          notifyTerminal();
        }
      } catch {
        handlers.onError('收到一条无法解析的智能体进度消息，已跳过该事件。');
      }
    };

    for (const eventName of ['task', 'agent', 'review', 'heartbeat']) {
      source.addEventListener(eventName, handle as EventListener);
    }
    source.onopen = () => handlers.onConnectionChange?.('connected');
    source.onmessage = handle;
    source.onerror = () => {
      source?.close();
      if (stopped) return;
      if (retries >= 3) {
        stopped = true;
        handlers.onConnectionChange?.('disconnected');
        handlers.onError('智能体进度连接已中断，正在通过任务状态保留已有结果。');
        return;
      }
      retries += 1;
      handlers.onConnectionChange?.('reconnecting');
      reconnectTimer = globalThis.setTimeout(() => {
        reconnectTimer = null;
        open();
      }, retries * 1000);
    };
  };

  open();
  return () => {
    stopped = true;
    source?.close();
    if (reconnectTimer !== null) globalThis.clearTimeout(reconnectTimer);
    reconnectTimer = null;
    handlers.onConnectionChange?.('closed');
  };
}
