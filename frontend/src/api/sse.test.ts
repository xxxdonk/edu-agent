import {describe, expect, it} from 'vitest';
import {isTerminalTaskEvent} from './sse';
import type {TaskEvent} from '@/types/api';

function taskEvent(overrides: Partial<TaskEvent>): TaskEvent {
  return {
    event_id: 'event-1',
    task_id: 'task-1',
    sequence: 1,
    event_type: 'task',
    status: 'started',
    progress: 10,
    message: 'started',
    agent: 'orchestrator_agent',
    resource_type: null,
    error: null,
    created_at: '2026-07-16T00:00:00Z',
    ...overrides,
  };
}

describe('isTerminalTaskEvent', () => {
  it('does not close the stream when a single agent completes', () => {
    expect(isTerminalTaskEvent(taskEvent({event_type: 'agent', status: 'completed'}))).toBe(false);
  });

  it.each(['completed', 'partial_success', 'failed'] as const)('closes on terminal task status %s', (status) => {
    expect(isTerminalTaskEvent(taskEvent({status}))).toBe(true);
  });
});
