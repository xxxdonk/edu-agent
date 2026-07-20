export interface DemoCase {
  id: 'visual_beginner' | 'exam_oriented' | 'project_practice';
  code: 'A' | 'B' | 'C';
  name: string;
  summary: string;
  input: string;
}

// Mirrors the non-sensitive input text in scripts/demo_cases.json. Keeping this
// small browser-side copy avoids exposing local paths or coupling Vite to files
// outside the frontend root.
export const demoCases: DemoCase[] = [
  {
    id: 'visual_beginner',
    code: 'A',
    name: '高中数学基础型',
    summary: '高二数学 · 函数与数列 · 每天 45 分钟',
    input: '我是高二学生，正在学习高中数学，函数和数列基础较弱，目标是提高期末考试成绩。我每天能学习45分钟，喜欢图示、例题和分步骤讲解。',
  },
  {
    id: 'exam_oriented',
    code: 'B',
    name: '大学英语考试型',
    summary: '大学英语 · 阅读与写作 · 每天 60 分钟',
    input: '我是大学生，准备大学英语考试，阅读理解和写作较弱，希望进行阶段复习。我每天能学习60分钟，喜欢词汇清单、阅读练习和错题分析。',
  },
  {
    id: 'project_practice',
    code: 'C',
    name: '项目实践型',
    summary: '分类项目 · 代码实验 · 每天 90 分钟',
    input: '我是人工智能专业大二学生，目前课程是机器学习，已有Python和机器学习基础，正在做一个客户流失分类项目，对逻辑回归、模型选择和参数调优不熟。希望完成可运行项目并比较模型效果，每天可以学习90分钟，偏好代码案例、实验和项目任务。',
  },
];
