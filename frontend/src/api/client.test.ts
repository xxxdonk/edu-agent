import {describe, expect, it, vi} from 'vitest';

const mocks = vi.hoisted(() => ({post: vi.fn()}));

vi.mock('axios', () => ({
  default: {
    create: vi.fn(() => ({post: mocks.post})),
  },
}));

import {api, PATH_GENERATION_TIMEOUT_MS} from './client';
import type {PathGenerateRequest, ProfileChatRequest} from '@/types/api';

describe('Planner API timeout', () => {
  it('uses the Planner-specific timeout and caller cancellation signal', async () => {
    const controller = new AbortController();
    const payload = {student_id: 'student-timeout'} as PathGenerateRequest;
    const path = {path_id: 'path-timeout'};
    mocks.post.mockResolvedValueOnce({data: {path}});

    await expect(api.generatePath(payload, controller.signal)).resolves.toBe(path);

    expect(PATH_GENERATION_TIMEOUT_MS).toBe(270_000);
    expect(mocks.post).toHaveBeenCalledWith('/api/path/generate', payload, {
      signal: controller.signal,
      timeout: PATH_GENERATION_TIMEOUT_MS,
    });
  });
});

describe('Profile API cancellation', () => {
  it('passes the caller cancellation signal without changing the payload', async () => {
    const controller = new AbortController();
    const payload = {
      student_id: 'profile-signal-student',
      messages: [{message_id: 'message-1', role: 'user', content: '更新画像'}],
    } as ProfileChatRequest;
    const response = {profile: {version: 1}};
    mocks.post.mockResolvedValueOnce({data: response});

    await expect(api.chat(payload, controller.signal)).resolves.toBe(response);

    expect(mocks.post).toHaveBeenLastCalledWith('/api/profile/chat', payload, {
      signal: controller.signal,
    });
  });
});
