import type {Resource, SourceReference, StudentProfile} from '@/types/api';

export type UiSubjectFamily = 'language' | 'mathematics' | 'natural_science' | 'social_science' | 'engineering' | 'computer_science' | 'arts' | 'other';

export interface SubjectExample {
  label: string;
  prompt: string;
}

export const subjectExamples: SubjectExample[] = [
  {label: '小学数学', prompt: '我是小学五年级学生，想提高数学应用题，每天可以学习30分钟。'},
  {label: '初中英语', prompt: '我是初二学生，想提高英语语法和阅读理解，每天可以学习40分钟。'},
  {label: '高中语文', prompt: '我是高二学生，想提高高中语文阅读理解和写作，目标是期末考试。'},
  {label: '高中数学', prompt: '我是高二学生，想提高高中数学，函数和数列比较薄弱，目标是期末考试，每天可以学习45分钟。'},
  {label: '高中物理', prompt: '我是高一学生，正在学习高中物理，力学比较薄弱，希望通过分步骤例题巩固。'},
  {label: '高中化学', prompt: '我是高二学生，想复习高中化学有机化学，目标是期末考试。'},
  {label: '高中历史', prompt: '我是高二学生，想梳理高中历史时间线和材料题答题方法。'},
  {label: '高中地理', prompt: '我是高中生，地理综合题比较薄弱，希望学习图表和区域分析方法。'},
  {label: '大学英语', prompt: '我是大学生，准备大学英语考试，阅读理解和写作较弱，每天可以学习60分钟。'},
  {label: '高等数学', prompt: '我是大学生，正在学习高等数学，极限部分比较薄弱。'},
  {label: '线性代数', prompt: '我是大学生，想复习线性代数，矩阵和线性变换不熟悉。'},
  {label: 'Java', prompt: '我想从零开始学习 Java 编程，偏好示例、练习和小项目。'},
  {label: '数据结构', prompt: '我正在学习数据结构，二叉树遍历比较薄弱，希望通过代码案例巩固。'},
  {label: '计算机组成原理', prompt: '我正在复习计算机组成原理，存储系统比较薄弱。'},
  {label: '自动控制原理', prompt: '我是自动化专业学生，正在复习自动控制原理，根轨迹和频率响应比较薄弱。'},
  {label: '嵌入式系统', prompt: '我正在学习嵌入式系统，希望掌握 STM32 中断和调试方法。'},
  {label: '机器学习', prompt: '我有 Python 基础，想学习机器学习中的逻辑回归和模型评估。'},
];

export function profileCourse(profile: StudentProfile | null): string {
  return String(profile?.course.value ?? '').trim();
}

export function subjectFamily(course: string): UiSubjectFamily {
  const value = course.toLowerCase();
  if (/语文|英语|语言|写作|阅读/.test(value)) return 'language';
  if (/数学|概率|统计|矩阵|高数|线性代数/.test(value)) return 'mathematics';
  if (/物理|化学|生物/.test(value)) return 'natural_science';
  if (/历史|地理|政治|道德|马克思/.test(value)) return 'social_science';
  if (/java|python|c语言|数据结构|算法|计算机|数据库|软件|机器学习|深度学习/.test(value)) return 'computer_science';
  if (/电路|电子|信号|控制|嵌入式|单片机|通信|工程|机械/.test(value)) return 'engineering';
  if (/绘画|美术|音乐|艺术/.test(value)) return 'arts';
  return 'other';
}

export function practiceDisplayName(course: string): string {
  const family = subjectFamily(course);
  if (family === 'computer_science') return '代码实践';
  if (['mathematics', 'natural_science', 'engineering'].includes(family)) return '计算与实验实践';
  return '应用实践任务';
}

export function resourceDisplayName(resource: Resource, course: string): string {
  if (resource.resource_type === 'coding') return `${practiceDisplayName(course)} · coding 类型`;
  return ({explanation: 'Markdown 课程讲解', mind_map: 'Mermaid 思维导图', quiz: '分层练习题', reading: '拓展阅读'} as const)[resource.resource_type];
}

export function conversationSuggestions(course: string): string[] {
  if (/高中数学/.test(course)) return ['我目前是高二', '我的函数和数列比较薄弱', '我的目标是期末考试', '我每天可以学习45分钟'];
  if (!course) return ['我想学高中数学', '我准备大学英语四级', '我想复习自动控制原理', '我想学习 Java 编程'];
  return [`我想明确${course}的学习目标`, `我目前最薄弱的知识点是……`, '我每天可以学习45分钟', '我喜欢例题、图示和分步骤讲解'];
}

export function actualRagSources(references: SourceReference[]): SourceReference[] {
  return references.filter((reference) => reference.source_id !== 'general-model');
}

export function usesGeneralModel(references: SourceReference[]): boolean {
  return references.some((reference) => reference.source_id === 'general-model');
}
