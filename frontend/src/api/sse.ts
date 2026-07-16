import {absoluteApiUrl} from './config';
import type {TaskEvent} from '@/types/api';

interface StreamHandlers {
  onEvent: (event: TaskEvent) => void;
  onTerminal: () => void;
  onError: (message: string) => void;
}

const terminalStatuses = new Set(['completed', 'partial_success', 'failed']);

export function isTerminalTaskEvent(event: TaskEvent): boolean {
  return event.event_type === 'task' && terminalStatuses.has(event.status);
}

export function connectTaskEvents(eventsUrl: string, handlers: StreamHandlers): () => void {
  let source: EventSource | null = null;
  let stopped = false;
  let lastSequence = 0;
  let retries = 0;
  let reconnectTimer: number | null = null;

  const open = () => {
    const url = new URL(absoluteApiUrl(eventsUrl));
    if (lastSequence > 0) url.searchParams.set('after', String(lastSequence));
    source = new EventSource(url);

    const handle = (message: MessageEvent<string>) => {
      try {
        const event = JSON.parse(message.data) as TaskEvent;
        if (event.sequence <= lastSequence) return;
        lastSequence = event.sequence;
        retries = 0;
        handlers.onEvent(event);
        if (isTerminalTaskEvent(event)) {
          stopped = true;
          source?.close();
          handlers.onTerminal();
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
        handlers.onError('智能体进度连接已中断，正在通过任务状态保留已有结果。');
        handlers.onTerminal();
        return;
      }
      retries += 1;
      reconnectTimer = window.setTimeout(open, retries * 1000);
    };
  };

  open();
  return () => {
    stopped = true;
    source?.close();
    if (reconnectTimer !== null) window.clearTimeout(reconnectTimer);
  };
}
