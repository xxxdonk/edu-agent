import MarkdownIt from 'markdown-it';
import hljs from 'highlight.js';
import type {LearningPath, QuizDocument, Resource, StudentProfile} from '@/types/api';

const markdown = new MarkdownIt({
  html: false,
  linkify: true,
  typographer: false,
  highlight(code: string, language: string): string {
    if (language && hljs.getLanguage(language)) {
      return `<pre class="hljs"><code>${hljs.highlight(code, {language}).value}</code></pre>`;
    }
    const escaped = code.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    return `<pre class="hljs"><code>${escaped}</code></pre>`;
  },
});

export function renderMarkdown(content: string): string {
  return markdown.render(content);
}

export function normalizeMermaidContent(content: string): string {
  const fencedBlock = content.match(/```(?:mermaid)?\s*\r?\n([\s\S]*?)```/i);
  const source = fencedBlock?.[1] ?? content;
  return source.replace(/<!--[\s\S]*?-->/g, '').trim();
}

export function parseQuiz(resource: Resource | undefined): QuizDocument | null {
  if (!resource || resource.resource_type !== 'quiz') return null;
  try {
    const parsed = JSON.parse(resource.content) as QuizDocument;
    if (!Array.isArray(parsed.questions)) return null;
    return parsed;
  } catch {
    return null;
  }
}

function displayProfileValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '未识别';
  if (Array.isArray(value)) return value.length ? value.join('、') : '未识别';
  if (typeof value === 'object') {
    const budget = value as {minutes_per_day?: number; days_per_week?: number};
    return `每天 ${budget.minutes_per_day ?? 0} 分钟，每周 ${budget.days_per_week ?? 0} 天`;
  }
  return String(value);
}

export interface DiffRow {label: string; before: string; after: string}

export function profileDiff(before: StudentProfile | null, after: StudentProfile | null): DiffRow[] {
  if (!before || !after) return [];
  const fields: Array<[keyof StudentProfile, string]> = [
    ['major', '专业'], ['course', '当前课程'], ['knowledge_level', '知识水平'],
    ['learning_goals', '学习目标'], ['weak_topics', '薄弱知识点'], ['learning_history', '学习历史'],
    ['cognitive_style', '认知风格'], ['language_preference', '语言偏好'],
    ['resource_preference', '资源偏好'], ['time_budget', '可用学习时间'],
  ];
  return fields.flatMap(([key, label]) => {
    const left = displayProfileValue((before[key] as {value?: unknown})?.value);
    const right = displayProfileValue((after[key] as {value?: unknown})?.value);
    return left === right ? [] : [{label, before: left, after: right}];
  });
}

export function pathDiff(before: LearningPath | null, after: LearningPath | null): DiffRow[] {
  if (!before || !after) return [];
  const max = Math.max(before.steps.length, after.steps.length);
  const rows: DiffRow[] = [];
  for (let index = 0; index < max; index += 1) {
    const left = before.steps[index];
    const right = after.steps[index];
    const beforeText = left ? `${left.step}. ${left.topic}（${left.estimated_minutes} 分钟）` : '无';
    const afterText = right ? `${right.step}. ${right.topic}（${right.estimated_minutes} 分钟）` : '无';
    if (beforeText !== afterText) rows.push({label: `步骤 ${index + 1}`, before: beforeText, after: afterText});
  }
  return rows;
}
