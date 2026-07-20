import {describe, expect, it} from 'vitest';
import type {Resource, SourceReference} from '@/types/api';
import {demoCases} from '@/config/demoCases';
import {
  actualRagSources,
  conversationSuggestions,
  practiceDisplayName,
  resourceDisplayName,
  subjectExamples,
  subjectFamily,
  usesGeneralModel,
} from './subject';

function codingResource(): Resource {
  return {
    resource_id: 'resource-1',
    resource_type: 'coding',
    title: '实践任务',
    content: '任务内容',
    content_format: 'markdown',
    target_topic: '阅读理解',
    difficulty: 'beginner',
    personalization_reason: '根据当前课程生成',
    source_references: [{source_id: 'general-model', title: '通用模型', locator: 'model://general-knowledge', chunk_id: null}],
    review_status: 'approved',
    created_at: '2026-07-20T00:00:00Z',
  };
}

describe('全科学科展示策略', () => {
  it('distinguishes application, computational and code practice without changing coding type', () => {
    expect(practiceDisplayName('高中语文')).toBe('应用实践任务');
    expect(practiceDisplayName('高中数学')).toBe('计算与实验实践');
    expect(practiceDisplayName('Java')).toBe('代码实践');
    expect(resourceDisplayName(codingResource(), '高中语文')).toBe('应用实践任务 · coding 类型');
    expect(codingResource().resource_type).toBe('coding');
  });

  it('provides dynamic high-school math suggestions and general suggestions', () => {
    expect(conversationSuggestions('高中数学')).toEqual([
      '我目前是高二', '我的函数和数列比较薄弱', '我的目标是期末考试', '我每天可以学习45分钟',
    ]);
    expect(conversationSuggestions('')).toContain('我准备大学英语四级');
    expect(conversationSuggestions('')).toContain('我想学习 Java 编程');
  });

  it('contains the required editable subject examples', () => {
    const labels = subjectExamples.map((item) => item.label);
    expect(labels).toHaveLength(17);
    for (const label of ['小学数学', '高中语文', '高中数学', '大学英语', '自动控制原理', '机器学习']) {
      expect(labels).toContain(label);
    }
  });

  it('keeps demo A/B/C cross-disciplinary and free of personal data', () => {
    expect(demoCases[0].input).toContain('高中数学');
    expect(demoCases[1].input).toContain('大学英语');
    expect(demoCases[2].input).toContain('机器学习');
    expect(demoCases.map((item) => item.input).join(' ')).not.toMatch(/[A-Za-z]:\\|API_KEY/);
  });

  it('does not count the general-model marker as a local RAG source', () => {
    const references: SourceReference[] = [
      {source_id: 'general-model', title: '通用模型', locator: 'model://general-knowledge', chunk_id: null},
      {source_id: 'course-1', title: '高中数学资料', locator: 'course/math', chunk_id: 'chunk-1'},
    ];
    expect(usesGeneralModel(references)).toBe(true);
    expect(actualRagSources(references)).toHaveLength(1);
    expect(actualRagSources(references)[0].source_id).toBe('course-1');
  });

  it('recognizes representative subject families', () => {
    expect(subjectFamily('高中英语')).toBe('language');
    expect(subjectFamily('线性代数')).toBe('mathematics');
    expect(subjectFamily('自动控制原理')).toBe('engineering');
    expect(subjectFamily('数据结构')).toBe('computer_science');
  });
});
