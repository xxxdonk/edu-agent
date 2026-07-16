import {describe, expect, it} from 'vitest';
import {normalizeMermaidContent, parseQuiz} from './content';
import type {Resource} from '@/types/api';

const baseResource: Resource = {
  resource_id: 'r1', resource_type: 'quiz', title: '测试', target_topic: '梯度下降',
  difficulty: 'beginner', personalization_reason: '针对薄弱点生成', source_references: [],
  review_status: 'approved', created_at: '2026-07-15T00:00:00Z', content_format: 'json', content: '',
};

describe('parseQuiz', () => {
  it('parses the frozen quiz resource shape', () => {
    const resource = {...baseResource, content: JSON.stringify({topic: '梯度下降', difficulty: 'beginner', questions: []})};
    expect(parseQuiz(resource)?.topic).toBe('梯度下降');
  });

  it('returns null for malformed agent content', () => {
    expect(parseQuiz({...baseResource, content: '{bad json'})).toBeNull();
  });
});

describe('normalizeMermaidContent', () => {
  it('extracts Mermaid source from a fenced resource response', () => {
    const content = '```mermaid\nmindmap\n  root((梯度下降))\n```\n\n<!-- 知识库参考片段已用于生成 -->';
    expect(normalizeMermaidContent(content)).toBe('mindmap\n  root((梯度下降))');
  });

  it('keeps raw Mermaid source while removing trailing comments', () => {
    const content = 'flowchart TD\n  A --> B\n<!-- source -->';
    expect(normalizeMermaidContent(content)).toBe('flowchart TD\n  A --> B');
  });
});
