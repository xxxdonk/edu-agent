import MarkdownIt from 'markdown-it';
import hljs from 'highlight.js';
import katex from 'katex';
import type {LearningPath, QuizDocument, Resource, StudentProfile} from '@/types/api';

function renderMath(content: string, displayMode: boolean): string {
  return katex.renderToString(content, {
    displayMode,
    throwOnError: false,
    strict: false,
  });
}

function findClosingDollar(source: string, start: number): number {
  let cursor = start;
  while (cursor < source.length) {
    const closing = source.indexOf('$', cursor);
    if (closing < 0) return -1;

    let backslashes = 0;
    for (let index = closing - 1; index >= 0 && source[index] === '\\'; index -= 1) backslashes += 1;
    if (backslashes % 2 === 0 && closing > start && !/\s/.test(source[closing - 1])) return closing;
    cursor = closing + 1;
  }
  return -1;
}

function installMathRules(markdown: MarkdownIt): void {
  markdown.inline.ruler.before('escape', 'math_inline', (state, silent) => {
    const start = state.pos;
    let contentStart = start;
    let contentEnd = -1;
    let end = -1;
    let markup = '';

    if (state.src.startsWith('\\(', start)) {
      contentStart = start + 2;
      contentEnd = state.src.indexOf('\\)', contentStart);
      end = contentEnd < 0 ? -1 : contentEnd + 2;
      markup = '\\(\\)';
    } else if (state.src[start] === '$' && state.src[start + 1] !== '$' && !/\s/.test(state.src[start + 1] ?? '')) {
      contentStart = start + 1;
      contentEnd = findClosingDollar(state.src, contentStart);
      end = contentEnd < 0 ? -1 : contentEnd + 1;
      markup = '$';
    }

    if (contentEnd < contentStart || end < 0) return false;
    if (!silent) {
      const token = state.push('math_inline', 'math', 0);
      token.content = state.src.slice(contentStart, contentEnd);
      token.markup = markup;
    }
    state.pos = end;
    return true;
  });

  markdown.block.ruler.before('fence', 'math_block', (state, startLine, endLine, silent) => {
    const firstStart = state.bMarks[startLine] + state.tShift[startLine];
    const firstLine = state.src.slice(firstStart, state.eMarks[startLine]);
    const delimiter = firstLine.startsWith('\\[')
      ? {open: '\\[', close: '\\]'}
      : firstLine.startsWith('$$')
        ? {open: '$$', close: '$$'}
        : null;
    if (!delimiter) return false;

    const lines: string[] = [];
    const firstContent = firstLine.slice(delimiter.open.length);
    const firstClose = firstContent.indexOf(delimiter.close);
    let nextLine = startLine + 1;

    if (firstClose >= 0) {
      if (firstContent.slice(firstClose + delimiter.close.length).trim()) return false;
      lines.push(firstContent.slice(0, firstClose));
    } else {
      if (firstContent) lines.push(firstContent);
      let closed = false;
      for (let line = startLine + 1; line < endLine; line += 1) {
        const lineText = state.src.slice(state.bMarks[line] + state.tShift[line], state.eMarks[line]);
        const close = lineText.indexOf(delimiter.close);
        if (close < 0) {
          lines.push(lineText);
          continue;
        }
        if (lineText.slice(close + delimiter.close.length).trim()) return false;
        lines.push(lineText.slice(0, close));
        nextLine = line + 1;
        closed = true;
        break;
      }
      if (!closed) return false;
    }

    if (silent) return true;
    state.line = nextLine;
    const token = state.push('math_block', 'math', 0);
    token.block = true;
    token.content = lines.join('\n').trim();
    token.map = [startLine, nextLine];
    token.markup = delimiter.open;
    return true;
  });

  markdown.renderer.rules.math_inline = (tokens, index) => renderMath(tokens[index].content, false);
  markdown.renderer.rules.math_block = (tokens, index) => `${renderMath(tokens[index].content, true)}\n`;
}

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

installMathRules(markdown);

export function renderMarkdown(content: string): string {
  return markdown.render(content);
}

export function formatSourceTitles(sources: Resource['source_references']): string {
  const titles = sources.map((source) => source.title.trim()).filter(Boolean);
  return [...new Set(titles)].join('、') || '暂无可展示来源';
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
  if (value === null || value === undefined || value === '') return '信息不足';
  if (Array.isArray(value)) return value.length ? value.join('、') : '信息不足';
  if (typeof value === 'object') {
    const budget = value as {minutes_per_day?: number; days_per_week?: number};
    return `每天 ${budget.minutes_per_day ?? 0} 分钟，每周 ${budget.days_per_week ?? 0} 天`;
  }
  return String(value);
}

export interface DiffRow {label: string; before: string; after: string}

export type EvaluationQuestionStatus = 'correct' | 'partial' | 'incorrect' | 'unknown';

export interface EvaluationQuestionFeedback {
  line: string;
  status: EvaluationQuestionStatus;
}

export function evaluationQuestionFeedback(feedback: string, questionId: string): EvaluationQuestionFeedback {
  const prefix = `题目 ${questionId}：`;
  const line = feedback.split('\n').find((item) => item.startsWith(prefix)) ?? '';
  const detail = line.slice(prefix.length);
  if (detail === '正确') return {line, status: 'correct'};
  if (detail.startsWith('部分正确')) return {line, status: 'partial'};
  if (detail.includes('不正确')) return {line, status: 'incorrect'};
  return {line, status: 'unknown'};
}

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
