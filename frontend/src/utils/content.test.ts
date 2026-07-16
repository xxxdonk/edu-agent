import {describe, expect, it} from 'vitest';
import {evaluationQuestionFeedback, formatSourceTitles, parseQuiz, pathDiff, profileDiff} from './content';
import type {LearningPath, Resource, StudentProfile} from '@/types/api';

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

describe('formatSourceTitles', () => {
  it('deduplicates repeated source titles while preserving order', () => {
    const sources = [
      {source_id: 's1', title: '线性回归', locator: 'chapter-1', chunk_id: 'c1'},
      {source_id: 's1', title: '线性回归', locator: 'chapter-1', chunk_id: 'c2'},
      {source_id: 's2', title: '逻辑回归', locator: 'chapter-2', chunk_id: null},
    ];
    expect(formatSourceTitles(sources)).toBe('线性回归、逻辑回归');
  });

  it('provides a readable fallback when no source title is available', () => {
    expect(formatSourceTitles([])).toBe('暂无可展示来源');
  });
});

describe('evaluationQuestionFeedback', () => {
  const feedback = [
    '题目 quiz::q1：正确',
    '题目 quiz::q2：部分正确，需要复习 梯度下降',
    '题目 quiz::q3：回答不正确，需要重点复习 梯度下降',
  ].join('\n');

  it('does not mistake an incorrect answer for a correct one', () => {
    expect(evaluationQuestionFeedback(feedback, 'quiz::q3').status).toBe('incorrect');
  });

  it('distinguishes correct and partially correct answers', () => {
    expect(evaluationQuestionFeedback(feedback, 'quiz::q1').status).toBe('correct');
    expect(evaluationQuestionFeedback(feedback, 'quiz::q2').status).toBe('partial');
  });
});

describe('evaluation diffs', () => {
  const field = <T>(value: T) => ({value, evidence: [], confidence: 0.8});
  const profile = (version: number, weakTopics: string[]): StudentProfile => ({
    student_id: 'student-1', version,
    major: field('计算机'), course: field('机器学习'), knowledge_level: field('beginner'),
    learning_goals: field(['完成课程项目']), weak_topics: field(weakTopics), learning_history: field([]),
    cognitive_style: field('visual'), language_preference: field('中文'),
    resource_preference: field(['代码实践']), time_budget: field({minutes_per_day: 45, days_per_week: 5}),
    evidence: [], confidence: 0.8, updated_at: '2026-07-17T00:00:00Z',
  });
  const path = (pathId: string, topics: string[]): LearningPath => ({
    path_id: pathId, student_id: 'student-1', profile_version: 1, course: '机器学习', status: 'active',
    steps: topics.map((topic, index) => ({
      step: index + 1, topic, learning_goal: `掌握${topic}`, reason: '针对薄弱点',
      recommended_resources: ['explanation'], completion_criteria: ['完成练习'],
      estimated_minutes: 45, prerequisites: [],
    })),
    adjustment_reason: null, generation_mode: 'development_rule_based', created_at: '2026-07-17T00:00:00Z',
  });

  it('shows changed profile dimensions only', () => {
    expect(profileDiff(profile(1, ['梯度下降']), profile(2, ['梯度下降', '学习率']))).toEqual([
      {label: '薄弱知识点', before: '梯度下降', after: '梯度下降、学习率'},
    ]);
  });

  it('shows added learning-path steps', () => {
    expect(pathDiff(path('p1', ['梯度下降']), path('p2', ['梯度下降', '学习率调优']))).toEqual([
      {label: '步骤 2', before: '无', after: '2. 学习率调优（45 分钟）'},
    ]);
  });
});
