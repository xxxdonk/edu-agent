import {absoluteApiUrl} from './config';
import type {TaskEvent} from '@/types/api';

interface StreamHandlers {
  onEvent: (event: TaskEvent) => void;
  onTerminal: () => void;
  onError: (message: string) => void;
}

const terminalStatuses = new Set(['completed', 'partial_success', 'failed']);

export function connectTaskEvents(eventsUrl: string, handlers: StreamHandlers): () => void {
  let source: EventSource | null = null;
  let stopped = false;
  let lastSequence = 0;
  let retries = 0;
  let terminalNotified = false;
  let reconnectTimer: ReturnType<typeof globalThis.setTimeout> | null = null;

  const notifyTerminal = () => {
    if (terminalNotified) return;
    terminalNotified = true;
    stopped = true;
    source?.close();
    if (reconnectTimer !== null) globalThis.clearTimeout(reconnectTimer);
    reconnectTimer = null;
    handlers.onTerminal();
  };

  const open = () => {
    if (stopped) return;
    const url = new URL(absoluteApiUrl(eventsUrl));
    if (lastSequence > 0) url.searchParams.set('after', String(lastSequence));
    source = new EventSource(url);

    const handle = (message: MessageEvent<string>) => {
      if (stopped) return;
      try {
        const event = JSON.parse(message.data) as TaskEvent;
        retries = 0;
        if (event.sequence <= lastSequence) return;
        lastSequence = event.sequence;
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
    source.onmessage = handle;
    source.onerror = () => {
      source?.close();
      if (stopped) return;
      if (retries >= 3) {
        stopped = true;
        handlers.onError('智能体进度连接已中断，正在通过任务状态保留已有结果。');
        return;
      }
      retries += 1;
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
  };
}
